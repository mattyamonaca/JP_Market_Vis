// 実ブラウザ操作レビュー（Issue #10）。Playwright + ローカルの Chrome（channel: 'chrome'）で
// PC・タッチ・キーボードのシナリオを実行し、スクリーンショットと結果 JSON を qa/results/<日付>/ に残す。
//   npm run dev  （別ターミナル）
//   npm i -D --no-save playwright && node qa/run_qa.mjs [http://localhost:5184/JP_Market_Vis/]
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const url = process.argv[2] || 'http://localhost:5184/JP_Market_Vis/';
const date = new Date().toISOString().slice(0, 10);
const outDir = `qa/results/${date}`;
mkdirSync(outDir, { recursive: true });
const commit = execSync('git rev-parse HEAD').toString().trim();
const results = [];
const record = (scenario, item, ok, detail = '') => { results.push({ scenario, item, ok, detail }); console.log(ok ? 'PASS' : 'FAIL', scenario, '|', item, detail ? '| ' + detail : ''); };

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const version = browser.version();

async function newPage(vp, opts = {}) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 2, ...opts });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
  await page.addInitScript(() => {
    window.__draws = 0;
    const orig = CanvasRenderingContext2D.prototype.clearRect;
    CanvasRenderingContext2D.prototype.clearRect = function (...a) { window.__draws++; return orig.apply(this, a); };
  });
  return { ctx, page, errors };
}
const tab = (page, name) => page.getByRole('button', { name, exact: true });
const zoomOf = (page) => page.evaluate(() => document.querySelector('.map-canvas canvas')?.getContext('2d').getTransform().a ?? null);
const drawsPerSec = async (page) => { await page.evaluate(() => { window.__draws = 0; }); await page.waitForTimeout(1000); return page.evaluate(() => window.__draws); };
const noHScroll = (page) => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

// ---------------------------------------------------------------- PC 1440x900
{
  const { ctx, page, errors } = await newPage({ width: 1440, height: 900 });
  const t0 = Date.now();
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.locator('.map-canvas canvas').waitFor({ timeout: 120000 });
  const loadMs = Date.now() - t0;
  await page.waitForTimeout(5000);
  await page.screenshot({ path: `${outDir}/pc_01_initial.png` });
  record('PC初回', '初回表示（マップ描画まで）', true, `${loadMs} ms`);
  record('PC初回', 'コンソールエラーなし', errors.length === 0, errors.join(' / '));
  record('PC初回', '横スクロールなし', await noHScroll(page));
  const overlap = await page.evaluate(() => {
    const r = (s) => document.querySelector(s)?.getBoundingClientRect();
    const cap = r('.map-caption'), tools = r('.map-tools'), hover = r('.map-hover');
    const inter = (a, b) => a && b && !(a.right < b.left || b.right < a.left || a.bottom < b.top || b.bottom < a.top);
    return { capTools: inter(cap, tools), capHover: inter(cap, hover) };
  });
  record('PC初回', '見出し・操作部品の重なりなし', !overlap.capTools && !overlap.capHover, JSON.stringify(overlap));

  // 通常移動 → 回転 → 移動
  const box = await page.locator('.map-canvas canvas').boundingBox();
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(cx + 120, cy + 40, { steps: 8 }); await page.mouse.up();
  await tab(page, '↻ 回転').click(); await page.waitForTimeout(300);
  record('操作', '回転ON', (await page.getByRole('button', { name: /回転/ }).getAttribute('aria-pressed')) === 'true');
  const z0 = await zoomOf(page);
  await page.mouse.move(cx, cy); await page.mouse.wheel(0, -300); await page.waitForTimeout(400);
  record('操作', '回転中のホイール拡大', (await zoomOf(page)) > z0, `${z0} -> ${await zoomOf(page)}`);
  await page.mouse.move(cx, cy); await page.mouse.down();
  await page.evaluate(() => { window.__draws = 0; });
  for (let i = 0; i < 20; i++) { await page.mouse.move(cx + i * 8, cy); await page.waitForTimeout(30); }
  const dragDraws = await page.evaluate(() => window.__draws);
  await page.mouse.up(); await page.waitForTimeout(1200);
  const idleDraws = await drawsPerSec(page);
  record('操作', '連続ドラッグ後、詳細を誤って開かない', await page.locator('.map-view').isVisible() && (await page.locator('.graph-view').count()) === 0);
  record('負荷', '回転ドラッグ中の再描画回数（約0.6秒）', dragDraws > 0, String(dragDraws));
  record('負荷', '回転ON停止中の再描画回数/秒', idleDraws === 0, String(idleDraws));
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(box.x + box.width + 200, cy, { steps: 4 }); await page.mouse.up();
  await page.mouse.move(cx, cy); await page.mouse.down(); await page.mouse.move(cx - 80, cy, { steps: 4 }); await page.mouse.up();
  record('操作', '外側リリース後の再ドラッグで固着なし', (await page.getByRole('button', { name: /回転/ }).getAttribute('aria-pressed')) === 'true');
  await page.locator('.rotation-surface').focus();
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  record('操作', '矢印キー・Escで移動モードに戻る', (await page.getByRole('button', { name: /回転/ }).getAttribute('aria-pressed')) === 'false');
  // 回転後のクリック
  await tab(page, '↻ 回転').click(); await page.waitForTimeout(200);
  await page.locator('.rotation-surface').focus(); await page.keyboard.press('ArrowRight'); await page.waitForTimeout(400);
  await tab(page, '全体を表示').click(); await page.waitForTimeout(800);
  let hit = null;
  outer: for (let y = box.y + 120; y < box.y + box.height - 120; y += 20) {
    for (let x = box.x + 120; x < box.x + box.width - 120; x += 20) {
      await page.mouse.move(x, y); await page.waitForTimeout(12);
      if (await page.locator('.map-hover').count()) { hit = { x, y, name: await page.locator('.map-hover strong').innerText() }; break outer; }
    }
  }
  if (hit) {
    await page.mouse.click(hit.x, hit.y); await page.waitForTimeout(1500);
    const center = (await page.locator('.react-flow__node-center').innerText().catch(() => '')).split('\n')[0];
    record('操作', '回転後のクリックで見た目どおりの企業が開く', center === hit.name, `${hit.name} -> ${center}`);
    await page.screenshot({ path: `${outDir}/pc_02_graph_after_rotation_click.png` });
  } else record('操作', '回転後のクリックで見た目どおりの企業が開く', false, 'ホバー対象を見つけられず');

  // カテゴリ全解除 → 0件 → 復帰
  await tab(page, '全体マップ').click(); await page.waitForTimeout(300);
  await tab(page, '↻ 回転中').click().catch(() => {});
  const pills = page.locator('.category-pills button:not([disabled])');
  const n = await pills.count();
  for (let i = 0; i < n; i++) { const b = pills.nth(i); if ((await b.getAttribute('aria-pressed')) === 'true') await b.click(); }
  await page.waitForTimeout(500);
  record('フィルタ', '全解除で空状態を表示', await page.locator('.map-empty').isVisible());
  await page.screenshot({ path: `${outDir}/pc_03_empty.png` });
  await page.locator('.map-empty .reset-button').click(); await page.waitForTimeout(800);
  record('フィルタ', '初期状態に戻すで復帰', !(await page.locator('.map-empty').count()));
  await page.locator('#min-degree').fill('20'); await page.waitForTimeout(500);
  const totals = await page.locator('.map-totals').innerText();
  record('フィルタ', '閾値20で表示線なし件数を表示', /表示線なし/.test(totals) || /表示中の企業/.test(totals), totals.replace(/\n/g, ' '));
  await page.locator('#min-degree').fill('1');
  record('フィルタ', '未収録カテゴリが無効化されている', (await page.locator('.category-pills button[disabled]').count()) >= 1);

  // 検索 → 個別グラフ → 詳細 → 全体（状態復元）
  await page.locator('#map-search').fill('トヨタ');
  await page.getByRole('button', { name: '取引' }).first().click();
  const before = await page.locator('.map-totals').innerText();
  await page.locator('.search-result').first().click(); await page.waitForTimeout(1500);
  await page.locator('.react-flow__edge').first().click({ force: true }).catch(() => {});
  await page.waitForTimeout(800);
  const detailOpen = await page.locator('.detail-panel').count();
  await page.screenshot({ path: `${outDir}/pc_04_graph_detail.png` });
  record('往復', '関係グラフでエッジを選択して詳細を表示', detailOpen > 0);
  await tab(page, '全体マップ').click(); await page.waitForTimeout(300);
  record('往復', '全体マップの検索・カテゴリ・件数を復元', (await page.locator('#map-search').inputValue()) === 'トヨタ' && (await page.locator('.map-totals').innerText()) === before);

  // 関係一覧
  await tab(page, '関係一覧').click(); await page.waitForTimeout(500);
  const q = page.getByLabel('企業名・証券コードで関係を検索');
  await q.fill('この企業は存在しないzzz'); await page.waitForTimeout(400);
  record('一覧', '0件表示', await page.getByRole('status').filter({ hasText: '一致する関係はありません' }).count() > 0);
  await q.fill(''); await page.waitForTimeout(600);
  const rows = await page.locator('tbody tr').count();
  const pageText = await page.locator('.pagination span').innerText();
  record('一覧', '1ページ300件の境界', rows === 300, `${rows}行 / ${pageText}`);
  await page.getByRole('button', { name: '次へ →' }).click(); await page.waitForTimeout(400);
  record('一覧', 'ページ送り', /^2 \//.test(await page.locator('.pagination span').innerText()));
  await q.fill('7203'); await page.waitForTimeout(500);
  record('一覧', '検索変更で1ページ目に戻る', /^1 \//.test(await page.locator('.pagination span').innerText()));
  await page.locator('tbody tr').first().click(); await page.waitForTimeout(1500);
  record('一覧', '詳細を開く', (await page.locator('.view-pane:not(.view-pane-hidden) .detail-panel').count()) > 0);
  await page.screenshot({ path: `${outDir}/pc_05_table_detail.png` });
  await page.getByRole('button', { name: '✕ 閉じる' }).click(); await page.waitForTimeout(200);
  record('一覧', '詳細を閉じる', (await page.locator('.view-pane:not(.view-pane-hidden) .detail-panel').count()) === 0);
  await ctx.close();
}

// ---------------------------------------------------------------- キーボードのみ
{
  const { ctx, page } = await newPage({ width: 1440, height: 900 });
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.locator('.map-canvas canvas').waitFor({ timeout: 120000 }); await page.waitForTimeout(2000);
  const reached = new Set();
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press('Tab');
    const info = await page.evaluate(() => { const el = document.activeElement; return `${el.tagName}:${el.id || el.getAttribute('aria-label') || el.textContent?.trim().slice(0, 12)}`; });
    reached.add(info);
    const visible = await page.evaluate(() => { const el = document.activeElement; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; });
    if (!visible) record('キーボード', `フォーカスが不可視要素に移動: ${info}`, false);
  }
  const list = [...reached];
  record('キーボード', 'Tabで検索欄に到達', list.some((s) => s.includes('map-search')), list.join(', ').slice(0, 300));
  record('キーボード', 'Tabで表示切替タブに到達', list.some((s) => /関係一覧|関係グラフ/.test(s)));
  record('キーボード', 'Tabで回転ボタンに到達', list.some((s) => s.includes('回転')));
  await page.getByRole('button', { name: /回転/ }).focus(); await page.keyboard.press('Enter'); await page.waitForTimeout(200);
  const onSurface = await page.evaluate(() => document.activeElement.classList.contains('rotation-surface'));
  record('キーボード', '回転ONで回転領域にフォーカスが移る', onSurface);
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('Escape'); await page.waitForTimeout(200);
  record('キーボード', 'Escで回転終了', (await page.getByRole('button', { name: /回転/ }).getAttribute('aria-pressed')) === 'false');
  await ctx.close();
}

// ---------------------------------------------------------------- 200% 拡大相当 (720x450)
{
  const { ctx, page } = await newPage({ width: 720, height: 450 });
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.locator('.map-canvas canvas').waitFor({ timeout: 120000 }); await page.waitForTimeout(2000);
  await page.screenshot({ path: `${outDir}/zoom200_map.png` });
  record('200%', '横スクロールなし', await noHScroll(page));
  const reach = await page.evaluate(() => { const el = document.querySelector('#min-degree'); el.scrollIntoView(); const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
  record('200%', '最小関係数スライダーにスクロールで到達', reach);
  await tab(page, '関係一覧').click(); await page.waitForTimeout(500);
  await page.screenshot({ path: `${outDir}/zoom200_table.png` });
  record('200%', '一覧の操作部品が表示される', await page.getByLabel('関係カテゴリ').isVisible() && await page.getByRole('button', { name: '次へ →' }).isVisible());
  await ctx.close();
}

// ---------------------------------------------------------------- タッチ 390x844（エミュレーション）
{
  const { ctx, page, errors } = await newPage({ width: 390, height: 844 }, { hasTouch: true, isMobile: true });
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await page.locator('.map-canvas canvas').waitFor({ timeout: 120000 }); await page.waitForTimeout(3000);
  await page.screenshot({ path: `${outDir}/mobile_01_map.png` });
  record('タッチ', '横スクロールなし', await noHScroll(page));
  const box = await page.locator('.map-canvas canvas').boundingBox();
  // 中央は企業が密集しているため、空いている左下寄りでタップ・スワイプする
  const cx = box.x + 60, cy = box.y + box.height - 90;
  await page.touchscreen.tap(cx, cy); await page.waitForTimeout(400);
  record('タッチ', '空き領域のタップで画面が切り替わらない', await page.locator('.map-view').isVisible());
  // ドラッグ（タッチ）: CDP でスワイプ
  const cdp = await ctx.newCDPSession(page);
  const swipe = async (x1, y1, x2, y2) => {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: x1, y: y1 }] });
    for (let i = 1; i <= 6; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: x1 + (x2 - x1) * i / 6, y: y1 + (y2 - y1) * i / 6 }] });
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  };
  const pageScroll0 = await page.evaluate(() => window.scrollY);
  await swipe(cx, cy, cx + 80, cy + 60); await page.waitForTimeout(300);
  record('タッチ', 'マップ上のスワイプでページがスクロールしない', (await page.evaluate(() => window.scrollY)) === pageScroll0);
  await page.locator('.map-tools button[aria-pressed]').click(); await page.waitForTimeout(300);
  await swipe(cx - 60, cy, cx + 60, cy); await page.waitForTimeout(300);
  record('タッチ', '回転モードのスワイプで固着なし・エラーなし', errors.length === 0 && (await page.getByRole('button', { name: /回転/ }).getAttribute('aria-pressed')) === 'true', errors.join(' / '));
  await page.screenshot({ path: `${outDir}/mobile_02_rotation.png` });
  await page.locator('.map-tools button[aria-pressed]').click();
  await page.getByRole('button', { name: '関係グラフ', exact: true }).click(); await page.waitForTimeout(1500);
  await page.screenshot({ path: `${outDir}/mobile_03_graph.png` });
  record('タッチ', '関係グラフを表示', await page.locator('.react-flow').isVisible());
  await page.getByRole('button', { name: '関係一覧', exact: true }).click(); await page.waitForTimeout(500);
  await page.locator('tbody tr').first().tap(); await page.waitForTimeout(1500);
  record('タッチ', '一覧から詳細を開く', (await page.locator('.view-pane:not(.view-pane-hidden) .detail-panel').count()) > 0);
  await page.screenshot({ path: `${outDir}/mobile_04_table_detail.png` });
  record('タッチ', 'コンソールエラーなし', errors.length === 0, errors.join(' / '));
  await ctx.close();
}

await browser.close();
const summary = { date, commit, url, browser: `Chrome ${version} (headless, Playwright)`, device: `${process.platform} ${process.arch}`, results };
writeFileSync(`${outDir}/results.json`, JSON.stringify(summary, null, 1));
const pass = results.filter((r) => r.ok).length;
const byScenario = {};
for (const r of results) (byScenario[r.scenario] ??= []).push(r);
const md = [
  `# 実操作レビュー結果 ${date}`,
  '',
  `- 対象コミット: \`${commit}\``,
  `- URL: ${url}`,
  `- ブラウザ: ${summary.browser}`,
  `- 端末: ${summary.device}（PC 1440×900 / 200%拡大相当 720×450 / タッチ 390×844 はエミュレーション。実機は未実施）`,
  `- 結果: ${pass}/${results.length} 合格`,
  '',
  '| シナリオ | 項目 | 結果 | 補足 |',
  '| --- | --- | --- | --- |',
  ...results.map((r) => `| ${r.scenario} | ${r.item} | ${r.ok ? '合格' : '**不合格**'} | ${(r.detail || '').replace(/\|/g, '／')} |`),
  '',
  '## スクリーンショット',
  '',
  ...['pc_01_initial', 'pc_02_graph_after_rotation_click', 'pc_03_empty', 'pc_04_graph_detail', 'pc_05_table_detail', 'zoom200_map', 'zoom200_table', 'mobile_01_map', 'mobile_02_rotation', 'mobile_03_graph', 'mobile_04_table_detail'].map((n) => `- ![${n}](${n}.png)`),
  '',
  '## 未実施・注記',
  '',
  '- タッチ操作はヘッドレス Chrome のエミュレーション（hasTouch / CDP のタッチイベント）で、実機ではない。',
  '- 描画負荷は canvas の clearRect 呼び出し回数を再描画回数として計測したもので、CPU 使用率・FPS の実測ではない。',
  '- データの事実精度の評価はこのレビューの対象外（Issue #3 の監査を参照）。',
  '',
].join('\n');
writeFileSync(`${outDir}/REPORT.md`, md);
console.log(`\n${pass}/${results.length} passed -> ${outDir}/results.json, REPORT.md`);
