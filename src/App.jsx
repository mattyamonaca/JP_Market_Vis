import React, { useCallback, useMemo, useState } from 'react';
import { Background, Controls, MiniMap, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  CATEGORY_AVAILABILITY,
  CATEGORY_TEXT_COLORS,
  CATEGORY_JA,
  COMPANIES,
  HUB_RANKING,
  RELATION_TYPES,
  nodeInfo,
  META,
  STATS,
} from './data/graph.js';
import { buildEgoNetwork } from './flow/egoNetwork.js';
import { nodeTypes } from './flow/nodeTypes.jsx';
import SearchSidebar from './components/SearchSidebar.jsx';
import DetailPanel from './components/DetailPanel.jsx';
import RelationTable from './components/RelationTable.jsx';
import StatsView from './components/StatsView.jsx';
import GlobalMap from './components/GlobalMap.jsx';

const DEFAULT_CODE = HUB_RANKING[0]?.code ?? '7203';

function Header({ view, setView }) {
  return (
    <header className="app-header">
      <div className="brand"><span className="brand-mark" aria-hidden="true">◉</span><div>
        <span className="brand-kicker">JP MARKET VIS</span>
        <h1>日本の上場企業マップ</h1>
      </div></div>
      <nav aria-label="表示切り替え" className="view-tabs">
        {Object.entries({ map: '全体マップ', graph: '関係グラフ', table: '関係一覧', stats: '統計・データ' }).map(([key, label]) => (
          <button key={key} aria-current={view === key ? 'page' : undefined}
            className={view === key ? 'active' : ''} onClick={() => setView(key)}>{label}</button>
        ))}
      </nav>
      <a className="repo-link" href="https://github.com/mattyamonaca/JP_Market_Vis" target="_blank" rel="noreferrer">GitHub ↗</a>
    </header>
  );
}

function CategoryFilterBar({ activeCategories, toggle }) {
  return (
    <div
      className="overlay-box"
      style={{
        position: 'absolute',
        top: 12,
        left: 12,
        flexWrap: 'wrap',
        maxWidth: 'calc(100% - 24px)',
        zIndex: 10,
        display: 'flex',
        gap: 6,
        padding: '8px 10px',
      }}
    >
      {Object.entries(CATEGORY_JA).map(([key, ja]) => {
        const unavailable = (CATEGORY_AVAILABILITY[key]?.total ?? 0) === 0;
        const active = activeCategories.has(key) && !unavailable;
        const color = CATEGORY_TEXT_COLORS[key];
        return (
          <button
            aria-pressed={active}
            aria-disabled={unavailable}
            disabled={unavailable}
            title={unavailable ? 'このカテゴリは現在のデータに収録されていません（関係がないことを意味しません）' : `${(CATEGORY_AVAILABILITY[key]?.total ?? 0).toLocaleString()}件`}
            key={key}
            onClick={() => toggle(key)}
            style={{
              opacity: unavailable ? 0.55 : 1,
              padding: '4px 12px',
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              background: active ? `${color}14` : 'var(--bg)',
              border: `1px solid ${active ? color : 'var(--border-strong)'}`,
              color: active ? color : 'var(--text-2)',
            }}
          >
            {ja}{unavailable && <small style={{ marginLeft: 4, fontSize: 10, color: 'var(--text-2)' }}>未収録</small>}
          </button>
        );
      })}
    </div>
  );
}

function BackBar({ history, onBack }) {
  if (history.length === 0) return null;
  const prev = COMPANIES[history[history.length - 1]];
  return (
    <div
      style={{
        position: 'absolute',
        top: 12,
        right: 12,
        zIndex: 10,
      }}
    >
      <button
        className="btn"
        onClick={onBack}
        style={{ padding: '6px 14px', fontSize: 12, background: 'rgba(255, 255, 255, 0.92)' }}
      >
        ← {prev?.name ?? history[history.length - 1]} に戻る
      </button>
    </div>
  );
}

function GraphView({ centerCode, setCenterCode, onShowInTable }) {
  const [selection, setSelection] = useState(null);
  const [history, setHistory] = useState([]);
  const [hoveredNodeId, setHoveredNodeId] = useState(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState(null);
  const [activeCategories, setActiveCategories] = useState(
    new Set(Object.keys(CATEGORY_JA)),
  );

  const toggleCategory = useCallback((key) => {
    setActiveCategories((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const { nodes, edges, truncated } = useMemo(
    () => buildEgoNetwork(centerCode, { categoryFilter: activeCategories }),
    [centerCode, activeCategories],
  );

  // ノードにホバー → そのノードに接続するエッジ/ノードを強調、他を減光。
  // エッジにホバー → 関係タイプ名のラベルを一時表示。
  const displayNodes = useMemo(() => {
    if (!hoveredNodeId) return nodes;
    const connected = new Set([hoveredNodeId]);
    for (const e of edges) {
      if (e.source === hoveredNodeId) connected.add(e.target);
      if (e.target === hoveredNodeId) connected.add(e.source);
    }
    return nodes.map((n) => ({
      ...n,
      data: { ...n.data, dimmed: !connected.has(n.id) },
    }));
  }, [nodes, edges, hoveredNodeId]);

  const displayEdges = useMemo(() => {
    return edges.map((e) => {
      const touchesHoverNode =
        hoveredNodeId && (e.source === hoveredNodeId || e.target === hoveredNodeId);
      const isHoverEdge = e.id === hoveredEdgeId;
      if (!hoveredNodeId && !isHoverEdge) return e;
      const rel = e.data.relation;
      const typeJa = RELATION_TYPES[rel.relation_type]?.ja ?? rel.relation_type;
      const dim = hoveredNodeId && !touchesHoverNode;
      const emphasize = isHoverEdge || touchesHoverNode;
      return {
        ...e,
        // ホバー対象のエッジ（およびホバー中ノードに接続するエッジ）に種別名を表示
        label: isHoverEdge || touchesHoverNode ? `${typeJa}${e.label ? ` ${e.label}` : ''}` : e.label,
        style: {
          ...e.style,
          opacity: dim ? 0.12 : emphasize ? 1 : e.style.opacity,
          strokeWidth: emphasize ? 2.6 : e.style.strokeWidth,
        },
      };
    });
  }, [edges, hoveredNodeId, hoveredEdgeId]);

  const onNodeClick = useCallback(
    (_, node) => {
      const ref = node.data.ref;
      // 上場企業の隣接ノードをクリック → その企業を中心に切り替え
      if (ref.type === 'listed' && ref.key !== centerCode) {
        setHistory((h) => [...h, centerCode]);
        setCenterCode(ref.key);
        setSelection(null);
        return;
      }
      setSelection({ kind: 'node', ref, info: nodeInfo(ref) });
    },
    [centerCode, setCenterCode],
  );

  const onEdgeClick = useCallback((_, edge) => {
    setSelection({ kind: 'edge', relation: edge.data.relation });
  }, []);

  const onNodeMouseEnter = useCallback((_, node) => setHoveredNodeId(node.id), []);
  const onNodeMouseLeave = useCallback(() => setHoveredNodeId(null), []);
  const onEdgeMouseEnter = useCallback((_, edge) => setHoveredEdgeId(edge.id), []);
  const onEdgeMouseLeave = useCallback(() => setHoveredEdgeId(null), []);

  const onBack = useCallback(() => {
    setHistory((h) => {
      if (h.length === 0) return h;
      const prev = h[h.length - 1];
      setCenterCode(prev);
      setSelection(null);
      return h.slice(0, -1);
    });
  }, [setCenterCode]);

  const handleSidebarSelect = useCallback(
    (code) => {
      if (code !== centerCode) {
        setHistory([]);
        setCenterCode(code);
        setSelection(null);
      }
    },
    [centerCode, setCenterCode],
  );

  return (
    <div className="graph-view" style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <SearchSidebar selectedCode={centerCode} onSelect={handleSidebarSelect} />
      <div className="ego-canvas" style={{ flex: 1, position: 'relative', minWidth: 0 }}>
        <CategoryFilterBar activeCategories={activeCategories} toggle={toggleCategory} />
        <BackBar history={history} onBack={onBack} />
        {truncated > 0 && (
          <div
            className="overlay-box"
            style={{
              position: 'absolute',
              bottom: 12,
              left: 12,
              zIndex: 10,
              fontSize: 12,
              color: 'var(--text-2)',
              padding: '6px 10px',
            }}
          >
            関係先が多いため {truncated} 社・団体を省略表示中（カテゴリ比例で関係先を抽出）。
            <button
              type="button"
              onClick={() => onShowInTable(centerCode)}
              style={{ marginLeft: 6, background: 'var(--bg)', border: '1px solid var(--border-strong)', borderRadius: 6, color: 'var(--accent)', padding: '2px 8px', fontSize: 12 }}
            >
              {COMPANIES[centerCode]?.name ?? centerCode} の関係を一覧で見る →
            </button>
          </div>
        )}
        {edges.length === 0 && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 5,
              pointerEvents: 'none',
              color: 'var(--text-2)',
              fontSize: 14,
            }}
          >
            {COMPANIES[centerCode]?.name ?? centerCode} の関係データはありません（フィルタを確認してください）
          </div>
        )}
        <ReactFlow
          key={centerCode}
          nodes={displayNodes}
          edges={displayEdges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          onEdgeClick={onEdgeClick}
          onNodeMouseEnter={onNodeMouseEnter}
          onNodeMouseLeave={onNodeMouseLeave}
          onEdgeMouseEnter={onEdgeMouseEnter}
          onEdgeMouseLeave={onEdgeMouseLeave}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.1}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#cbd5e1" gap={24} />
          <Controls />
          <MiniMap
            style={{ background: '#f8fafc' }}
            nodeColor={(n) => (n.type === 'center' ? '#0369a1' : n.type === 'listed' ? '#0ea5e9' : '#cbd5e1')}
            maskColor="rgba(248, 250, 252, 0.7)"
          />
        </ReactFlow>
      </div>
      <DetailPanel selection={selection} onClose={() => setSelection(null)} />
    </div>
  );
}

// 非表示のビューはレイアウト上のサイズを保ったまま見えなくする（display:none だと ResizeObserver が
// 0 サイズを拾い、復帰時にズーム・位置がずれる）
function ViewPane({ active, children }) {
  return (
    <div className={`view-pane${active ? '' : ' view-pane-hidden'}`} aria-hidden={!active} inert={active ? undefined : ''}>
      {children}
    </div>
  );
}

export default function App() {
  const [view, setView] = useState('map');
  const [centerCode, setCenterCode] = useState(DEFAULT_CODE);
  // 一覧への絞り込み依頼（企業コード）。nonce で同じ企業の再依頼も反映する
  const [tableRequest, setTableRequest] = useState(null);
  // 一度表示したビューはアンマウントせず非表示にする（検索・フィルタ・回転モード・描画位置・ズーム・
  // 一覧のページ位置を往復後も保持するため。Issue #7）
  const [visited, setVisited] = useState(() => new Set(['map']));
  const showView = useCallback((key) => {
    setVisited((prev) => (prev.has(key) ? prev : new Set([...prev, key])));
    setView(key);
  }, []);

  const selectAndShowGraph = useCallback((code) => {
    setCenterCode(code);
    showView('graph');
  }, [showView]);
  const showInTable = useCallback((code) => {
    setTableRequest({ code, nonce: Date.now() });
    showView('table');
  }, [showView]);

  return (
    <div className="app-shell" style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
      <Header view={view} setView={showView} />
      <ViewPane active={view === 'map'}><GlobalMap onSelectCompany={selectAndShowGraph} /></ViewPane>
      {visited.has('graph') && <ViewPane active={view === 'graph'}><GraphView centerCode={centerCode} setCenterCode={setCenterCode} onShowInTable={showInTable} /></ViewPane>}
      {visited.has('table') && <ViewPane active={view === 'table'}><RelationTable request={tableRequest} /></ViewPane>}
      {visited.has('stats') && <ViewPane active={view === 'stats'}><StatsView onSelectCompany={selectAndShowGraph} /></ViewPane>}
      <footer className="app-footer"><span>収録 {STATS.companies.toLocaleString()}社 · 確定 {STATS.relations.toLocaleString()}関係{STATS.byStatus.needs_review ? ` · 要確認 ${STATS.byStatus.needs_review.toLocaleString()}` : ''}</span><span>データ生成 {META.generatedAt} · 自動抽出を含む／最新の上場状況・関係を保証しません</span></footer>
    </div>
  );
}
