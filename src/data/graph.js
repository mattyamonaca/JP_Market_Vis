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
  statusValues: m5.status_values ?? null,
  evidenceShards: m5.evidence_shards ?? null,
};

// 関係の状態（Issue #3/#5）。旧データには status がないため confirmed 扱い
export const STATUS_JA = {
  confirmed: '確定',
  needs_review: '要確認',
  historical: '過去',
};
export const relationStatus = (rel) => rel.status ?? 'confirmed';
// 全体マップ・ランキング・統計の「確定関係」= status が confirmed のもの
export const CURRENT_RELATIONS = RELATIONS.filter((rel) => relationStatus(rel) === 'confirmed');

// 出所の種別（一次開示／二次情報／LLM抽出）と、抽出内容の検証状態は別の情報として扱う
export const TIER_JA = {
  primary: '一次開示',
  secondary: '二次情報',
  llm_extraction: 'LLM抽出',
};
export const evidenceTier = (ev) => ev.tier ?? ev.source_tier ?? ({ edinet: 'primary', official_release: 'primary', wikidata: 'secondary', ir_disclosure: 'llm_extraction' }[ev.source] ?? null);

// エビデンス全文（基準日・原本URL・抽出根拠・引用・比率の履歴）は関係IDごとのシャードに分けて配信する。
// 詳細パネルを開いたときだけ取得し、メモリにキャッシュする。旧データ（シャードなし）は本体の evidence をそのまま返す。
const shardCache = new Map();
export async function loadRelationDetail(relation) {
  const shards = META.evidenceShards;
  if (!shards) return { evidence: relation.evidence, ownership: relation.attributes?.ownership ?? null };
  const n = Number(relation.relation_id.slice(1));
  const shard = String(Math.floor(n / shards.size)).padStart(4, '0');
  if (!shardCache.has(shard)) {
    shardCache.set(shard, readData(shards.path.replace('{shard}', shard)).catch((err) => {
      shardCache.delete(shard);
      throw err;
    }));
  }
  const payload = await shardCache.get(shard);
  return payload[relation.relation_id] ?? null;
}

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

export function currentDegreeOf(ref) {
  return neighborsOf(ref).filter((n) => relationStatus(n.relation) === 'confirmed').length;
}

// エッジを持つ上場企業の次数ランキング（降順）。確定関係のみを数える
export const HUB_RANKING = Object.keys(COMPANIES)
  .map((code) => ({
    code,
    company: COMPANIES[code],
    degree: currentDegreeOf({ type: 'listed', key: code }),
  }))
  .filter((r) => r.degree > 0)
  .sort((a, b) => b.degree - a.degree);

// 統計集計。関係数の内訳は確定関係、状態別は全関係を数える
export const STATS = (() => {
  const byType = {};
  const byCategory = {};
  const bySource = {};
  const byTier = {};
  const byStatus = {};
  let listedToListed = 0;
  let verified = 0;
  let withAsOf = 0;
  for (const rel of RELATIONS) {
    byStatus[relationStatus(rel)] = (byStatus[relationStatus(rel)] ?? 0) + 1;
    if (rel.verification?.status === 'verified') verified += 1;
    if (rel.evidence.some((ev) => ev.as_of)) withAsOf += 1;
    if (relationStatus(rel) !== 'confirmed') continue;
    byType[rel.relation_type] = (byType[rel.relation_type] ?? 0) + 1;
    byCategory[rel.category] = (byCategory[rel.category] ?? 0) + 1;
    if (rel.source.type === 'listed' && rel.target.type === 'listed') listedToListed += 1;
    for (const ev of rel.evidence) {
      bySource[ev.source] = (bySource[ev.source] ?? 0) + 1;
      const tier = evidenceTier(ev) ?? 'unknown';
      byTier[tier] = (byTier[tier] ?? 0) + 1;
    }
  }
  return {
    companies: Object.keys(COMPANIES).length,
    relations: CURRENT_RELATIONS.length,
    relationsAll: RELATIONS.length,
    entities: Object.keys(ENTITIES).length,
    listedToListed,
    companiesWithEdges: HUB_RANKING.length,
    verified,
    withAsOf,
    byType,
    byCategory,
    bySource,
    byTier,
    byStatus,
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
  for (const rel of CURRENT_RELATIONS) {
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
  const byCategory = {};
  for (const link of links) byCategory[link.category] = (byCategory[link.category] ?? 0) + 1;
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
  return { nodes, links, byCategory };
})();

// カテゴリの収録状況: 全関係（確定）の件数と、全体マップ（上場企業間）の件数。0 件は「未収録」として区別する
export const CATEGORY_AVAILABILITY = Object.fromEntries(Object.keys(CATEGORY_JA).map((key) => [key, {
  total: STATS.byCategory[key] ?? 0,
  listed: GLOBAL_GRAPH.byCategory[key] ?? 0,
}]));
