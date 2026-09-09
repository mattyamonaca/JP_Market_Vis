import React, { useMemo, useRef, useState, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { CATEGORY_AVAILABILITY, CATEGORY_COLORS, CATEGORY_JA, GLOBAL_GRAPH, INDUSTRY_COLORS, industryColor, searchCompanies } from '../data/graph.js';

// 収録のあるカテゴリだけを初期選択にする（未収録カテゴリは選択できない）
const AVAILABLE_CATEGORIES = Object.keys(CATEGORY_JA).filter((key) => CATEGORY_AVAILABILITY[key]?.listed > 0);
import { rotateNodes } from '../data/rotateNodes.js';
import { filterGlobalGraph } from '../data/filterGlobalGraph.js';

export default function GlobalMap({ onSelectCompany }) {
  const fgRef = useRef(null);
  const wrapRef = useRef(null);
  const fittedRef = useRef(null);
  const rotationDrag = useRef(null);
  const [rotationMode, setRotationMode] = useState(false);
  // 回転モード中でも、ドラッグ・キー操作の間だけ再描画を回し、停止中は休止する（Issue #8）
  const [interacting, setInteracting] = useState(false);
  const idleTimer = useRef(null);
  const wake = (ms = 400) => {
    setInteracting(true);
    clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => setInteracting(false), ms);
  };
  useEffect(() => () => clearTimeout(idleTimer.current), []);
  // 回転用オーバーレイのホイールを拡大縮小へ転送（React の onWheel は passive なので native で登録）
  const surfaceRef = useRef(null);
  useEffect(() => {
    const el = surfaceRef.current;
    if (!rotationMode || !el) return undefined;
    const onWheel = (event) => {
      event.preventDefault();
      const fg = fgRef.current;
      if (fg) fg.zoom(fg.zoom() * (event.deltaY < 0 ? 1.15 : 1 / 1.15), 150);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, [rotationMode]);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [activeCategories, setActiveCategories] = useState(new Set(AVAILABLE_CATEGORIES));
  const [minDegree, setMinDegree] = useState(1);
  const [hoverNode, setHoverNode] = useState(null);
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchCompanies(query, 12), [query]);
  const data = useMemo(() => filterGlobalGraph(GLOBAL_GRAPH, activeCategories, minDegree), [activeCategories, minDegree]);
  useEffect(() => {
    const el = wrapRef.current;
    const resize = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    const ro = new ResizeObserver(resize);
    ro.observe(el); resize();
    return () => ro.disconnect();
  }, []);
  useEffect(() => { setHoverNode(null); rotationDrag.current = null; }, [data, rotationMode]);
  const toggleCategory = (key) => setActiveCategories((prev) => {
    const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next;
  });
  const resetFilters = () => { setActiveCategories(new Set(AVAILABLE_CATEGORIES)); setMinDegree(1); };
  const nodeSize = (node) => Math.max(2, Math.sqrt(node.degree) * 1.4);
  const fit = () => fgRef.current?.zoomToFit(500, Math.min(60, size.w * .1));
  const zoomBy = (factor) => fgRef.current?.zoom(fgRef.current.zoom() * factor, 250);
  // 回転用オーバーレイ上の座標から、見た目どおりのノードを探す（回転後の位置で判定）
  const nodeAt = (clientX, clientY) => {
    const fg = fgRef.current;
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!fg || !rect) return null;
    const p = fg.screen2GraphCoords(clientX - rect.left, clientY - rect.top);
    const scale = fg.zoom();
    let best = null;
    let bestD = Infinity;
    for (const node of data.nodes) {
      if (!Number.isFinite(node.x)) continue;
      const d = Math.hypot(node.x - p.x, node.y - p.y);
      const r = nodeSize(node) + 6 / scale;
      if (d <= r && d < bestD) { best = node; bestD = d; }
    }
    return best;
  };
  const CLICK_SLOP = 5;
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
            const active = activeCategories.has(key) && !unavailable, color = CATEGORY_COLORS[key];
            const title = unavailable
              ? (avail.total === 0 ? 'このカテゴリは現在のデータに収録されていません（関係がないことを意味しません）' : '上場企業同士の関係が収録されていないため全体マップでは選べません')
              : `上場企業間 ${avail.listed.toLocaleString()}件（全体 ${avail.total.toLocaleString()}件）`;
            return <button key={key} aria-pressed={active} aria-disabled={unavailable} disabled={unavailable} title={title} onClick={() => toggleCategory(key)} style={{ color: active ? color : '#94a3b8', border: `1px solid ${active ? color + '88' : '#334155'}`, background: active ? color + '18' : 'transparent', opacity: unavailable ? 0.55 : 1, cursor: unavailable ? 'not-allowed' : 'pointer' }}>{label}<small>{unavailable ? '未収録' : avail.listed.toLocaleString()}</small></button>;
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
          <div className="legend">{Object.entries(INDUSTRY_COLORS).map(([name, color]) => <span key={name}><i style={{ background: color }} />{name}</span>)}</div>
        </details>
      </aside>
      <div ref={wrapRef} className="map-canvas" role="region" aria-label="上場企業間ネットワーク。企業検索からも各社の関係を確認できます。">
        <div className="map-caption"><strong>上場企業間ネットワーク</strong><br />色：業種 ／ 円の大きさ：関係数<br />{rotationMode ? '左右にドラッグして回転 · スクロール・＋/−で拡大縮小 · 企業をクリックで詳細へ · Escで移動モード' : 'ドラッグで移動 · スクロールで拡大 · 企業を選択して詳細へ'}</div>
        <ForceGraph2D ref={fgRef} width={size.w} height={size.h} graphData={data}
          backgroundColor="#0b1220" nodeId="id" nodeRelSize={1}
          nodeVal={(n) => nodeSize(n) ** 2 / 4} nodeColor={(n) => industryColor(n.industry)} nodeLabel={() => ''}
          linkColor={(l) => `${CATEGORY_COLORS[l.category] ?? '#475569'}55`} linkWidth={0.6}
          warmupTicks={50} cooldownTicks={rotationMode ? 0 : 90}
          autoPauseRedraw={!(rotationMode && interacting)}
          enableNodeDrag={!rotationMode} enablePanInteraction={!rotationMode}
          onEngineStop={() => { if (fittedRef.current !== data && data.nodes.length) { fittedRef.current = data; fit(); } }}
          onNodeHover={(n) => { setHoverNode(n || null); if (wrapRef.current) wrapRef.current.style.cursor = n ? 'pointer' : 'grab'; }}
          onNodeClick={(n) => onSelectCompany(n.id)}
          nodeCanvasObjectMode={() => 'after'}
          nodeCanvasObject={(node, ctx, scale) => {
            if (node !== hoverNode && !(scale > 2 && node.degree >= 8) && node.degree < 110) return;
            ctx.font = `${12 / scale}px sans-serif`; ctx.textAlign = 'center';
            ctx.fillStyle = '#dce8f6'; ctx.fillText(node.name, node.x, node.y - nodeSize(node) - 4 / scale);
          }}
        />
        {rotationMode && <div className="rotation-surface"
          tabIndex={0} role="group" aria-label="ドラッグでマップ全体を回転。左右の矢印キーでも回転できます。企業をクリックすると詳細を開きます。"
          ref={surfaceRef}
          onPointerDown={(event) => {
            if (!event.isPrimary || event.button !== 0) return;
            event.preventDefault();
            event.currentTarget.focus();
            event.currentTarget.setPointerCapture(event.pointerId);
            rotationDrag.current = { id: event.pointerId, x: event.clientX, startX: event.clientX, startY: event.clientY, moved: false };
            wake(1000);
          }}
          onPointerMove={(event) => {
            const drag = rotationDrag.current;
            if (!drag || drag.id !== event.pointerId) {
              // ドラッグしていない間は通常モードと同じくホバーで企業名を表示
              if (!drag && event.pointerType !== 'touch') {
                const node = nodeAt(event.clientX, event.clientY);
                if (node !== hoverNode) { setHoverNode(node); wake(300); }
                event.currentTarget.style.cursor = node ? 'pointer' : 'ew-resize';
              }
              return;
            }
            if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < CLICK_SLOP) return;
            if (hoverNode) setHoverNode(null);
            drag.moved = true;
            rotateNodes(data.nodes, (event.clientX - drag.x) * Math.PI / 360);
            drag.x = event.clientX;
            wake(600);
          }}
          onPointerUp={(event) => {
            const drag = rotationDrag.current;
            if (drag?.id !== event.pointerId) return;
            rotationDrag.current = null;
            if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
            wake(300);
            // 動かしていなければクリック扱い: 見た目の位置にある企業を開く（ドラッグ終了では開かない）
            if (!drag.moved) {
              const node = nodeAt(event.clientX, event.clientY);
              if (node) onSelectCompany(node.id);
            }
          }}
          onPointerCancel={() => { rotationDrag.current = null; wake(300); }}
          onLostPointerCapture={() => { rotationDrag.current = null; }}
          onKeyDown={(event) => {
            if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
              event.preventDefault();
              rotateNodes(data.nodes, (event.key === 'ArrowRight' ? 1 : -1) * Math.PI / 12);
              wake(500);
            }
            if (event.key === '+' || event.key === '=') zoomBy(1.4);
            if (event.key === '-') zoomBy(1 / 1.4);
            if (event.key === 'Escape') setRotationMode(false);
          }}
        />}
        {!data.nodes.length && <div className="map-empty" role="status"><strong>表示できる企業がありません</strong><span>カテゴリを選択するか、最小関係数を下げてください。</span><button type="button" className="reset-button" style={{ pointerEvents: 'auto' }} onClick={resetFilters}>初期状態に戻す</button></div>}
        {hoverNode && <div className="map-hover"><strong>{hoverNode.name}</strong><small>{hoverNode.id} · {hoverNode.industry}</small><small>選択カテゴリで上場企業と {hoverNode.degree}関係（非表示の相手を含む）</small></div>}
        <div className="map-tools"><button aria-pressed={rotationMode} onClick={() => { setRotationMode((active) => !active); wake(300); }}>{rotationMode ? '↻ 回転中' : '↻ 回転'}</button><button onClick={() => zoomBy(1.4)} aria-label="拡大">＋</button><button onClick={() => zoomBy(1 / 1.4)} aria-label="縮小">−</button><button onClick={fit}>全体を表示</button></div>
      </div>
    </div>
  );
}
