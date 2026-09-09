// 企業IRサイト LLMナビ型クロール — 測定用PoC
// ヘッドレス描画 → IR/ニュースリンク自動発見 → 提携系リリース抽出 → Kimiで構造化
// 1社あたりの「IRページ到達率・抽出件数・Kimiトークン・所要時間」を計測する。
//
// 実行: NODE_PATH=<occupation_db_vis>/node_modules KIMI_API_KEY=xxx node crawl_poc.mjs [N]
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dir = path.dirname(fileURLToPath(import.meta.url));
const KIMI_KEY = process.env.KIMI_API_KEY;
const KIMI_URL = 'https://api.moonshot.ai/v1/chat/completions';
// 構造化抽出には非思考モデルを使う（kimi-k2.5 は reasoning にトークンを使い切り content を返さない）
const KIMI_MODEL = process.env.KIMI_MODEL || 'moonshot-v1-32k';

const N = parseInt(process.argv[2] || '8', 10);
const MAX_RELEASES_PER_CO = 3; // 1社あたりKimi抽出するリリース数の上限（PoC）
const NAV_TIMEOUT = 25000;

// IR/ニュース一覧ページへのリンク判定
const IR_LINK_RE = /news|ニュース|press|プレス|release|リリース|お知らせ|ir|investor|topics/i;
// 提携・資本・M&A 系のリリース見出し判定
const ALLIANCE_RE = /提携|出資|買収|合弁|資本|業務提携|協業|協力|株式(取得|譲渡)|子会社化|資本参加|アライアンス|M&A|統合|パートナーシップ|共同/;

const EXTRACT_PROMPT = (title, body) => `あなたは企業のプレスリリースから企業間の関係を抽出する専門家です。
以下のリリース本文から、発表企業と「他の実在企業」との関係を抽出してJSON配列のみで返してください。
関係がなければ [] を返す。推測やページにない情報は禁止。本文に明記された相手企業のみ。

各要素のスキーマ:
{"counterparty":"相手企業の正式名称","relation_type":"<enum>","date":"YYYY-MM-DD or null","evidence_quote":"根拠となる本文中の一文(60字以内)"}
relation_type の enum: business_alliance(業務提携) / capital_alliance(資本業務提携) / joint_venture(合弁設立) / technology_license(技術提携・ライセンス) / joint_research(共同研究) / merger_acquisition(買収・合併) / ownership(出資・株式取得) / major_customer(主要顧客・大口取引)

見出し: ${title}
本文: ${body.slice(0, 4000)}

JSON配列のみ:`;

async function kimiExtract(title, body) {
  const res = await fetch(KIMI_URL, {
    method: 'POST',
    headers: { Authorization: `Bearer ${KIMI_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: KIMI_MODEL,
      messages: [{ role: 'user', content: EXTRACT_PROMPT(title, body) }],
      max_tokens: 800,
      temperature: 0.3,
    }),
  });
  if (!res.ok) throw new Error(`Kimi ${res.status}: ${(await res.text()).slice(0, 150)}`);
  const data = await res.json();
  const tokens = data.usage?.total_tokens ?? 0;
  let content = (data.choices?.[0]?.message?.content || '').trim();
  const m = content.match(/\[[\s\S]*\]/);
  let parsed = [];
  if (m) { try { parsed = JSON.parse(m[0]); } catch { parsed = []; } }
  return { relations: Array.isArray(parsed) ? parsed : [], tokens };
}

async function findIrListPage(page, homeUrl) {
  await page.goto(homeUrl, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT });
  await page.waitForTimeout(1500);
  const links = await page.$$eval('a[href]', (as) =>
    as.map((a) => ({ text: (a.textContent || '').trim().slice(0, 40), href: a.href })));
  // IRっぽいリンクを優先度つきで選ぶ
  const cand = links.filter((l) => l.href && IR_LINK_RE.test(l.text + ' ' + l.href));
  const score = (l) => {
    const s = (l.text + ' ' + l.href).toLowerCase();
    if (/news|ニュース|release|リリース/.test(s)) return 0;
    if (/press|プレス|お知らせ|topics/.test(s)) return 1;
    return 2;
  };
  cand.sort((a, b) => score(a) - score(b));
  return cand[0]?.href || null;
}

async function collectReleases(page, irUrl) {
  await page.goto(irUrl, { waitUntil: 'networkidle', timeout: NAV_TIMEOUT }).catch(() => {});
  await page.waitForTimeout(2000);
  const items = await page.$$eval('a[href]', (as) =>
    as.map((a) => ({ title: (a.textContent || '').replace(/\s+/g, ' ').trim(), href: a.href }))
      .filter((x) => x.title.length >= 8));
  // 重複除去 + 提携系フィルタ
  const seen = new Set();
  const matched = [];
  for (const it of items) {
    if (seen.has(it.href)) continue;
    seen.add(it.href);
    if (ALLIANCE_RE.test(it.title)) matched.push(it);
  }
  return { total: items.length, matched };
}

async function fetchReleaseText(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: NAV_TIMEOUT }).catch(() => {});
  await page.waitForTimeout(1000);
  return page.evaluate(() => document.body?.innerText?.replace(/\s+/g, ' ').trim() || '');
}

async function main() {
  if (!KIMI_KEY) { console.error('KIMI_API_KEY 未設定'); process.exit(2); }
  const companies = JSON.parse(fs.readFileSync(path.join(__dir, 'data', 'sample_urls.json'), 'utf-8')).slice(0, N);
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ userAgent: 'persona-project-ir-research/1.0 (+research)' });
  const results = [];
  let totalTokens = 0;
  const t0 = Date.now();

  for (const co of companies) {
    const page = await ctx.newPage();
    const rec = { code: co.code, name: co.name, url: co.url, ir_page: null,
                  releases_total: 0, releases_matched: 0, relations: [], tokens: 0, ms: 0 };
    const cs = Date.now();
    try {
      const ir = await findIrListPage(page, co.url);
      rec.ir_page = ir;
      if (ir) {
        const { total, matched } = await collectReleases(page, ir);
        rec.releases_total = total;
        rec.releases_matched = matched.length;
        for (const rel of matched.slice(0, MAX_RELEASES_PER_CO)) {
          const text = await fetchReleaseText(page, rel.href);
          if (text.length < 50) continue;
          const { relations, tokens } = await kimiExtract(rel.title, text);
          rec.tokens += tokens;
          for (const r of relations) {
            if (r && r.counterparty) rec.relations.push({ ...r, source_url: rel.href, release_title: rel.title });
          }
        }
      }
    } catch (e) {
      rec.error = String(e).slice(0, 120);
    }
    rec.ms = Date.now() - cs;
    totalTokens += rec.tokens;
    await page.close();
    results.push(rec);
    console.log(`${co.code} ${co.name}: IR=${rec.ir_page ? 'o' : 'x'} 一覧${rec.releases_total} 提携${rec.releases_matched} 抽出${rec.relations.length} ${rec.tokens}tok ${rec.ms}ms` + (rec.error ? ` ERR:${rec.error}` : ''));
  }
  await browser.close();

  const totalMs = Date.now() - t0;
  const withIr = results.filter((r) => r.ir_page).length;
  const totalRel = results.reduce((s, r) => s + r.relations.length, 0);
  const out = { sample: results.length, ir_found: withIr, relations: totalRel,
                total_tokens: totalTokens, total_ms: totalMs, per_company: results };
  fs.writeFileSync(path.join(__dir, 'data', 'poc_results.json'), JSON.stringify(out, null, 1));

  // 全社(3900)換算
  const perCoTok = totalTokens / results.length;
  const perCoMs = totalMs / results.length;
  console.log('\n=== 測定サマリー ===');
  console.log(`対象 ${results.length}社 / IR到達 ${withIr}社(${(withIr / results.length * 100).toFixed(0)}%) / 関係抽出 ${totalRel}件`);
  console.log(`合計 ${totalTokens}トークン / ${(totalMs / 1000).toFixed(0)}秒`);
  console.log(`1社あたり 約${Math.round(perCoTok)}トークン / 約${(perCoMs / 1000).toFixed(1)}秒`);
  console.log(`→ 3,900社換算: 約${(perCoTok * 3900 / 1e6).toFixed(1)}Mトークン / 約${(perCoMs * 3900 / 3600000).toFixed(1)}時間（直列）`);
}

main();
