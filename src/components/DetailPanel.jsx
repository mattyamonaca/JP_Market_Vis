import React, { useEffect, useState } from 'react';
import CompanySources from './CompanySources.jsx';
import {
  CATEGORY_TEXT_COLORS,
  CATEGORY_JA,
  META,
  RELATION_TYPES,
  SEGMENT_JA,
  STATUS_COLORS,
  STATUS_JA,
  TIER_COLORS,
  TIER_JA,
  evidenceTier,
  loadRelationDetail,
  nodeName,
  neighborsOf,
  relationStatus,
  relationStatusLabel,
} from '../data/graph.js';

const SOURCE_JA = {
  wikidata: 'Wikidata',
  edinet: 'EDINET 有価証券報告書',
  ir_disclosure: '企業IRリリース（LLM抽出）',
  official_release: '公式開示（原本確認）',
  issuer_website: '企業公式サイト（原本確認）',
  group_site: 'グループ広報団体の会員一覧（公式サイト）',
};


const RATIO_KIND_JA = { voting: '議決権', share: '株式数', share_large_holding: '株券等保有割合（大量保有報告）', sales_share: '売上' };
const SCOPE_JA = { total: '合計', indirect_only: '間接のみ（合計不明）', unresolved: '同じ時点の記載が食い違い（未確定）' };
const REASON_JA = {
  unclassified: '関係会社の分類が原本で不明',
  officer_role_unproven: '顧問・相談役等の記載のみで、両社の役員兼任を確認できない',
  ambiguous_listed_name: '同名の上場企業が複数あり、法人を特定できない',
  direction_conflict: '分類と所有方向の記載が矛盾',
  'ir:no_quote': '根拠文なし',
  'ir:counterparty_not_in_quote': '根拠文に相手が出てこない',
  'ir:no_relation_cue': '根拠文に関係を示す語がない',
  'ir:co_mention_only': '社名が並んでいるだけ',
  'ir:tech_basis_only': 'ベース技術・準拠の記述のみ（供与の明示なし）',
  'ir:noise_context': '注記・商標・受賞・イベント等の文脈',
  'ir:third_party_statement': '提出会社が当事者でない記述',
  'ir:direction_unclear': 'どちらが主体か不明（対等な合併・統合など）',
  'ir:counterparty_is_own_subsidiary': '相手が提出会社自身の子会社として記述されている',
  'ir:major_customer_materiality_unproven': '主要販売先の基準（連結売上10%以上）を確認できない',
  'ir:joint_venture_target_unverified': '出資先の合弁会社と共同出資者を区別できない',
  'ir:source_not_checked': '引用元との照合が未実施',
  'ir:source_excerpt_not_found': '取得した本文で抽出根拠の一致を確認できない',
  'ir:source_excerpt_too_short': '抽出根拠が短く出典を照合できない',
  'ir:source_fetch_failed': '出典を再取得できず照合できない',
  'ir:source_reviewed_document': '資料上の当事者・関係分類を個別照合',
  wikidata_parent_below_control: 'Wikidata の親組織だが、有報では支配関係ではない',
  insufficient_evidence: '原本確認の結果、根拠不足',
};
const reasonLabel = (r) => REASON_JA[r] ?? (r.startsWith('ir:cue_for_other_type:') ? `根拠は別タイプ（${RELATION_TYPES[r.split(':')[2]]?.ja ?? r.split(':')[2]}）を示す` : r);

const pct = (v, digits = 2) => (v == null ? null : `${(v * 100).toFixed(digits)}%`);
const dateOrUnknown = (d) => d ?? '不明';

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text-2)', letterSpacing: .5, marginBottom: 6 }}>
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
      <span style={{ color: 'var(--text-2)', minWidth: 84, flexShrink: 0 }}>{label}</span>
      <span style={{ color: 'var(--text)', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}

function Badge({ color, children, title }) {
  return (
    <span className="pill" title={title} style={{ fontSize: 11, background: `${color}14`, color, marginRight: 6, marginBottom: 4 }}>
      {children}
    </span>
  );
}

function ExternalLink({ href, children }) {
  if (!/^https?:\/\//i.test(href ?? '')) return null;
  return <a href={href} target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>{children}</a>;
}

function groupRelations(ref) {
  return neighborsOf(ref).filter(({ relation }) => relation.relation_type === 'corporate_group' && relationStatus(relation) === 'confirmed');
}

function GroupMembers({ groupRef, onSelectCompany }) {
  const members = [...new Map(groupRelations(groupRef).filter(n => n.other.type === 'listed').map(n => [n.other.key, n.other])).values()];
  return <div style={{ fontSize: 12 }}>
    <p>収録している所属企業 {members.length}社。子会社の会員資格を通じて掲載している場合があります。同一グループへの所属は、企業間の資本関係を意味しません。</p>
    {members.map(ref => <button key={ref.key} className="company-row" onClick={() => onSelectCompany?.(ref.key)}>{nodeName(ref)}（{ref.key}） ↗</button>)}
  </div>;
}

function CompanyGroups({ companyRef, onSelectCompany }) {
  const groups = [...new Map(groupRelations(companyRef).filter(n => n.other.type === 'entity').map(n => [n.other.key, n.other])).values()];
  if (!groups.length) return null;
  return <section aria-label="グループ関係" style={{ marginTop: 16 }}>
    <h3 style={{ fontSize: 12 }}>グループ関係</h3>
    {groups.map(ref => <details key={ref.key} style={{ fontSize: 12, marginBottom: 8 }}><summary style={{ cursor: 'pointer' }}>{nodeName(ref)}</summary><GroupMembers groupRef={ref} onSelectCompany={onSelectCompany} /></details>)}
  </section>;
}

function CompanyDetail({ info, refObj, onSelectCompany }) {
  if (refObj.type === 'entity' && info.kind === 'group') return <>
    <Section title="企業グループ"><Field label="名称" value={info.name} /><Field label="確認元団体" value={info.organization} /><Field label="出典" value={info.url && <ExternalLink href={info.url}>会員一覧 ↗</ExternalLink>} /></Section>
    <GroupMembers groupRef={refObj} onSelectCompany={onSelectCompany} />
  </>;
  if (refObj.type === 'entity') {
    return (
      <>
        <Section title={info.identity_status === 'ambiguous_listed_name' ? '法人の特定が必要' : '非上場エンティティ'}>
          <Field label="名称" value={info.name} />
          <Field label="法人番号" value={info.corporate_number} />
          <Field label="Wikidata" value={info.wikidata_qid && <ExternalLink href={`https://www.wikidata.org/wiki/${info.wikidata_qid}`}>{info.wikidata_qid}</ExternalLink>} />
        </Section>
        <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{info.identity_status === 'ambiguous_listed_name' ? '同名の上場企業が複数あるため、名称だけでは証券コードを割り当てられません。関連する関係は要確認です。' : '収録上場企業以外の組織です。子会社・グループ等として関係先にのみ登場します。'}</div>
      </>
    );
  }
  return (
    <Section title="収録企業">
      {info.data_quality && <div role="note" style={{ padding: 10, marginBottom: 12, background: "#fff8e1", color: "#654b00", fontSize: 12 }}>
        情報元の違い・更新時期・自動抽出により、信頼度が低い項目があります。
        {info.data_quality.needs_review?.length > 0 && <div>不一致・未確認：{info.data_quality.needs_review.map(k => ({name:"名称", industry_33:"33業種", market_segment:"市場区分", listing_scope:"上場対象・基準日"}[k] ?? k)).join("、")}</div>}
        正確な上場状況・市場区分・業種は、<ExternalLink href="https://www.jpx.co.jp/markets/statistics-equities/misc/01.html">JPX公式の最新情報</ExternalLink>をご自身で確認してください。地方市場は各取引所の公式情報をご確認ください。
      </div>}
      <Field label="名称" value={info.name} />
      {info.name_edinet && info.name_edinet !== info.name && <>
        <Field label="EDINET掲載名" value={info.name_edinet} />
        <div style={{ fontSize: 11, color: "var(--text-2)", marginBottom: 8 }}>参考情報です。旧名称の場合があります。</div>
      </>}
      <Field label="EDINET読み" value={info.name_kana} />
      <Field label="別名" value={info.aliases?.length ? info.aliases.join('、') : null} />
      <Field label="英文名" value={info.name_en} />
      <Field label="証券コード" value={info.securities_code} />
      <Field label="市場区分" value={SEGMENT_JA[info.market_segment]} />
      <Field label="33業種" value={info.industry_33} />


      <Field label="法人番号" value={info.corporate_number} />
      <Field label="EDINET" value={info.edinet_code} />
      <Field label="所在地" value={info.address} />
      <Field label="Wikidata" value={info.wikidata_qid && <ExternalLink href={`https://www.wikidata.org/wiki/${info.wikidata_qid}`}>{info.wikidata_qid}</ExternalLink>} />
      <CompanyGroups companyRef={refObj} onSelectCompany={onSelectCompany} />
      <CompanySources sources={info.field_sources} collectedOn={info.data_quality?.as_of} />
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
      {r.verified && <Field label="検証" value="原本で確認済みの値" />}
      {r.conflicting_values?.length > 0 && <Field label="競合する値" value={r.conflicting_values.map((v) => pct(v)).join(' ／ ')} />}
      {r.conflict_same_period && <Field label="注意" value="同じ時点で異なる値の記載があります（履歴を確認してください）" />}
      {r.history?.length > 0 && (
        <details style={{ fontSize: 12, marginTop: 4 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--text-2)' }}>他の記載・過去の値 {r.history.length} 件</summary>
          <ul style={{ margin: '4px 0 0', paddingLeft: 16, color: 'var(--text-2)' }}>
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

export function EvidenceCard({ ev }) {
  const facts = ev.facts ?? {};
  const tier = evidenceTier(ev);
  const url = ev.url;
  const originalLabel = ev.source === 'edinet' ? 'EDINET で原本を開く' : ev.source === 'wikidata' ? 'Wikidata の項目を開く' : '公表資料を開く';
  return (
    <div className="card" style={{ background: 'var(--surface)', borderRadius: 8, padding: '8px 10px', marginBottom: 6, fontSize: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4, gap: 6, flexWrap: 'wrap' }}>
        <span style={{ color: 'var(--text)', fontWeight: 600 }}>{SOURCE_JA[ev.source] ?? ev.source}</span>
        <span>
          {tier && <Badge color={TIER_COLORS[tier] ?? '#475569'} title="出所の種別。抽出内容の正しさとは別です">{TIER_JA[tier] ?? tier}</Badge>}
          {ev.verification === 'verified' && <Badge color={STATUS_COLORS.confirmed}>原本確認</Badge>}
        </span>
      </div>
      {ev.support_status === 'needs_review' && <Field label="根拠の判定" value="要確認（確定関係の裏付け件数には含めません）" />}
      {ev.support_status === 'historical' && <Field label="根拠の判定" value="過去の関係（現在の関係の裏付け件数には含めません）" />}
      <Field label="基準日" value={dateOrUnknown(ev.as_of)} />
      <Field label="公表日" value={dateOrUnknown(ev.published ?? ev.date)} />
      <Field label="取得日" value={dateOrUnknown(ev.retrieved)} />
      {ev.origin === 'edinet_republication' && <Field label="元資料" value="有価証券報告書（企業サイト掲載）。寄与度ではEDINET由来として集計" />}
      {ev.reviewer === 'codex_primary_source_review' && <Field label="確認方法" value="AIによる資料との個別照合" />}
      {ev.reviewer === 'reviewed_same_document_offices' && <Field label="確認方法" value="AIが同じ公式プロフィールで照合した現任役職から、兼任する企業対を生成" />}
      {ev.property && <Field label="項目" value={{ affiliated: '関係会社の状況', shareholder: '大株主の状況', large_holding_report: '大量保有報告書（大株主の状況の注記）', customer: '主要な顧客' }[ev.property] ?? ev.property} />}
      {ev.classification && (
        <Field label="原本の分類" value={`${ev.classification}${ev.classification_source ? `（${{ section: '節見出し', row: 'ラベル行', column: '区分列', prefix: '行頭の表記', note: '注記', header: '見出しセル' }[ev.classification_source] ?? ev.classification_source}から）` : ''}`} />
      )}
      {ev.direction_source && <Field label="方向の根拠" value={{ cell: 'セル内の所有／被所有表記', header: '列見出し', classification: '分類（親会社・その他の関係会社）', default: '既定（提出会社が所有）' }[ev.direction_source] ?? ev.direction_source} />}
      {ev.raw_name && <Field label="資料上の相手名" value={ev.raw_name} />}
      {ev.table_ref && <Field label="資料内の位置" value={ev.table_ref} />}
      {ev.extraction?.reasons?.length > 0 && <Field label="要確認理由" value={ev.extraction.reasons.map((r) => reasonLabel(`ir:${r}`)).join('、')} />}
      {ev.source_check && <Field label="本文照合" value={ev.source_check.status === 'excerpt_found' ? '抽出根拠と本文の文字列一致を確認（関係の正しさは未検証）' : reasonLabel(`ir:source_${ev.source_check.status}`)} />}
      {ev.source_check?.checked_at && <Field label="照合日" value={ev.source_check.checked_at.slice(0, 10)} />}
      {ev.extraction?.retyped_from && <Field label="読み替え" value={`LLM の分類 ${RELATION_TYPES[ev.extraction.retyped_from]?.ja ?? ev.extraction.retyped_from} → 根拠文に基づき変更`} />}
      {(ev.source === 'ir_disclosure' || ev.property === 'contracts' || facts.deal_status) && <Field label="実行状態" value={{ agreed: '合意・予定', executed: '実行済み' }[facts.deal_status] ?? '未確認'} />}
      {facts.event_year && <Field label="時点" value={`${facts.event_year}年の出来事に言及`} />}
      {facts.person && <Field label="人物" value={facts.person} />}
      {(facts.role_at_filer || facts.role_at_counterparty) && <Field label="役職" value={[facts.role_at_filer && `提出会社: ${facts.role_at_filer}`, facts.role_at_counterparty && `相手: ${facts.role_at_counterparty}`].filter(Boolean).join(' ／ ')} />}
      {facts.contracting_party && <Field label="契約会社" value={facts.contracting_party} />}
      {facts.contract_date && <Field label="契約年月" value={facts.contract_date} />}
      {facts.organization && <Field label="団体" value={facts.organization} />}
      {url ? (
        <Field label="原本" value={<>{ev.doc_id && <span style={{ color: 'var(--text-2)', marginRight: 6 }}>{ev.doc_id}</span>}<ExternalLink href={url}>{originalLabel} ↗</ExternalLink></>} />
      ) : (
        <Field label="原本" value={ev.doc_id ? `書類ID ${ev.doc_id}（リンク情報なし。EDINET の書類検索で参照できます）` : 'リンク情報なし'} />
      )}
    </div>
  );
}

export function RelationDetail({ relation }) {
  const typeDef = RELATION_TYPES[relation.relation_type] ?? {};
  const color = CATEGORY_TEXT_COLORS[relation.category] ?? '#475569';
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
          <Badge color={STATUS_COLORS[status] ?? '#475569'} title={status === 'confirmed' ? '抽出ルールによる判定を通過した関係。個別の原本照合の有無は別に表示します' : status === 'needs_review' ? '出所の記載から関係タイプ・方向を確定できない関係' : '後続の開示で過去の状態になった関係'}>{relationStatusLabel(relation)}</Badge>
          <Badge color={verification?.status === 'verified' ? STATUS_COLORS.confirmed : '#475569'} title="抽出結果を原本と個別に照合したかどうか。照合者は根拠ごとに表示">
            {verification?.status === 'verified' ? `原本照合済み${verification.on ? `（${verification.on}）` : ''}` : '未検証（自動抽出）'}
          </Badge>
        </div>
        {status === 'needs_review' && relation.review_reasons?.length > 0 && (
          <Field label="要確認理由" value={relation.review_reasons.map(reasonLabel).join('、')} />
        )}
        {status === 'historical' && <Field label="有効期限" value={`${relation.valid_until ?? '不明'} まで${relation.superseded_by ? `（後続: ${relation.superseded_by}）` : ''}`} />}
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
        {relation.attributes?.persons?.length > 0 && <Field label="兼任者" value={relation.attributes.persons.map((p) => `${p.name}${p.status === 'historical' ? `［退任済み${p.valid_until ? `・${p.valid_until}` : ''}］` : p.status === 'needs_review' ? '［現任か要確認］' : ''}（${Object.entries(p.roles ?? {}).map(([code, role]) => `${nodeName({ type: 'listed', key: code })}: ${role}`).join('、')}）`).join(' ／ ')} />}
        {relation.attributes?.contract_date && <Field label="契約年月" value={relation.attributes.contract_date} />}
        {relation.attributes?.contract_kind && <Field label="契約の種類" value={relation.attributes.contract_kind} />}
        {relation.attributes?.member_via && <Field label="会員会社" value={`${relation.attributes.member_via}（上場親会社として表示）`} />}
      </Section>
      <Section title={`資料から抽出した情報・出典 ${evidence.length} 件`}>
        {loadState === 'loading' && detail === null && META.evidenceShards && <div style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 6 }}>原本情報を読み込み中…</div>}
        {loadState === 'error' && <div role="alert" style={{ fontSize: 12, color: 'var(--danger)', marginBottom: 6 }}>原本情報を取得できませんでした。通信状況を確認し、ページを再読み込みしてください。</div>}
        <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6 }}>JP Market Visが資料から抽出・整理した項目です。原文の引用ではありません。個別の条件や詳細は出典リンクから原本をご確認ください。</p>
        {evidence.map((ev, i) => <EvidenceCard key={i} ev={ev} />)}
        <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6 }}>
          「一次開示」は出所の種別で、抽出が正しいことを意味しません。「原本照合済み」は個別に照合した関係に付きます。AIによる照合は根拠ごとに明記します。
        </div>
      </Section>
    </>
  );
}

export default function DetailPanel({ selection, onClose, onSelectCompany }) {
  if (!selection) return null;
  return (
    <div className="detail-panel" role="region" aria-label="企業・関係の詳細" style={{ width: 320, minWidth: 320, height: '100%', overflowY: 'auto', borderLeft: '1px solid var(--border)', padding: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>詳細</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 14 }}>✕ 閉じる</button>
      </div>
      {selection.kind === 'node' && <CompanyDetail info={selection.info} refObj={selection.ref} onSelectCompany={onSelectCompany} />}
      {selection.kind === 'edge' && <RelationDetail relation={selection.relation} />}
    </div>
  );
}
