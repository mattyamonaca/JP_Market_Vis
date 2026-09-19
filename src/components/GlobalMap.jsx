import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { CATEGORY_AVAILABILITY, CATEGORY_COLORS, CATEGORY_JA, CATEGORY_TEXT_COLORS, GLOBAL_GRAPH, INDUSTRY_COLORS, industryColor, searchCompanies } from '../data/graph.js';
import { filterGlobalGraph } from '../data/filterGlobalGraph.js';
import { HOVER_SCALE, LABEL_MIN_DEGREE, insideLayout, nodeRadius, ringWidth, showsLabel } from '../data/nodeShape.js';

// 収録のあるカテゴリだけを初期選択にする（未収録カテゴリは選択できない）
const AVAILABLE_CATEGORIES = Object.keys(CATEGORY_JA).filter((key) => CATEGORY_AVAILABILITY[key]?.listed > 0);

// 全体マップ: 平面（2D）のネットワーク。ノードは白い円に業種色の縁（半径 ∝ √関係数）で、円の中に企業名を書く。線は関係カテゴリ。
// ドラッグで移動、スクロール／ピンチで拡大縮小。ノードの描画と当たり判定は nodeShape.js の同じ半径を使う。
const CORE_MIN_DEGREE = 3; // 「全体を表示」で収める中心部の関係数（孤立した小さな塊は画面外でもよい）
const isCore = (node) => node.degree >= CORE_MIN_DEGREE;
const PAN_STEP = 80; // 矢印キー 1 回で動かす画面上の距離（px）
const LINK_ALPHA = '4d'; // 線の不透明度 0.3（線より円が目立つように）
const linkColor = (link) => `${CATEGORY_COLORS[link.category] ?? '#94a3b8'}${LINK_ALPHA}`;
const noLabel = () => '';

export default function GlobalMap({ onSelectCompany }) {
  const fgRef = useRef(null);
  const wrapRef = useRef(null);
  const fittedRef = useRef(null);
  const hoverRef = useRef(null);
  const tickCount = useRef(0);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [activeCategories, setActiveCategories] = useState(new Set(AVAILABLE_CATEGORIES));
  const [minDegree, setMinDegree] = useState(1);
  const [hoverNode, setHoverNode] = useState(null);
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchCompanies(query, 12), [query]);
  const data = useMemo(() => filterGlobalGraph(GLOBAL_GRAPH, activeCategories, minDegree), [activeCategories, minDegree]);

  // 停止中は描画を休止する（autoPauseRedraw）。ホバーの見た目とサイズ変更はライブラリが再描画の対象にしないため、
  // 休止を 80ms だけ解除して数フレーム描かせる（中心やズームの再設定で代用するとズーム操作中にズームイベントが割り込んでカクつく）
  const [drawing, setDrawing] = useState(false);
  const drawTimer = useRef(null);
  const redraw = useCallback(() => { setDrawing(true); clearTimeout(drawTimer.current); drawTimer.current = setTimeout(() => setDrawing(false), 80); }, []);
  useEffect(() => () => clearTimeout(drawTimer.current), []);
  useEffect(() => {
    const el = wrapRef.current;
    const resize = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    const ro = new ResizeObserver(resize);
    ro.observe(el); resize();
    return () => ro.disconnect();
  }, []);
  // サイズ反映後（ウィンドウ幅の変更・端末の向き変更）に再描画し、休止中に消えたままにしない
  useEffect(() => { redraw(); }, [size, redraw]);
  // 配置計算中は一定ティックごとに全体を収め直す（下の onEngineTick）が、その間にユーザーがズーム・移動したら追従をやめる
  // （追従を続けると操作のたびに視点が引き戻されてガクつく）。データが変わって配置をやり直すときに解除する
  // （ズームライブラリはホイール・ポインターイベントの伝播を止めるので、キャプチャ段階で受け取る）
  const userAdjusted = useRef(false);
  const markAdjusted = () => { userAdjusted.current = true; };
  useEffect(() => { hoverRef.current = null; setHoverNode(null); tickCount.current = 0; userAdjusted.current = false; }, [data]);
  // 離れた小さな塊が全体を押し広げないよう、反発力の届く距離を制限する
  useEffect(() => { fgRef.current?.d3Force('charge')?.distanceMax(500); }, [data]);
  // 収める対象: 中心部（関係数 3 以上）。フィルタ後に低次数のノードしか残らない場合は表示中の全ノード
  const fitFilter = useMemo(() => (data.nodes.some(isCore) ? isCore : undefined), [data]);
  const fit = useCallback((ms = 500) => fgRef.current?.zoomToFit(ms, Math.min(60, size.w * 0.08), fitFilter), [fitFilter, size.w]);
  // 配置計算中は塊が広がり続けるので、一定ティックごとに中心部が収まるよう追従させる（最終位置は onEngineStop で確定）
  const onEngineTick = useCallback(() => { tickCount.current += 1; if (tickCount.current % 25 === 0 && !userAdjusted.current) fit(200); }, [fit]);
  const onEngineStop = useCallback(() => { if (fittedRef.current !== data && data.nodes.length) { fittedRef.current = data; if (!userAdjusted.current) fit(); } }, [data, fit]);
  // 倍率と中心を data-view（倍率,中心x,中心y）に出し、操作記録・確認に使う
  const onZoom = useCallback(({ k, x, y }) => { const el = wrapRef.current; if (el) el.dataset.view = `${k.toFixed(3)},${Math.round(x)},${Math.round(y)}`; }, []);

  const toggleCategory = (key) => setActiveCategories((prev) => {
    const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next;
  });
  const resetFilters = () => { setActiveCategories(new Set(AVAILABLE_CATEGORIES)); setMinDegree(1); };

  // --- 拡大縮小・移動（ボタン・キーボード用。ドラッグ・ホイール・ピンチはライブラリが処理する）
  const zoomBy = (factor) => { const fg = fgRef.current; if (fg) fg.zoom(fg.zoom() * factor, 250); };
  const panBy = (dx, dy) => { const fg = fgRef.current; if (!fg) return; const c = fg.centerAt(), k = fg.zoom(); fg.centerAt(c.x + dx / k, c.y + dy / k, 200); };
  const onKeyDown = (event) => {
    const keys = { ArrowLeft: () => panBy(-PAN_STEP, 0), ArrowRight: () => panBy(PAN_STEP, 0), ArrowUp: () => panBy(0, -PAN_STEP), ArrowDown: () => panBy(0, PAN_STEP),
      '+': () => zoomBy(1.4), '=': () => zoomBy(1.4), '-': () => zoomBy(1 / 1.4), '0': () => fit(), Home: () => fit() };
    const fn = keys[event.key];
    if (fn) { event.preventDefault(); markAdjusted(); fn(); }
  };

  // --- ノードの描画: 白い円に業種色の縁（縁は円の内側に描くので外側＝当たり判定の半径）。ホバー中は縁を太くし、少し拡大して薄く色を敷く。
  // 円の中に企業名を書く（画面上で 11〜20px、長い名前は 2 行。円に収まらない企業は drawLabels で円の上に出す）
  const textWidths = useRef(new Map()); // 企業名の 12px での幅（画面 px）。倍率に関係なく一定なので一度だけ測る
  const widthAt12 = (ctx, name) => {
    let w = textWidths.current.get(name);
    if (w === undefined) { const f = ctx.font; ctx.font = '12px sans-serif'; w = ctx.measureText(name).width; ctx.font = f; textWidths.current.set(name, w); }
    return w;
  };
  // 画面に入っているグラフ座標の範囲（フレームの最初に求め、画面外のノードは描かない。拡大時の描画量を抑える）
  const viewRef = useRef(null);
  const onRenderFramePre = useCallback(() => {
    const fg = fgRef.current; if (!fg) return;
    const tl = fg.screen2GraphCoords(0, 0), br = fg.screen2GraphCoords(size.w, size.h);
    viewRef.current = { x0: tl.x, y0: tl.y, x1: br.x, y1: br.y };
  }, [size]);
  const offScreen = (node, r) => { const v = viewRef.current; return v && (node.x + r < v.x0 || node.x - r > v.x1 || node.y + r < v.y0 || node.y - r > v.y1); };
  const drawNode = useCallback((node, ctx, scale) => {
    const hover = node === hoverRef.current;
    const r = nodeRadius(node.degree) * (hover ? HOVER_SCALE : 1);
    if (offScreen(node, r)) return;
    const color = industryColor(node.industry);
    if (r * scale < 2) {
      // 画面上 2px 未満の円は白い中身も縁も見えないので、縁の色の点として 1 回の塗りで済ませる（全体表示の大半）
      ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
      return;
    }
    const ring = ringWidth(r, hover);
    ctx.beginPath(); ctx.arc(node.x, node.y, r - ring / 2, 0, Math.PI * 2);
    ctx.fillStyle = hover ? `${color}1f` : '#ffffff'; ctx.fill();
    ctx.lineWidth = ring; ctx.strokeStyle = color; ctx.stroke();
  }, []);
  // 円の中に名前が入らない企業のラベルは、全ノードを描いた後に別パスで円の上に重ねる（後から描かれる円に隠れない）。画面上で一定の大きさ（12px）、白の下地付き。
  // 画面内の候補を関係数の多い順（ホバー中を最優先）に置き、先に置いたラベルと重なるものは描かない（縮小時にハブのラベルが重ならない）
  const dataRef = useRef(data); dataRef.current = data;
  const drawLabels = useCallback((ctx, scale) => {
    const fg = fgRef.current; if (!fg) return;
    const font = 12 / scale, pad = 4 / scale, hoverNode = hoverRef.current;
    const tl = fg.screen2GraphCoords(0, 0), br = fg.screen2GraphCoords(size.w, size.h);
    const candidates = [], placed = []; // placed: 名前を書いた円と、置いたラベルの矩形（上ラベルはこれらと重ねない）
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#0f172a';
    for (const node of dataRef.current.nodes) {
      if (!Number.isFinite(node.x) || node.x < tl.x || node.x > br.x || node.y < tl.y || node.y > br.y) continue;
      const hover = node === hoverNode;
      // 円の中に書く企業名の配置（null なら入らない）。画面内のノードだけ計算する
      const inside = insideLayout(nodeRadius(node.degree) * (hover ? HOVER_SCALE : 1) * scale, node.name, (text) => widthAt12(ctx, text));
      if (inside) {
        ctx.font = `${hover ? 600 : 500} ${inside.font / scale}px sans-serif`;
        const step = inside.font * 1.3 / scale, y0 = node.y - step * (inside.lines.length - 1) / 2;
        inside.lines.forEach((line, i) => ctx.fillText(line, node.x, y0 + step * i));
        const r = nodeRadius(node.degree) * (hover ? HOVER_SCALE : 1);
        placed.push({ x0: node.x - r, x1: node.x + r, y0: node.y - r, y1: node.y + r });
      } else if (showsLabel(node.degree, scale, hover)) candidates.push(node);
    }
    candidates.sort((a, b) => (b === hoverNode) - (a === hoverNode) || b.degree - a.degree);
    ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
    for (const node of candidates) {
      const hover = node === hoverNode;
      const r = nodeRadius(node.degree) * (hover ? HOVER_SCALE : 1);
      ctx.font = `${hover || node.degree >= LABEL_MIN_DEGREE ? 600 : 400} ${font}px sans-serif`;
      const y = node.y - r - 3 / scale;
      const w = ctx.measureText(node.name).width + pad * 2;
      const box = { x0: node.x - w / 2, x1: node.x + w / 2, y0: y - font - pad / 2, y1: y + pad / 2 };
      if (placed.some((b) => box.x0 < b.x1 && b.x0 < box.x1 && box.y0 < b.y1 && b.y0 < box.y1)) continue;
      placed.push(box);
      ctx.fillStyle = 'rgba(255, 255, 255, .85)'; ctx.fillRect(box.x0, box.y0, w, font + pad);
      ctx.fillStyle = '#0f172a'; ctx.fillText(node.name, node.x, y);
    }
  }, [size]);
  // 当たり判定は描いた円と同じ半径（ホバー中は拡大後）
  const paintPointerArea = useCallback((node, color, ctx) => {
    const r = nodeRadius(node.degree) * (node === hoverRef.current ? HOVER_SCALE : 1);
    if (offScreen(node, r)) return;
    ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill();
  }, []);
  const onNodeHover = useCallback((node) => {
    hoverRef.current = node || null;
    setHoverNode(node || null);
    const el = wrapRef.current, fg = fgRef.current;
    if (el) {
      el.style.cursor = node ? 'pointer' : 'grab';
      el.dataset.hover = node ? node.id : '';
      // ホバー中のノードの画面上の中心と半径（見た目と当たり判定の一致確認用）
      if (node && fg) {
        const p = fg.graph2ScreenCoords(node.x, node.y);
        el.dataset.hoverCenter = `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
        el.dataset.hoverRadius = (nodeRadius(node.degree) * HOVER_SCALE * fg.zoom()).toFixed(1);
      } else { delete el.dataset.hoverCenter; delete el.dataset.hoverRadius; }
    }
    redraw();
  }, [redraw]);
  // クリック（ドラッグせずに離した場合だけライブラリが発火する）で見た目どおりの企業を開く
  const onNodeClick = useCallback((node) => onSelectCompany(node.id), [onSelectCompany]);

  return (
    <div className="map-view">
      <aside className="map-sidebar" aria-label="マップの検索とフィルタ">
        <h2>企業のつながりを探る</h2>
        <p>資本・取引・提携から、日本の企業ネットワークを俯瞰。</p>
        <div className="map-totals" aria-live="polite">
          <div><strong>{data.nodes.length.toLocaleString()}</strong><span>表示中の企業{data.isolated > 0 && <><br />うち表示線なし {data.isolated.toLocaleString()}社</>}</span></div>
          <div><strong>{data.links.length.toLocaleString()}</strong><span>表示中の関係<br />上場企業間 {GLOBAL_GRAPH.links.length.toLocaleString()}件中</span></div>
        </div>
        <section className="control-section">
          <label htmlFor="map-search">企業を検索</label>
          <input id="map-search" className="search-input" placeholder="企業名・証券コード" value={query} onChange={(e) => setQuery(e.target.value)} />
          {query.trim() && <div className="search-results" aria-live="polite">
            {results.map(({ code, company }) => <button className="search-result" key={code} onClick={() => onSelectCompany(code)}>{company.name}<br /><small>{code} · 関係グラフを開く ↗</small></button>)}
            {!results.length && <p>該当する企業がありません</p>}
          </div>}
        </section>
        <section className="control-section">
          <h3>関係のカテゴリ</h3>
          <div className="category-pills">{Object.entries(CATEGORY_JA).map(([key, label]) => {
            const avail = CATEGORY_AVAILABILITY[key] ?? { total: 0, listed: 0 };
            const unavailable = avail.listed === 0;
            const active = activeCategories.has(key) && !unavailable, color = CATEGORY_TEXT_COLORS[key];
            const title = unavailable
              ? (avail.total === 0 ? 'このカテゴリは現在のデータに収録されていません（関係がないことを意味しません）' : '上場企業同士の関係が収録されていないため全体マップでは選べません')
              : `上場企業間 ${avail.listed.toLocaleString()}件（全体 ${avail.total.toLocaleString()}件）`;
            return <button key={key} aria-pressed={active} aria-disabled={unavailable} disabled={unavailable} title={title} onClick={() => toggleCategory(key)} style={{ color: active ? color : 'var(--text-2)', border: `1px solid ${active ? color : 'var(--border-strong)'}`, background: active ? color + '14' : 'var(--bg)', opacity: unavailable ? 0.55 : 1, cursor: unavailable ? 'not-allowed' : 'pointer' }}>{label}<small>{unavailable ? '未収録' : avail.listed.toLocaleString()}</small></button>;
          })}</div>
          {AVAILABLE_CATEGORIES.length < Object.keys(CATEGORY_JA).length && <p className="control-note">「未収録」は収集していないカテゴリです。関係がないことを意味しません。</p>}
        </section>
        <section className="control-section">
          <label className="range-caption" htmlFor="min-degree">最小関係数 <strong>{minDegree}</strong></label>
          <input id="min-degree" type="range" min="1" max="20" value={minDegree} onChange={(e) => setMinDegree(Number(e.target.value))} />
          <p>選択カテゴリで、その企業が上場企業と持つ関係数（非表示の企業との関係を含む）が {minDegree} 以上の企業を表示します。線は表示中の企業同士の関係だけなので、相手が非表示の企業は「表示線なし」になります。円の大きさも同じ関係数です。</p>
          {(data.nodes.length === 0 || activeCategories.size === 0) && <button type="button" className="reset-button" onClick={resetFilters}>カテゴリと最小関係数を初期状態に戻す</button>}
        </section>
        <details className="legend-details" open>
          <summary>業種の凡例</summary>
          <div className="legend">{Object.entries(INDUSTRY_COLORS).map(([name, color]) => <span key={name}><i style={{ borderColor: color }} />{name}</span>)}</div>
        </details>
      </aside>
      <div ref={wrapRef} className="map-canvas" tabIndex={0} role="group"
        aria-label="上場企業間ネットワーク。ドラッグで移動、スクロールで拡大縮小。矢印キーで移動、＋／−で拡大縮小、0 で全体を表示できます。企業をクリックすると関係グラフを開きます。"
        onKeyDown={onKeyDown} onWheelCapture={markAdjusted} onPointerDownCapture={markAdjusted} onTouchStartCapture={markAdjusted}>
        <div className="map-caption"><strong>上場企業間ネットワーク</strong><br />縁の色：業種 ／ 円の大きさ：関係数<br />ドラッグで移動 · スクロール／ピンチで拡大縮小 · 企業を選択して詳細へ</div>
        <ForceGraph2D ref={fgRef} width={size.w} height={size.h} graphData={data}
          backgroundColor="#ffffff" nodeId="id" nodeLabel={noLabel}
          nodeCanvasObject={drawNode} nodePointerAreaPaint={paintPointerArea}
          linkColor={linkColor} linkWidth={0.8}
          warmupTicks={50} cooldownTicks={100}
          enableNodeDrag={false} minZoom={0.05} maxZoom={20} autoPauseRedraw={!drawing}
          onRenderFramePre={onRenderFramePre} onRenderFramePost={drawLabels}
          onEngineTick={onEngineTick} onEngineStop={onEngineStop} onZoom={onZoom}
          onNodeHover={onNodeHover} onNodeClick={onNodeClick}
        />
        {!data.nodes.length && <div className="map-empty" role="status"><strong>表示できる企業がありません</strong><span>カテゴリを選択するか、最小関係数を下げてください。</span><button type="button" className="reset-button" style={{ pointerEvents: 'auto' }} onClick={resetFilters}>初期状態に戻す</button></div>}
        {hoverNode && <div className="map-hover"><strong>{hoverNode.name}</strong><small>{hoverNode.id} · {hoverNode.industry}</small><small>選択カテゴリで上場企業と {hoverNode.degree}関係（非表示の相手を含む）</small></div>}
        <div className="map-tools"><button onClick={() => zoomBy(1.4)} aria-label="拡大">＋</button><button onClick={() => zoomBy(1 / 1.4)} aria-label="縮小">−</button><button onClick={() => fit()}>全体を表示</button></div>
      </div>
    </div>
  );
}
