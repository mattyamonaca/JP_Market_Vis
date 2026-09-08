import React, { useCallback, useMemo, useState } from 'react';
import { Background, Controls, MiniMap, ReactFlow } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import {
  CATEGORY_COLORS,
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
      style={{
        position: 'absolute',
        top: 12,
        left: 12,
        flexWrap: 'wrap',
        maxWidth: 'calc(100% - 24px)',
        zIndex: 10,
        display: 'flex',
        gap: 6,
        background: 'rgba(15, 23, 42, 0.85)',
        padding: '8px 10px',
        borderRadius: 10,
        border: '1px solid #1e293b',
      }}
    >
      {Object.entries(CATEGORY_JA).map(([key, ja]) => {
        const active = activeCategories.has(key);
        const color = CATEGORY_COLORS[key];
        return (
          <button
            aria-pressed={active}
            key={key}
            onClick={() => toggle(key)}
            style={{
              padding: '4px 12px',
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              background: active ? `${color}22` : 'transparent',
              border: `1px solid ${active ? color : '#334155'}`,
              color: active ? color : '#64748b',
            }}
          >
            {ja}
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
        onClick={onBack}
        style={{
          padding: '6px 14px',
          borderRadius: 8,
          fontSize: 12,
          cursor: 'pointer',
          background: 'rgba(15, 23, 42, 0.85)',
          border: '1px solid #334155',
          color: '#cbd5e1',
        }}
      >
        ← {prev?.name ?? history[history.length - 1]} に戻る
      </button>
    </div>
  );
}

function GraphView({ centerCode, setCenterCode }) {
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
            style={{
              position: 'absolute',
              bottom: 12,
              left: 12,
              zIndex: 10,
              fontSize: 12,
              color: '#94a3b8',
              background: 'rgba(15, 23, 42, 0.85)',
              border: '1px solid #334155',
              borderRadius: 8,
              padding: '6px 10px',
            }}
          >
            関係先が多いため {truncated} 社・団体を省略表示中（カテゴリ比例で関係先を抽出）。全件は「関係テーブル」で確認できます
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
              color: '#64748b',
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
          <Background color="#1e293b" gap={24} />
          <Controls
            style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
          />
          <MiniMap
            style={{ background: '#1e293b' }}
            nodeColor={(n) => (n.type === 'center' ? '#facc15' : n.type === 'listed' ? '#38bdf8' : '#475569')}
            maskColor="rgba(15, 23, 42, 0.7)"
          />
        </ReactFlow>
      </div>
      <DetailPanel selection={selection} onClose={() => setSelection(null)} />
    </div>
  );
}

export default function App() {
  const [view, setView] = useState('map');
  const [centerCode, setCenterCode] = useState(DEFAULT_CODE);

  const selectAndShowGraph = useCallback((code) => {
    setCenterCode(code);
    setView('graph');
  }, []);

  return (
    <div className="app-shell" style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%' }}>
      <Header view={view} setView={setView} />
      {view === 'map' && <GlobalMap onSelectCompany={selectAndShowGraph} />}
      {view === 'graph' && <GraphView centerCode={centerCode} setCenterCode={setCenterCode} />}
      {view === 'table' && <RelationTable />}
      {view === 'stats' && <StatsView onSelectCompany={selectAndShowGraph} />}
      <footer className="app-footer"><span>収録 {STATS.companies.toLocaleString()}社 · {STATS.relations.toLocaleString()}関係</span><span>データ生成 {META.generatedAt} · 自動抽出を含む／最新の上場状況・関係を保証しません</span></footer>
    </div>
  );
}
