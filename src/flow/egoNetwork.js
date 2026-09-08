// 選択企業のエゴネットワーク（1ホップ）を React Flow の nodes/edges に変換する。
// レイアウトはカテゴリ別セクター × 多重リング。ノード重なりを避け、
// 同じ関係カテゴリの相手先が角度的にまとまって見えるようにする。
import {
  CATEGORY_COLORS,
  RELATION_TYPES,
  degreeOf,
  neighborsOf,
  nodeInfo,
  nodeKey,
  nodeName,
} from '../data/graph.js';

const CATEGORY_ORDER = ['capital', 'transaction', 'alliance', 'personnel', 'group'];

const BASE_RADIUS = 300; // 最内リングの半径
const RING_GAP = 165; // リング間隔
const NODE_ARC = 165; // 1ノードが必要とする弧長（重なり防止）
const SECTOR_GAP = 0.14; // セクター間の角度の隙間（rad）

function relSortKey(rel) {
  return [CATEGORY_ORDER.indexOf(rel.category), rel.relation_type, ''].join('|');
}

// 1セクター内に members を多重リングで配置し positions(Map) に書き込む
function layoutSector(members, angleStart, span, positions) {
  let placed = 0;
  let ring = 0;
  while (placed < members.length) {
    const radius = BASE_RADIUS + ring * RING_GAP;
    const arc = span * radius;
    const capacity = Math.max(1, Math.floor(arc / NODE_ARC));
    const countThisRing = Math.min(capacity, members.length - placed);
    for (let j = 0; j < countThisRing; j += 1) {
      const frac = countThisRing === 1 ? 0.5 : j / (countThisRing - 1);
      // セクター端への張り付きを避けるため内側に少し詰める
      const a = angleStart + span * (0.08 + 0.84 * frac);
      positions.set(members[placed + j].key, {
        x: Math.cos(a) * radius,
        y: Math.sin(a) * radius,
      });
    }
    placed += countThisRing;
    ring += 1;
  }
}

export function buildEgoNetwork(centerCode, { categoryFilter = null, maxNeighbors = 90 } = {}) {
  const centerRef = { type: 'listed', key: centerCode };
  const center = nodeInfo(centerRef);
  if (!center) return { nodes: [], edges: [], truncated: 0 };

  let links = neighborsOf(centerRef);
  if (categoryFilter) {
    links = links.filter((l) => categoryFilter.has(l.relation.category));
  }

  // 相手先ごとに集約（同じ相手と複数関係があればノードを共有）。
  // 相手先の「主カテゴリ」は、その相手に紐づく関係のうち CATEGORY_ORDER 最優先のもの。
  const neighborMap = new Map(); // key -> { key, ref, relations:[], primaryCat }
  for (const l of links) {
    const k = nodeKey(l.other);
    if (!neighborMap.has(k)) {
      neighborMap.set(k, { key: k, ref: l.other, relations: [] });
    }
    neighborMap.get(k).relations.push(l.relation);
  }
  for (const nb of neighborMap.values()) {
    nb.relations.sort((a, b) => relSortKey(a).localeCompare(relSortKey(b)));
    nb.primaryCat = nb.relations[0].category;
  }

  // 多すぎる場合は次数の高い相手・上場企業を優先して打ち切り
  let neighbors = [...neighborMap.values()];
  const totalNeighbors = neighbors.length;
  neighbors.sort((a, b) => {
    const ca = CATEGORY_ORDER.indexOf(a.primaryCat);
    const cb = CATEGORY_ORDER.indexOf(b.primaryCat);
    if (ca !== cb) return ca - cb;
    const la = a.ref.type === 'listed' ? 0 : 1;
    const lb = b.ref.type === 'listed' ? 0 : 1;
    if (la !== lb) return la - lb;
    return nodeName(a.ref).localeCompare(nodeName(b.ref));
  });
  let truncated = 0;
  if (neighbors.length > maxNeighbors) {
    // カテゴリの多様性を保つため、各カテゴリから比例配分で残す
    const byCat = new Map();
    for (const nb of neighbors) {
      if (!byCat.has(nb.primaryCat)) byCat.set(nb.primaryCat, []);
      byCat.get(nb.primaryCat).push(nb);
    }
    const kept = [];
    for (const [, list] of byCat) {
      const quota = Math.max(1, Math.round((list.length / totalNeighbors) * maxNeighbors));
      kept.push(...list.slice(0, quota));
    }
    truncated = neighbors.length - kept.length;
    neighbors = kept;
  }

  // カテゴリ別グループ（CATEGORY_ORDER 順）
  const groups = [];
  for (const cat of CATEGORY_ORDER) {
    const members = neighbors.filter((nb) => nb.primaryCat === cat);
    if (members.length) groups.push({ cat, members });
  }

  // 角度割当：各セクターはメンバー数に比例。セクター間に固定の隙間。
  const n = neighbors.length || 1;
  const positions = new Map();
  const usable = 2 * Math.PI - SECTOR_GAP * groups.length;
  let angle = -Math.PI / 2; // 真上から開始
  for (const g of groups) {
    const span = Math.max(0.2, usable * (g.members.length / n));
    layoutSector(g.members, angle, span, positions);
    angle += span + SECTOR_GAP;
  }

  const nodes = [
    {
      id: nodeKey(centerRef),
      type: 'center',
      position: { x: 0, y: 0 },
      data: {
        label: center.name,
        code: centerCode,
        segment: center.market_segment,
        industry: center.industry_17,
        degree: degreeOf(centerRef),
        ref: centerRef,
      },
    },
    ...neighbors.map((nb) => {
      const info = nodeInfo(nb.ref);
      return {
        id: nb.key,
        type: nb.ref.type === 'listed' ? 'listed' : 'entity',
        position: positions.get(nb.key) ?? { x: 0, y: 0 },
        data: {
          label: nodeName(nb.ref),
          code: nb.ref.type === 'listed' ? nb.ref.key : null,
          segment: nb.ref.type === 'listed' ? info?.market_segment : null,
          ref: nb.ref,
        },
      };
    }),
  ];

  // 表示する相手先のキー集合（打ち切られた相手へのエッジは描かない）
  const visibleKeys = new Set(neighbors.map((nb) => nb.key));
  const centerKey = nodeKey(centerRef);

  const edges = [];
  for (const nb of neighbors) {
    for (const rel of nb.relations) {
      const color = CATEGORY_COLORS[rel.category] ?? '#64748b';
      const ratioVal = rel.attributes?.ownership_ratio ?? rel.attributes?.sales_ratio;
      const ratioLabel = ratioVal != null ? `${(ratioVal * 100).toFixed(1)}%` : '';
      const sKey = nodeKey(rel.source);
      const tKey = nodeKey(rel.target);
      if (!visibleKeys.has(sKey === centerKey ? tKey : sKey)) continue;
      edges.push({
        id: rel.relation_id,
        source: sKey,
        target: tKey,
        type: 'default',
        label: ratioLabel, // 種別は色で表現。比率がある時だけラベル表示してクラッタを抑える
        labelStyle: { fill: '#e2e8f0', fontSize: 10, fontWeight: 600 },
        labelBgStyle: { fill: '#0f172a', fillOpacity: 0.85 },
        labelBgPadding: [3, 2],
        labelBgBorderRadius: 3,
        style: { stroke: color, strokeWidth: 1.4, opacity: 0.75 },
        markerEnd: rel.directed
          ? { type: 'arrowclosed', color, width: 14, height: 14 }
          : undefined,
        data: { relation: rel },
      });
    }
  }

  return { nodes, edges, truncated };
}
