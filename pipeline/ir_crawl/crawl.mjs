// 企業IRサイト LLMナビ型クロール（本番）— 並列・再開可能
// 描画 → IR/ニュース一覧を発見（ヒューリスティック + LLMナビ fallback）→ 提携系リリースを抽出
// → Kimi(moonshot-v1-32k) で構造化 → data/ir_relations.json（build 取込用スキーマ）
//
// 実行: KIMI_API_KEY=xxx node crawl.mjs [concurrency]
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = path.dirname(fileURLToPath(import.meta.url));
const DATA = path.join(__dir, 'data');
const KIMI_KEY = process.env.KIMI_API_KEY;
const KIMI_URL = 'https://api.moonshot.ai/v1/chat/completions';
const KIMI_MODEL = process.env.KIMI_MODEL || 'moonshot-v1-32k';

const CONCURRENCY = parseInt(process.argv[2] || '6', 10);
const MAX_RELEASES_PER_CO = 5;
const NAV_TIMEOUT = 25000;
const PROGRESS_PATH = path.join(DATA, 'crawl_progress.json');
const OUT_PATH = path.join(DATA, 'ir_relations.json');

const IR_LINK_RE = /news|ニュース|press|プレス|release|リリース|お知らせ|^ir$|investor|topics|新着/i;
const ALLIANCE_RE = /提携|出資|買収|合弁|資本|業務提携|協業|協力|株式(取得|譲渡)|子会社化|資本参加|アライアンス|M&A|統合|パートナーシップ|共同|資本参画|資本提携/;
const RELEASE_HREF_RE = /\/(news|press|release|topics|ir|pdf).*?(20\d\d|\d{6,8})/i;

const VALID_TYPES = new Set([
  'business_alliance', 'capital_alliance', 'joint_venture', 'technology_license',
  'joint_research', 'merger_acquisition', 'ownership', 'major_customer',
]);

const EXTRACT_PROMPT = (filerName, title, body) => `あなたは企業のプレスリリースから企業間の関係を抽出する専門家です。
発表企業は「${filerName}」です。以下のリリースから、発表企業と「他の実在企業」との関係をJSON配列のみで返してください。
関係がなければ [] を返す。推測や本文にない情報は禁止。発表企業自身や個人・行政・団体は対象外、企業のみ。

各要素: {"counterparty":"相手企業の正式名称","relation_type":"<enum>","date":"YYYY-MM-DD or null","evidence_quote":"根拠となる本文の一文(60字以内)"}
relation_type: business_alliance(業務提携) / capital_alliance(資本業務提携) / joint_venture(合弁設立) / technology_license(技術提携・ライセンス) / joint_research(共同研究) / merger_acquisition(買収・合併) / ownership(出資・株式取得) / major_customer(主要顧客・大口取引)

見出し: ${title}
本文: ${body.slice(0, 5000)}

JSON配列のみ:`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function kimi(messages, maxTokens = 800) {
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    // タイムアウト必須: 設定しないと応答が来ない Kimi 呼び出しでワーカーが無限ハングする
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), 60000);
    let res;
    try {
      res = await fetch(KIMI_URL, {
        method: 'POST',
        headers: { Authorization: `Bearer ${KIMI_KEY}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: KIMI_MODEL, messages, max_tokens: maxTokens, temperature: 0.3 }),
        signal: ac.signal,
      });
    } catch (e) {
      clearTimeout(timer);
      if (attempt === 4) throw new Error(`Kimi timeout/network: ${String(e).slice(0, 80)}`);
      await sleep(2000 * attempt);
      continue;
    }
    clearTimeout(timer);
    if (res.status === 429 || res.status >= 500) {
      if (attempt === 4) throw new Error(`Kimi ${res.status} (overloaded)`);
      await sleep(2000 * attempt + Math.floor(1000 * (attempt / 4)));
      continue;
    }
    if (!res.ok) throw new Error(`Kimi ${res.status}: ${(await res.text()).slice(0, 120)}`);
    const data = await res.json();
    return { content: (data.choices?.[0]?.message?.content || '').trim(), tokens: data.usage?.total_tokens ?? 0 };
  }
  return { content: '', tokens: 0 };
}

function parseJsonArray(text) {
  const m = text.match(/\[[\s\S]*\]/);
  if (!m) return [];
  try { const v = JSON.parse(m[0]); return Array.isArray(v) ? v : []; } catch { return []; }
}

async function extractRelations(filerName, title, body) {
  const { content, tokens } = await kimi([{ role: 'user', content: EXTRACT_PROMPT(filerName, title, body) }]);
  const rels = parseJsonArray(content).filter((r) => r && r.counterparty && VALID_TYPES.has(r.relation_type));
  return { rels, tokens };
}

async function anchors(page) {
  return page.$$eval('a[href]', (as) =>
    as.map((a) => ({ text: (a.textContent || '').replace(/\s+/g, ' ').trim(), href: a.href }))
      .filter((x) => x.href && x.href.startsWith('http')));
}

async function findIrPage(page, homeUrl, budget) {
  await page.goto(homeUrl, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
  await page.waitForTimeout(1200);
  const links = await anchors(page);
  const cand = links.filter((l) => IR_LINK_RE.test(l.text + ' ' + l.href));
  const score = (l) => {
    const s = (l.text + ' ' + l.href).toLowerCase();
    if (/news|ニュース|release|リリース/.test(s)) return 0;
    if (/press|プレス|お知らせ|topics|新着/.test(s)) return 1;
    return 2;
  };
  cand.sort((a, b) => score(a) - score(b));
  if (cand[0]) return cand[0].href;
  // LLMナビ fallback: アンカー一覧から IR/ニュース一覧の URL を選ばせる
  if (budget.tokens < budget.maxTokens) {
    const list = links.slice(0, 60).map((l, i) => `${i}: ${l.text.slice(0, 30)} | ${l.href}`).join('\n');
    const { content, tokens } = await kimi([{ role: 'user',
      content: `次のリンク一覧から、企業のニュースリリース/プレスリリース一覧ページのURLを1つだけ選びURLのみ返す。なければ NONE。\n${list}` }], 100);
    budget.tokens += tokens;
    const m = content.match(/https?:\/\/\S+/);
    if (m) return m[0];
  }
  return null;
}

async function collectReleases(page, irUrl) {
  await page.goto(irUrl, { waitUntil: 'networkidle', timeout: NAV_TIMEOUT }).catch(() => {});
  await page.waitForTimeout(1800);
  const items = await anchors(page);
  const seen = new Set();
  const keyword = [];
  const dated = [];
  for (const it of items) {
    if (it.text.length < 8 || seen.has(it.href)) continue;
    seen.add(it.href);
    if (ALLIANCE_RE.test(it.text)) keyword.push(it);
    else if (RELEASE_HREF_RE.test(it.href)) dated.push(it);
  }
  // キーワード一致を優先、不足分を日付パターンのリリースで補う
  return [...keyword, ...dated].slice(0, MAX_RELEASES_PER_CO);
}

async function fetchText(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => {});
  await page.waitForTimeout(800);
  return page.evaluate(() => document.body?.innerText?.replace(/\s+/g, ' ').trim() || '');
}

async function crawlCompany(ctx, co, budget) {
  const page = await ctx.newPage();
  const out = { code: co.code, relations: [], tokens: 0, ir_page: null, error: null };
  try {
    const ir = await findIrPage(page, co.url, budget);
    out.ir_page = ir;
    if (ir) {
      const releases = await collectReleases(page, ir);
      for (const rel of releases) {
        const text = await fetchText(page, rel.href);
        if (text.length < 80) continue;
        const { rels, tokens } = await extractRelations(co.name, rel.title || '(無題)', text);
        out.tokens += tokens;
        budget.tokens += tokens;
        for (const r of rels) {
          out.relations.push({
            filer_sec_code: co.code,
            counterparty_name: r.counterparty,
            relation_type: r.relation_type,
            date: r.date || null,
            evidence_quote: (r.evidence_quote || '').slice(0, 120),
            source_url: rel.href,
          });
        }
      }
    }
  } catch (e) {
    out.error = String(e).slice(0, 120);
  }
  await page.close();
  return out;
}

function loadProgress() {
  if (fs.existsSync(PROGRESS_PATH)) return JSON.parse(fs.readFileSync(PROGRESS_PATH, 'utf-8'));
  return { done: [], relations: [] };
}

async function main() {
  if (!KIMI_KEY) { console.error('KIMI_API_KEY 未設定'); process.exit(2); }
  const companies = JSON.parse(fs.readFileSync(path.join(DATA, 'sample_urls.json'), 'utf-8'));
  const progress = loadProgress();
  const done = new Set(progress.done);
  const relations = progress.relations;
  const queue = companies.filter((c) => !done.has(c.code));
  console.log(`対象 ${companies.length} 社 / 残り ${queue.length} 社 / 並列 ${CONCURRENCY}`);

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ userAgent: 'persona-project-ir-research/1.0 (+research; contact: project)' });
  const budget = { tokens: 0, maxTokens: 60_000_000 };
  let idx = 0;
  let processed = 0;
  const t0 = Date.now();

  async function worker() {
    while (idx < queue.length) {
      const co = queue[idx++];
      const r = await crawlCompany(ctx, co, budget);
      relations.push(...r.relations);
      done.add(co.code);
      processed += 1;
      if (r.relations.length || r.error) {
        console.log(`${co.code} ${co.name}: ${r.relations.length}件 ${r.tokens}tok ${r.error ? 'ERR:' + r.error : ''}`);
      }
      if (processed % 20 === 0) {
        fs.writeFileSync(PROGRESS_PATH, JSON.stringify({ done: [...done], relations }));
        const rate = processed / ((Date.now() - t0) / 1000);
        console.log(`-- 進捗 ${processed}/${queue.length} 関係${relations.length} ${budget.tokens}tok 残約${Math.round((queue.length - processed) / rate / 60)}分`);
      }
    }
  }
  await Promise.all(Array.from({ length: CONCURRENCY }, worker));
  await browser.close();

  fs.writeFileSync(PROGRESS_PATH, JSON.stringify({ done: [...done], relations }));
  fs.writeFileSync(OUT_PATH, JSON.stringify(relations, null, 1));
  const byType = {};
  for (const r of relations) byType[r.relation_type] = (byType[r.relation_type] || 0) + 1;
  console.log(`\nDONE: ${relations.length}関係 / ${budget.tokens}トークン / ${((Date.now() - t0) / 60000).toFixed(0)}分`);
  console.log('種別:', JSON.stringify(byType));
  console.log('->', OUT_PATH);
}

main();
