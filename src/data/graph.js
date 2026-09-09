import { createSearcher } from './search.js';

// M4/M5 の読み込みとグラフインデックス構築（モジュールロード時に一度だけ実行）
// データは大きい（M5 ~32MB）ためバンドルせず public/ から実行時 fetch する。
// top-level await でモジュール解決をデータ取得まで待たせ、以降は同期的に参照できる。
async function readData(name) {
  const response = await fetch(`${import.meta.env?.BASE_URL ?? '/'}${name}`);
  if (!response.ok) throw new Error(`データを取得できませんでした (${response.status})`);
  return response.json();
}
const [m4, m5] = await Promise.all([
  readData('M4_companies.json'), readData('M5_company_relations.json'),
]);

export const COMPANIES = m4.companies;
export const ENTITIES = m5.entities;
export const RELATIONS = m5.relations;
export const RELATION_TYPES = m5.relation_types;
export const META = {
  m4Version: m4.version,
  m5Version: m5.version,
  generatedAt: m5.generated_at,
};

export const CATEGORY_COLORS = {
  capital: '#38bdf8',
  transaction: '#fb923c',
  alliance: '#4ade80',
  personnel: '#f472b6',
  group: '#a78bfa',
};

export const CATEGORY_JA = {
  capital: '資本',
  transaction: '取引',
  alliance: '提携',
  personnel: '人的',
  group: 'グループ',
};

export const SEGMENT_JA = {
  prime: 'プライム',
  standard: 'スタンダード',
  growth: 'グロース',
};

// ノードキー（"listed:7203" / "entity:ENT000001"）
export const nodeKey = (ref) => `${ref.type}:${ref.key}`;

export function nodeName(ref) {
  if (ref.type === 'listed') return COMPANIES[ref.key]?.name ?? ref.key;
  return ENTITIES[ref.key]?.name ?? ref.key;
}

export function nodeInfo(ref) {
  if (ref.type === 'listed') return COMPANIES[ref.key] ?? null;
  return ENTITIES[ref.key] ?? null;
}

// 隣接インデックス: nodeKey → [{relation, other, isOutgoing}]
const adjacency = new Map();
for (const rel of RELATIONS) {
  const sKey = nodeKey(rel.source);
  const tKey = nodeKey(rel.target);
  if (!adjacency.has(sKey)) adjacency.set(sKey, []);
  if (!adjacency.has(tKey)) adjacency.set(tKey, []);
  adjacency.get(sKey).push({ relation: rel, other: rel.target, isOutgoing: true });
  adjacency.get(tKey).push({ relation: rel, other: rel.source, isOutgoing: false });
}

export function neighborsOf(ref) {
  return adjacency.get(nodeKey(ref)) ?? [];
}

export function degreeOf(ref) {
  return neighborsOf(ref).length;
}

// エッジを持つ上場企業の次数ランキング（降順）
export const HUB_RANKING = Object.keys(COMPANIES)
  .map((code) => ({
    code,
    company: COMPANIES[code],
    degree: degreeOf({ type: 'listed', key: code }),
  }))
  .filter((r) => r.degree > 0)
  .sort((a, b) => b.degree - a.degree);

// 統計集計
export const STATS = (() => {
  const byType = {};
  const byCategory = {};
  const bySource = {};
  const byConfidence = {};
  let listedToListed = 0;
  for (const rel of RELATIONS) {
    byType[rel.relation_type] = (byType[rel.relation_type] ?? 0) + 1;
    byCategory[rel.category] = (byCategory[rel.category] ?? 0) + 1;
    if (rel.source.type === 'listed' && rel.target.type === 'listed') listedToListed += 1;
    for (const ev of rel.evidence) {
      bySource[ev.source] = (bySource[ev.source] ?? 0) + 1;
      byConfidence[ev.confidence] = (byConfidence[ev.confidence] ?? 0) + 1;
    }
  }
  return {
    companies: Object.keys(COMPANIES).length,
    relations: RELATIONS.length,
    entities: Object.keys(ENTITIES).length,
    listedToListed,
    companiesWithEdges: HUB_RANKING.length,
    byType,
    byCategory,
    bySource,
    byConfidence,
  };
})();

// 企業検索（名称・英文名・別名・ヨミ・証券コードの部分一致）。索引の作り方は search.js
export const searchCompanies = createSearcher(COMPANIES, (code) => degreeOf({ type: 'listed', key: code }));

// 17業種 → 色（全体マップのノード配色）
export const INDUSTRY_COLORS = {
  '食品': '#f87171',
  'エネルギー資源': '#fb923c',
  '建設・資材': '#fbbf24',
  '素材・化学': '#a3e635',
  '医薬品': '#4ade80',
  '自動車・輸送機': '#34d399',
  '鉄鋼・非鉄': '#2dd4bf',
  '機械': '#22d3ee',
  '電機・精密': '#38bdf8',
  '情報通信・サービスその他': '#818cf8',
  '電力・ガス': '#a78bfa',
  '運輸・物流': '#c084fc',
  '商社・卸売': '#e879f9',
  '小売': '#f472b6',
  '銀行': '#fb7185',
  '金融（除く銀行）': '#fda4af',
  '不動産': '#fcd34d',
  'その他': '#94a3b8',
};

export function industryColor(industry17) {
  return INDUSTRY_COLORS[industry17] ?? '#94a3b8';
}

// 全体マップ用: 両端が上場企業のエッジのみで構成したネットワーク
// （子会社など非上場エンティティは末端が大半のため除外して俯瞰性を確保）
export const GLOBAL_GRAPH = (() => {
  const deg = new Map();
  const links = [];
  for (const rel of RELATIONS) {
    if (rel.source.type !== 'listed' || rel.target.type !== 'listed') continue;
    const s = rel.source.key;
    const t = rel.target.key;
    deg.set(s, (deg.get(s) ?? 0) + 1);
    deg.set(t, (deg.get(t) ?? 0) + 1);
    links.push({
      source: s,
      target: t,
      category: rel.category,
      relationType: rel.relation_type,
      relationId: rel.relation_id,
    });
  }
  const nodes = [];
  for (const [code, d] of deg) {
    const c = COMPANIES[code];
    if (!c) continue;
    nodes.push({
      id: code,
      name: c.name,
      industry: c.industry_17 ?? 'その他',
      segment: c.market_segment,
      degree: d,
    });
  }
  return { nodes, links };
})();
