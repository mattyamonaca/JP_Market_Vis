import React, { useEffect, useState } from 'react';
import {
  CATEGORY_COLORS,
  CATEGORY_JA,
  META,
  RELATION_TYPES,
  SEGMENT_JA,
  STATUS_JA,
  TIER_JA,
  evidenceTier,
  loadRelationDetail,
  nodeName,
  relationStatus,
} from '../data/graph.js';

const SOURCE_JA = {
  wikidata: 'Wikidata',
  edinet: 'EDINET 有価証券報告書',
  ir_disclosure: '企業IRリリース（LLM抽出）',
  official_release: '公式開示（原本確認）',
};

const TIER_COLOR = { primary: '#7dd3fc', secondary: '#c4b5fd', llm_extraction: '#fdba74' };
const STATUS_COLOR = { confirmed: '#4ade80', needs_review: '#facc15', historical: '#94a3b8' };

const RATIO_KIND_JA = { voting: '議決権', share: '株式数', share_large_holding: '株券等保有割合（大量保有報告）', sales_share: '売上' };
const SCOPE_JA = { total: '合計', indirect_only: '間接のみ（合計不明）', unresolved: '同じ時点の記載が食い違い（未確定）' };
const REASON_JA = {
  unclassified: '関係会社の分類が原本で不明',
  direction_conflict: '分類と所有方向の記載が矛盾',
  'ir:no_quote': '根拠文なし',
  'ir:counterparty_not_in_quote': '根拠文に相手が出てこない',
  'ir:no_relation_cue': '根拠文に関係を示す語がない',
  'ir:co_mention_only': '社名が並んでいるだけ',
  'ir:tech_basis_only': 'ベース技術・準拠の記述のみ（供与の明示なし）',
  'ir:noise_context': '注記・商標・受賞・イベント等の文脈',
  'ir:third_party_statement': '提出会社が当事者でない記述',
  'ir:direction_unclear': 'どちらが主体か不明',
};
const reasonLabel = (r) => REASON_JA[r] ?? (r.startsWith('ir:cue_for_other_type:') ? `根拠は別タイプ（${RELATION_TYPES[r.split(':')[2]]?.ja ?? r.split(':')[2]}）を示す` : r);

const pct = (v, digits = 2) => (v == null ? null : `${(v * 100).toFixed(digits)}%`);
const dateOrUnknown = (d) => d ?? '不明';

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 }}>
        {title}
      </div>
      {children}
    </div>
  );
}

function Field({ label, value }) {
  if (value == null || value === '') return null;
  return (
    <div style={{ display: 'flex', fontSize: 12, marginBottom: 4, gap: 8 }}>
      <span style={{ color: '#a8b7cb', minWidth: 84, flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#f1f5f9', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}

function Badge({ color, children, title }) {
  return (
    <span title={title} style={{ display: 'inline-block', padding: '2px 8px', borderRadius: 999, fontSize: 11, fontWeight: 700, background: `${color}22`, border: `1px solid ${color}`, color, marginRight: 6, marginBottom: 4 }}>
      {children}
    </span>
  );
}

function ExternalLink({ href, children }) {
  if (!/^https?:\/\//i.test(href ?? '')) return null;
  return <a href={href} target="_blank" rel="noreferrer" style={{ color: '#7dd3fc' }}>{children}</a>;
}

function CompanyDetail({ info, refObj }) {
  if (refObj.type === 'entity') {
    return (
      <>
        <Section title="非上場エンティティ">
          <Field label="名称" value={info.name} />
          <Field label="法人番号" value={info.corporate_number} />
          <Field label="Wikidata" value={info.wikidata_qid && <ExternalLink href={`https://www.wikidata.org/wiki/${info.wikidata_qid}`}>{info.wikidata_qid}</ExternalLink>} />
        </Section>
        <div style={{ fontSize: 12, color: '#a8b7cb' }}>収録上場企業以外の組織です。子会社・グループ等として関係先にのみ登場します。</div>
      </>
    );
  }
  return (
    <Section title="上場企業">
      <Field label="名称" value={info.name} />
      <Field label="正式名称" value={info.name_edinet} />
      <Field label="読み" value={info.name_kana} />
      <Field label="別名" value={info.aliases?.length ? info.aliases.join('、') : null} />
      <Field label="英文名" value={info.name_en} />
      <Field label="証券コード" value={info.securities_code} />
      <Field label="市場区分" value={SEGMENT_JA[info.market_segment]} />
      <Field label="33業種" value={info.industry_33} />
      <Field label="17業種" value={info.industry_17} />
      <Field label="規模区分" value={info.scale_category} />
      <Field label="法人番号" value={info.corporate_number} />
      <Field label="EDINET" value={info.edinet_code} />
      <Field label="所在地" value={info.address} />
      <Field label="Wikidata" value={info.wikidata_qid && <ExternalLink href={`https://www.wikidata.org/wiki/${info.wikidata_qid}`}>{info.wikidata_qid}</ExternalLink>} />
    </Section>
  );
}

// 比率の表示用に、本体の要約（意味・基準日・数値）とシャードの内訳（直接／間接・原文・履歴）を合成する。
// シャード取得前・失敗時も本体の既知の数値を表示し、間接のみ／未確定の本当に合計不明な値は不明のまま残す。
export function mergeRatio(summary, detail, fallback) {
  if (!summary && !detail && fallback == null) return null;
  const merged = { ...(summary ?? {}), ...(detail ?? {}) };
  if (merged.value == null && fallback != null && !['indirect_only', 'unresolved'].includes(merged.scope)) {
    merged.value = fallback;
  }
  return merged;
}

// 比率の内訳（意味・直接／間接・基準日・出所・履歴）
function RatioDetail({ label, summary, detail, fallback }) {
  const r = mergeRatio(summary, detail, fallback);
  if (!r) return null;
  const kind = RATIO_KIND_JA[r.kind] ?? '';
  const main = r.value != null ? `${kind}${kind ? ' ' : ''}${pct(r.value)}` : `合計不明（${SCOPE_JA[r.scope] ?? r.scope ?? '—'}）`;
  return (
    <div style={{ marginBottom: 6 }}>
      <Field label={label} value={main} />
      {(r.direct != null || r.indirect != null) && (
        <Field label="内訳" value={[r.direct != null && `直接 ${pct(r.direct)}`, r.indirect != null && `間接 ${pct(r.indirect)}`].filter(Boolean).join(' ／ ')} />
      )}
      <Field label="基準日" value={dateOrUnknown(r.as_of)} />
      {r.raw && <Field label="原文" value={r.raw} />}
      {r.verified && <Field label="検証" value="原本で確認済みの値" />}
      {r.conflicting_values?.length > 0 && <Field label="競合する値" value={r.conflicting_values.map((v) => pct(v)).join(' ／ ')} />}
      {r.conflict_same_period && <Field label="注意" value="同じ時点で異なる値の記載があります（履歴を確認してください）" />}
      {r.history?.length > 0 && (
        <details style={{ fontSize: 12, marginTop: 4 }}>
          <summary style={{ cursor: 'pointer', color: '#a8b7cb' }}>他の記載・過去の値 {r.history.length} 件</summary>
          <ul style={{ margin: '4px 0 0', paddingLeft: 16, color: '#cbd5e1' }}>
            {r.history.map((h, i) => (
              <li key={i}>
                {RATIO_KIND_JA[h.kind] ?? ''} {h.value != null ? pct(h.value) : '合計不明'}
                {h.indirect != null ? `（間接 ${pct(h.indirect)}）` : ''} · 基準日 {dateOrUnknown(h.as_of)}{h.doc_id ? ` · ${h.doc_id}` : ''}{h.status ? ` · ${h.status}` : ''}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function EvidenceCard({ ev }) {
  const tier = evidenceTier(ev);
  const url = ev.url;
  const originalLabel = ev.source === 'edinet' ? 'EDINET で原本を開く' : ev.source === 'wikidata' ? 'Wikidata の項目を開く' : '公表資料を開く';
  return (
    <div style={{ background: '#1e293b', borderRadius: 8, padding: '8px 10px', marginBottom: 6, fontSize: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4, gap: 6, flexWrap: 'wrap' }}>
        <span style={{ color: '#f1f5f9', fontWeight: 600 }}>{SOURCE_JA[ev.source] ?? ev.source}</span>
        <span>
          {tier && <Badge color={TIER_COLOR[tier] ?? '#94a3b8'} title="出所の種別。抽出内容の正しさとは別です">{TIER_JA[tier] ?? tier}</Badge>}
          {ev.verification === 'verified' && <Badge color="#4ade80">原本確認</Badge>}
        </span>
      </div>
      <Field label="基準日" value={dateOrUnknown(ev.as_of)} />
      <Field label="公表日" value={dateOrUnknown(ev.published ?? ev.date)} />
      <Field label="取得日" value={dateOrUnknown(ev.retrieved)} />
      {ev.property && <Field label="項目" value={{ affiliated: '関係会社の状況', shareholder: '大株主の状況', large_holding_report: '大量保有報告書（大株主の状況の注記）', customer: '主要な顧客' }[ev.property] ?? ev.property} />}
      {ev.classification && (
        <Field label="原本の分類" value={`${ev.classification}${ev.classification_source ? `（${{ section: '節見出し', row: 'ラベル行', column: '区分列', prefix: '行頭の表記', note: '注記', header: '見出しセル' }[ev.classification_source] ?? ev.classification_source}から）` : ''}`} />
      )}
      {ev.direction_source && <Field label="方向の根拠" value={{ cell: 'セル内の所有／被所有表記', header: '列見出し', classification: '分類（親会社・その他の関係会社）', default: '既定（提出会社が所有）' }[ev.direction_source] ?? ev.direction_source} />}
      {ev.raw_name && <Field label="原文名" value={ev.raw_name} />}
      {ev.relationship_note && <Field label="関係内容" value={ev.relationship_note} />}
      {ev.quote && <Field label="根拠文" value={`「${ev.quote}」`} />}
      {ev.extraction?.cue && <Field label="手がかり" value={ev.extraction.cue} />}
      {ev.extraction?.reasons?.length > 0 && <Field label="要確認理由" value={ev.extraction.reasons.map((r) => reasonLabel(`ir:${r}`)).join('、')} />}
      {ev.extraction?.retyped_from && <Field label="読み替え" value={`LLM の分類 ${RELATION_TYPES[ev.extraction.retyped_from]?.ja ?? ev.extraction.retyped_from} → 根拠文に基づき変更`} />}
      {ev.deal_status && <Field label="状態" value={{ agreed: '合意・予定', executed: '実行済み' }[ev.deal_status] ?? ev.deal_status} />}
      {ev.event_year && <Field label="時点" value={`${ev.event_year}年の出来事に言及`} />}
      {ev.person && <Field label="人物" value={ev.person} />}
      {ev.note && <Field label="備考" value={ev.note} />}
      {url ? (
        <Field label="原本" value={<>{ev.doc_id && <span style={{ color: '#cbd5e1', marginRight: 6 }}>{ev.doc_id}</span>}<ExternalLink href={url}>{originalLabel} ↗</ExternalLink></>} />
      ) : (
        <Field label="原本" value={ev.doc_id ? `書類ID ${ev.doc_id}（リンク情報なし。EDINET の書類検索で参照できます）` : 'リンク情報なし'} />
      )}
    </div>
  );
}

export function RelationDetail({ relation }) {
  const typeDef = RELATION_TYPES[relation.relation_type] ?? {};
  const color = CATEGORY_COLORS[relation.category] ?? '#64748b';
  const status = relationStatus(relation);
  const [detail, setDetail] = useState(null);
  const [loadState, setLoadState] = useState('loading');
  useEffect(() => {
    let alive = true;
    setDetail(null);
    setLoadState('loading');
    loadRelationDetail(relation).then((d) => {
      if (!alive) return;
      setDetail(d);
      setLoadState('done');
    }).catch(() => alive && setLoadState('error'));
    return () => { alive = false; };
  }, [relation]);
  const evidence = detail?.evidence ?? relation.evidence;
  const verification = detail?.verification ?? relation.verification;
  return (
    <>
      <Section title={`関係 ${relation.relation_id}`}>
        <div style={{ marginBottom: 8 }}>
          <Badge color={color}>{CATEGORY_JA[relation.category]} / {typeDef.ja ?? relation.relation_type}</Badge>
          <Badge color={STATUS_COLOR[status]} title={status === 'confirmed' ? '出所の記載どおりに抽出できた関係。内容の真偽を保証するものではありません' : status === 'needs_review' ? '出所の記載から関係タイプ・方向を確定できない関係' : '後続の開示で過去の状態になった関係'}>{STATUS_JA[status]}</Badge>
          <Badge color={verification?.status === 'verified' ? '#4ade80' : '#94a3b8'} title="抽出結果を人手で原本と照合したかどうか">
            {verification?.status === 'verified' ? `原本で検証済み${verification.on ? `（${verification.on}）` : ''}` : '未検証（自動抽出）'}
          </Badge>
        </div>
        {status === 'needs_review' && relation.review_reasons?.length > 0 && (
          <Field label="要確認理由" value={relation.review_reasons.map(reasonLabel).join('、')} />
        )}
        {status === 'historical' && <Field label="有効期限" value={`${relation.valid_until ?? '不明'} まで${relation.superseded_by ? `（後続: ${relation.superseded_by}）` : ''}`} />}
        {verification?.note && <Field label="検証メモ" value={verification.note} />}
        {verification?.source?.url && <Field label="検証の根拠" value={<ExternalLink href={verification.source.url}>{verification.source.title ?? verification.source.url} ↗</ExternalLink>} />}
        <Field label="From" value={nodeName(relation.source)} />
        <Field label="To" value={nodeName(relation.target)} />
        <Field label="方向" value={relation.directed ? '有向' : '無向'} />
        <Field label="説明" value={typeDef.description} />
        <RatioDetail label="出資比率" summary={relation.attributes?.ownership} detail={detail?.ownership} fallback={relation.attributes?.ownership_ratio} />
        {relation.attributes?.sales_ratio != null && <Field label="売上比率" value={pct(relation.attributes.sales_ratio)} />}
        {relation.attributes?.sales_amount?.value != null && <Field label="売上高" value={`${relation.attributes.sales_amount.value.toLocaleString()} ${relation.attributes.sales_amount.unit ?? ''}（基準日 ${dateOrUnknown(relation.attributes.sales_amount.as_of)}）`} />}
        {relation.attributes?.deal_status && <Field label="状態" value={{ agreed: '合意・予定', executed: '実行済み' }[relation.attributes.deal_status] ?? relation.attributes.deal_status} />}
        {relation.attributes?.event_year && <Field label="時点" value={`${relation.attributes.event_year}年の出来事（公表日とは別）`} />}
        {relation.attributes?.person && <Field label="人物" value={relation.attributes.person} />}
      </Section>
      <Section title={`エビデンス（出所） ${evidence.length} 件`}>
        {loadState === 'loading' && detail === null && META.evidenceShards && <div style={{ fontSize: 12, color: '#a8b7cb', marginBottom: 6 }}>原本情報を読み込み中…</div>}
        {loadState === 'error' && <div style={{ fontSize: 12, color: '#fca5a5', marginBottom: 6 }}>原本情報を取得できませんでした。通信状況を確認してください。</div>}
        {evidence.map((ev, i) => <EvidenceCard key={i} ev={ev} />)}
        <div style={{ fontSize: 11, color: '#a8b7cb', lineHeight: 1.6 }}>
          「一次開示」は出所の種別で、抽出が正しいことを意味しません。「原本で検証済み」は人手で照合した関係にだけ付きます。
        </div>
      </Section>
    </>
  );
}

export default function DetailPanel({ selection, onClose }) {
  if (!selection) return null;
  return (
    <div className="detail-panel" role="region" aria-label="企業・関係の詳細" style={{ width: 320, minWidth: 320, height: '100%', overflowY: 'auto', borderLeft: '1px solid #1e293b', background: 'rgba(15, 23, 42, 0.97)', padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#facc15' }}>詳細</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#a8b7cb', cursor: 'pointer', fontSize: 14 }}>✕ 閉じる</button>
      </div>
      {selection.kind === 'node' && <CompanyDetail info={selection.info} refObj={selection.ref} />}
      {selection.kind === 'edge' && <RelationDetail relation={selection.relation} />}
    </div>
  );
}
