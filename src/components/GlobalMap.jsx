import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ForceGraph3D from 'react-force-graph-3d';
import { CATEGORY_AVAILABILITY, CATEGORY_COLORS, CATEGORY_JA, CATEGORY_TEXT_COLORS, GLOBAL_GRAPH, INDUSTRY_COLORS, industryColor, searchCompanies } from '../data/graph.js';
import { filterGlobalGraph } from '../data/filterGlobalGraph.js';

// 収録のあるカテゴリだけを初期選択にする（未収録カテゴリは選択できない）
const AVAILABLE_CATEGORIES = Object.keys(CATEGORY_JA).filter((key) => CATEGORY_AVAILABILITY[key]?.listed > 0);

// 全体マップ（Issue #22）: ノードを 3D 空間に配置し、ドラッグでカメラを回す。
// 球の半径 ∝ 関係数の立方根（nodeRelSize × cbrt(nodeVal)）。色は業種。線は関係カテゴリ。
// アクセサは参照が変わるとライブラリがオブジェクトを作り直すため、モジュール定数として固定する。
const NODE_REL_SIZE = 8;
const LABEL_MIN_DEGREE = 110; // 主要ハブだけ常時ラベル（HTML を球の画面位置に重ねる）。その他はホバーで表示
const CORE_MIN_DEGREE = 3; // 視点リセット・初期表示で収める「中心部」の関係数（孤立した小さな塊は画面外でもよい）
const nodeVal = (node) => node.degree * 2;
const nodeColor = (node) => industryColor(node.industry);
const linkColor = (link) => CATEGORY_COLORS[link.category] ?? '#94a3b8';
const noLabel = () => '';
const radiusOf = (node) => Math.cbrt(nodeVal(node)) * NODE_REL_SIZE;
const isCore = (node) => node.degree >= CORE_MIN_DEGREE;
const ORBIT_STEP = Math.PI / 12; // 矢印キー 1 回で 15°
const CLAMP = 0.05;

export default function GlobalMap({ onSelectCompany }) {
  const fgRef = useRef(null);
  const wrapRef = useRef(null);
  const fittedRef = useRef(null);
  const engineRunning = useRef(true);
  const paused = useRef(false);
  const idleTimer = useRef(null);
  const tickCount = useRef(0);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const [activeCategories, setActiveCategories] = useState(new Set(AVAILABLE_CATEGORIES));
  const [minDegree, setMinDegree] = useState(1);
  const [hoverNode, setHoverNode] = useState(null);
  const labelsRef = useRef(null);
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchCompanies(query, 12), [query]);
  const data = useMemo(() => filterGlobalGraph(GLOBAL_GRAPH, activeCategories, minDegree), [activeCategories, minDegree]);

  // 描画は操作中と力学シミュレーション中だけ回し、停止中は休止する（Issue #8 の方針を 3D でも維持）。
  // 休止中はホバー判定も止まるため、ポインターが動いたら再開する
  const pause = () => { const fg = fgRef.current; if (fg && !paused.current) { fg.pauseAnimation(); paused.current = true; } };
  const resume = () => { const fg = fgRef.current; if (fg && paused.current) { fg.resumeAnimation(); paused.current = false; } };
  const wake = useCallback((ms = 1200) => {
    resume();
    clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => { if (!engineRunning.current) pause(); }, ms);
  }, []);
  useEffect(() => () => clearTimeout(idleTimer.current), []);

  // リサイズ（ウィンドウ幅の変更・端末の向き変更）: サイズ反映後のフレームを描いてから休止する（休止中に消えたままにしない）
  useEffect(() => {
    const el = wrapRef.current;
    const resize = () => { setSize({ w: el.clientWidth, h: el.clientHeight }); wake(800); };
    const ro = new ResizeObserver(resize);
    ro.observe(el); resize();
    return () => ro.disconnect();
  }, [wake]);
  // データが変わったらシミュレーションが動くので描画を再開し、ホバーを消す
  useEffect(() => { setHoverNode(null); engineRunning.current = true; tickCount.current = 0; resume(); }, [data]);
  // 主要ハブのラベルを、球の画面座標に合わせて HTML で重ねる（カメラ移動・シミュレーションのたびに位置を更新）
  const hubs = useMemo(() => data.nodes.filter((n) => n.degree >= LABEL_MIN_DEGREE), [data]);
  const updateLabels = useCallback(() => {
    const fg = fgRef.current, layer = labelsRef.current;
    if (!fg || !layer) return;
    const { w, h } = { w: layer.clientWidth, h: layer.clientHeight };
    // カメラの背後にあるノードは映らないので、注視方向との内積で前方にあるものだけ描く
    const cam = fg.cameraPosition(), t = fg.controls()?.target ?? { x: 0, y: 0, z: 0 };
    const fwd = { x: t.x - cam.x, y: t.y - cam.y, z: t.z - cam.z };
    for (const span of layer.children) {
      const node = hubs[Number(span.dataset.i)];
      if (!node || !Number.isFinite(node.x)) { span.style.visibility = 'hidden'; continue; }
      const inFront = (node.x - cam.x) * fwd.x + (node.y - cam.y) * fwd.y + (node.z - cam.z) * fwd.z > 0;
      const p = fg.graph2ScreenCoords(node.x, node.y + radiusOf(node), node.z);
      const visible = inFront && p.x > -40 && p.x < w + 40 && p.y > -20 && p.y < h + 20;
      span.style.visibility = visible ? 'visible' : 'hidden';
      if (visible) span.style.transform = `translate(-50%, -100%) translate(${p.x.toFixed(1)}px, ${(p.y - 4).toFixed(1)}px)`;
    }
  }, [hubs]);
  useEffect(() => { updateLabels(); }, [updateLabels, size]);
  // カメラの向きを data-camera（注視点からの相対位置）に出し、操作記録・確認に使う。ラベル位置もカメラ移動で更新する
  useEffect(() => {
    const fg = fgRef.current;
    const controls = fg?.controls();
    const el = wrapRef.current;
    if (!fg || !controls || !el) return undefined;
    controls.minDistance = 120; // 表示が 2 社だけのときなどに球の内側まで寄らない
    let timer = null;
    const update = () => {
      timer = null;
      const c = fg.cameraPosition(), t = controls.target;
      el.dataset.camera = [c.x - t.x, c.y - t.y, c.z - t.z].map((v) => Math.round(v)).join(',');
    };
    const onChange = () => { updateLabels(); if (!timer) timer = setTimeout(update, 80); };
    controls.addEventListener('change', onChange);
    update();
    return () => { clearTimeout(timer); controls.removeEventListener('change', onChange); };
  }, [updateLabels]);
  // 離れた小さな塊が全体を押し広げないよう、反発力の届く距離を制限する
  useEffect(() => { fgRef.current?.d3Force('charge')?.distanceMax(700); }, [data]);
  // 収める対象: 中心部（関係数 3 以上）。フィルタ後に低次数のノードしか残らない場合は表示中の全ノードに切り替える
  const fitFilter = useMemo(() => (data.nodes.some(isCore) ? isCore : undefined), [data]);
  const fit = useCallback((ms = 600) => { fgRef.current?.zoomToFit(ms, Math.min(60, size.w * 0.08), fitFilter); wake(ms + 800); }, [fitFilter, size.w, wake]);
  // 配置計算中は塊が広がり続けるので、一定ティックごとに中心部が収まるようカメラを追従させる（最終位置は onEngineStop で確定）
  const onEngineTick = useCallback(() => {
    tickCount.current += 1;
    if (tickCount.current % 25 === 0) fgRef.current?.zoomToFit(300, Math.min(60, size.w * 0.08), fitFilter);
    updateLabels();
  }, [updateLabels, size.w, fitFilter]);

  const toggleCategory = (key) => setActiveCategories((prev) => {
    const next = new Set(prev); if (next.has(key)) next.delete(key); else next.add(key); return next;
  });
  const resetFilters = () => { setActiveCategories(new Set(AVAILABLE_CATEGORIES)); setMinDegree(1); };

  // --- カメラ操作（ボタン・キーボード用。ドラッグ・ホイール・ピンチは OrbitControls が処理する）
  const target = () => { const t = fgRef.current?.controls()?.target; return t ? { x: t.x, y: t.y, z: t.z } : { x: 0, y: 0, z: 0 }; };
  const zoomBy = (factor) => {
    const fg = fgRef.current; if (!fg) return;
    const c = fg.cameraPosition(), t = target();
    fg.cameraPosition({ x: t.x + (c.x - t.x) / factor, y: t.y + (c.y - t.y) / factor, z: t.z + (c.z - t.z) / factor }, t, 250);
    wake();
  };
  const orbit = (dAzimuth, dPolar) => {
    const fg = fgRef.current; if (!fg) return;
    const c = fg.cameraPosition(), t = target();
    const dx = c.x - t.x, dy = c.y - t.y, dz = c.z - t.z;
    const r = Math.hypot(dx, dy, dz) || 1;
    const theta = Math.atan2(dx, dz) + dAzimuth;
    const phi = Math.min(Math.PI - CLAMP, Math.max(CLAMP, Math.acos(Math.min(1, Math.max(-1, dy / r))) + dPolar));
    fg.cameraPosition({ x: t.x + r * Math.sin(phi) * Math.sin(theta), y: t.y + r * Math.cos(phi), z: t.z + r * Math.sin(phi) * Math.cos(theta) }, t, 200);
    wake();
  };
  // 視点リセット: 正面（z 軸上）に戻してから全体が入る距離にする
  const resetView = () => {
    const fg = fgRef.current; if (!fg) return;
    const c = fg.cameraPosition(), t = target();
    const r = Math.hypot(c.x - t.x, c.y - t.y, c.z - t.z) || 1000;
    fg.cameraPosition({ x: 0, y: 0, z: r }, { x: 0, y: 0, z: 0 }, 400);
    setTimeout(() => fit(500), 420);
    wake(2000);
  };
  const onKeyDown = (event) => {
    const keys = { ArrowLeft: () => orbit(-ORBIT_STEP, 0), ArrowRight: () => orbit(ORBIT_STEP, 0), ArrowUp: () => orbit(0, -ORBIT_STEP / 2), ArrowDown: () => orbit(0, ORBIT_STEP / 2),
      '+': () => zoomBy(1.4), '=': () => zoomBy(1.4), '-': () => zoomBy(1 / 1.4), '0': resetView, Home: resetView };
    const fn = keys[event.key];
    if (fn) { event.preventDefault(); fn(); }
  };

  const onNodeHover = useCallback((node) => {
    setHoverNode(node || null);
    if (wrapRef.current) wrapRef.current.style.cursor = node ? 'pointer' : 'grab';
  }, []);
  // クリック（ドラッグせずに離した場合だけライブラリが発火する）で見た目どおりの企業を開く
  const onNodeClick = useCallback((node) => onSelectCompany(node.id), [onSelectCompany]);
  const onEngineStop = useCallback(() => {
    engineRunning.current = false;
    const el = wrapRef.current;
    if (el && data.nodes.length) {
      const zs = data.nodes.map((n) => n.z).filter(Number.isFinite);
      el.dataset.depth = zs.length ? String(Math.round(Math.max(...zs) - Math.min(...zs))) : '0';
    }
    if (fittedRef.current !== data && data.nodes.length) { fittedRef.current = data; fit(); } else wake(800);
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

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
          <p>選択カテゴリで、その企業が上場企業と持つ関係数（非表示の企業との関係を含む）が {minDegree} 以上の企業を表示します。線は表示中の企業同士の関係だけなので、相手が非表示の企業は「表示線なし」になります。球の大きさも同じ関係数です。</p>
          {(data.nodes.length === 0 || activeCategories.size === 0) && <button type="button" className="reset-button" onClick={resetFilters}>カテゴリと最小関係数を初期状態に戻す</button>}
        </section>
        <details className="legend-details" open>
          <summary>業種の凡例</summary>
          <div className="legend">{Object.entries(INDUSTRY_COLORS).map(([name, color]) => <span key={name}><i style={{ background: color }} />{name}</span>)}</div>
        </details>
      </aside>
      <div ref={wrapRef} className="map-canvas" tabIndex={0} role="group"
        aria-label="上場企業間ネットワークの 3D 表示。ドラッグで視点を回転、スクロールで拡大縮小。左右の矢印キーで水平に、上下の矢印キーで垂直に回転、＋／−で拡大縮小、0 で視点をリセットできます。企業をクリックすると関係グラフを開きます。"
        onPointerDown={() => wake(1500)} onPointerMove={() => wake(600)} onWheel={() => wake(800)} onKeyDown={onKeyDown}>
        <div className="map-caption"><strong>上場企業間ネットワーク（3D）</strong><br />色：業種 ／ 球の大きさ：関係数<br />ドラッグで回転 · スクロール／ピンチで拡大縮小 · 右ドラッグ／2本指で移動 · 企業を選択して詳細へ</div>
        <ForceGraph3D ref={fgRef} width={size.w} height={size.h} graphData={data}
          controlType="orbit" backgroundColor="#ffffff" showNavInfo={false}
          nodeId="id" nodeRelSize={NODE_REL_SIZE} nodeVal={nodeVal} nodeColor={nodeColor} nodeOpacity={0.95} nodeResolution={12}
          nodeLabel={noLabel}
          linkColor={linkColor} linkOpacity={0.4} linkWidth={0}
          warmupTicks={60} cooldownTicks={150}
          enableNodeDrag={false}
          onEngineTick={onEngineTick} onEngineStop={onEngineStop} onNodeHover={onNodeHover} onNodeClick={onNodeClick}
        />
        <div ref={labelsRef} className="map-labels" aria-hidden="true">{hubs.map((n, i) => <span key={n.id} data-i={i} style={{ visibility: 'hidden' }}>{n.name}</span>)}</div>
        {!data.nodes.length && <div className="map-empty" role="status"><strong>表示できる企業がありません</strong><span>カテゴリを選択するか、最小関係数を下げてください。</span><button type="button" className="reset-button" style={{ pointerEvents: 'auto' }} onClick={resetFilters}>初期状態に戻す</button></div>}
        {hoverNode && <div className="map-hover"><strong>{hoverNode.name}</strong><small>{hoverNode.id} · {hoverNode.industry}</small><small>選択カテゴリで上場企業と {hoverNode.degree}関係（非表示の相手を含む）</small></div>}
        <div className="map-tools"><button onClick={() => zoomBy(1.4)} aria-label="拡大">＋</button><button onClick={() => zoomBy(1 / 1.4)} aria-label="縮小">−</button><button onClick={resetView}>視点をリセット</button></div>
      </div>
    </div>
  );
}
