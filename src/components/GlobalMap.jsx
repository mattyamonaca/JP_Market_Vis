import React, { useMemo, useRef, useState, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { CATEGORY_COLORS, CATEGORY_JA, GLOBAL_GRAPH, INDUSTRY_COLORS, industryColor, searchCompanies } from '../data/graph.js';
import { filterGlobalGraph } from '../data/filterGlobalGraph.js';

export default function GlobalMap({ onSelectCompany }) {
  const fgRef = useRef(null);
  const wrapRef = useRef(null);
  const fittedRef = useRef(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [activeCategories, setActiveCategories] = useState(new Set(Object.keys(CATEGORY_JA)));
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
  useEffect(() => { setHoverNode(null); }, [data]);
  const toggleCategory = (key) => setActiveCategories((prev) => {
    const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next;
  });
  const nodeSize = (node) => Math.max(2, Math.sqrt(node.degree) * 1.4);
  const fit = () => fgRef.current?.zoomToFit(500, Math.min(60, size.w * .1));
  return (
    <div className="map-view">
      <aside className="map-sidebar" aria-label="マップの検索とフィルタ">
        <h2>企業のつながりを探る</h2>
        <p>資本・取引・提携から、日本の企業ネットワークを俯瞰。</p>
        <div className="map-totals" aria-live="polite">
          <div><strong>{data.nodes.length.toLocaleString()}</strong><span>表示中の企業</span></div>
          <div><strong>{data.links.length.toLocaleString()}</strong><span>表示中の関係</span></div>
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
            const active = activeCategories.has(key), color = CATEGORY_COLORS[key];
            return <button key={key} aria-pressed={active} onClick={() => toggleCategory(key)} style={{ color: active ? color : '#94a3b8', border: `1px solid ${active ? color + '88' : '#334155'}`, background: active ? color + '18' : 'transparent' }}>{label}</button>;
          })}</div>
        </section>
        <section className="control-section">
          <label className="range-caption" htmlFor="min-degree">最小関係数 <strong>{minDegree}</strong></label>
          <input id="min-degree" type="range" min="1" max="20" value={minDegree} onChange={(e) => setMinDegree(Number(e.target.value))} />
          <p>選択カテゴリ内の関係数で絞り込みます。</p>
        </section>
        <details className="legend-details" open>
          <summary>業種の凡例</summary>
          <div className="legend">{Object.entries(INDUSTRY_COLORS).map(([name, color]) => <span key={name}><i style={{ background: color }} />{name}</span>)}</div>
        </details>
      </aside>
      <div ref={wrapRef} className="map-canvas" role="region" aria-label="上場企業間ネットワーク。企業検索からも各社の関係を確認できます。">
        <div className="map-caption"><strong>上場企業間ネットワーク</strong><br />色：業種 ／ 円の大きさ：関係数<br />ドラッグで移動 · スクロールで拡大 · 企業を選択して詳細へ</div>
        <ForceGraph2D ref={fgRef} width={size.w} height={size.h} graphData={data}
          backgroundColor="#0b1220" nodeId="id" nodeRelSize={1}
          nodeVal={(n) => nodeSize(n) ** 2 / 4} nodeColor={(n) => industryColor(n.industry)} nodeLabel={() => ''}
          linkColor={(l) => `${CATEGORY_COLORS[l.category] ?? '#475569'}55`} linkWidth={0.6}
          warmupTicks={50} cooldownTicks={90}
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
        {!data.nodes.length && <div className="map-empty" role="status"><strong>表示できる企業がありません</strong><span>カテゴリを選択するか、最小関係数を下げてください。</span></div>}
        {hoverNode && <div className="map-hover"><strong>{hoverNode.name}</strong><small>{hoverNode.id} · {hoverNode.industry}</small><small>選択カテゴリ内 {hoverNode.degree}関係</small></div>}
        <div className="map-tools"><button onClick={() => fgRef.current?.zoom(fgRef.current.zoom() * 1.4, 250)} aria-label="拡大">＋</button><button onClick={() => fgRef.current?.zoom(fgRef.current.zoom() / 1.4, 250)} aria-label="縮小">−</button><button onClick={fit}>全体を表示</button></div>
      </div>
    </div>
  );
}
