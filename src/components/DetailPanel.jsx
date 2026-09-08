import React from 'react';
import {
  CATEGORY_COLORS,
  CATEGORY_JA,
  RELATION_TYPES,
  SEGMENT_JA,
  nodeName,
} from '../data/graph.js';

const CONFIDENCE_BADGE = {
  high: { label: '信頼度 high', color: '#4ade80' },
  medium: { label: '信頼度 medium', color: '#facc15' },
  low: { label: '低信頼', color: '#f87171' },
};

const SOURCE_JA = {
  wikidata: 'Wikidata',
  edinet: 'EDINET 有価証券報告書',
  ir_disclosure: '企業IRリリース（LLM抽出）',
};

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: '#64748b',
          textTransform: 'uppercase',
          letterSpacing: 1,
          marginBottom: 6,
        }}
      >
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
      <span style={{ color: '#94a3b8', minWidth: 84, flexShrink: 0 }}>{label}</span>
      <span style={{ color: '#f1f5f9', wordBreak: 'break-all' }}>{value}</span>
    </div>
  );
}

function CompanyDetail({ info, refObj }) {
  if (refObj.type === 'entity') {
    return (
      <>
        <Section title="非上場エンティティ">
          <Field label="名称" value={info.name} />
          <Field label="法人番号" value={info.corporate_number} />
          <Field
            label="Wikidata"
            value={
              info.wikidata_qid && (
                <a
                  href={`https://www.wikidata.org/wiki/${info.wikidata_qid}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: '#38bdf8' }}
                >
                  {info.wikidata_qid}
                </a>
              )
            }
          />
        </Section>
        <div style={{ fontSize: 12, color: '#64748b' }}>
          収録上場企業以外の組織です。子会社・グループ等として関係先にのみ登場します。
        </div>
      </>
    );
  }
  return (
    <Section title="上場企業">
      <Field label="名称" value={info.name} />
      <Field label="英文名" value={info.name_en} />
      <Field label="証券コード" value={info.securities_code} />
      <Field label="市場区分" value={SEGMENT_JA[info.market_segment]} />
      <Field label="33業種" value={info.industry_33} />
      <Field label="17業種" value={info.industry_17} />
      <Field label="規模区分" value={info.scale_category} />
      <Field label="法人番号" value={info.corporate_number} />
      <Field label="EDINET" value={info.edinet_code} />
      <Field label="所在地" value={info.address} />
      <Field
        label="Wikidata"
        value={
          info.wikidata_qid && (
            <a
              href={`https://www.wikidata.org/wiki/${info.wikidata_qid}`}
              target="_blank"
              rel="noreferrer"
              style={{ color: '#38bdf8' }}
            >
              {info.wikidata_qid}
            </a>
          )
        }
      />
    </Section>
  );
}

export function RelationDetail({ relation }) {
  const typeDef = RELATION_TYPES[relation.relation_type] ?? {};
  const color = CATEGORY_COLORS[relation.category] ?? '#64748b';
  return (
    <>
      <Section title={`関係エッジ ${relation.relation_id}`}>
        <div style={{ marginBottom: 8 }}>
          <span
            style={{
              display: 'inline-block',
              padding: '3px 10px',
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 700,
              background: `${color}22`,
              border: `1px solid ${color}`,
              color,
            }}
          >
            {CATEGORY_JA[relation.category]} / {typeDef.ja ?? relation.relation_type}
          </span>
        </div>
        <Field label="From" value={nodeName(relation.source)} />
        <Field label="To" value={nodeName(relation.target)} />
        <Field label="方向" value={relation.directed ? '有向' : '無向'} />
        <Field label="説明" value={typeDef.description} />
        {relation.attributes?.ownership_ratio != null && (
          <Field
            label="出資比率"
            value={`${(relation.attributes.ownership_ratio * 100).toFixed(2)}%`}
          />
        )}
        {relation.attributes?.sales_ratio != null && (
          <Field label="売上比率" value={`${(relation.attributes.sales_ratio * 100).toFixed(2)}%`} />
        )}
      </Section>
      <Section title="エビデンス（出所）">
        {relation.evidence.map((ev, i) => {
          const conf = CONFIDENCE_BADGE[ev.confidence] ?? CONFIDENCE_BADGE.low;
          return (
            <div
              key={i}
              style={{
                background: '#1e293b',
                borderRadius: 8,
                padding: '8px 10px',
                marginBottom: 6,
                fontSize: 12,
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ color: '#f1f5f9', fontWeight: 600 }}>
                  {SOURCE_JA[ev.source] ?? ev.source}
                </span>
                <span style={{ color: conf.color, fontSize: 12 }}>{conf.label}</span>
              </div>
              {ev.property && <Field label="プロパティ" value={ev.property} />}
              {ev.doc_id && <Field label="書類ID" value={ev.doc_id} />}
              {ev.quote && <Field label="根拠" value={`「${ev.quote}」`} />}
              {ev.url && (
                <Field
                  label="リリース"
                  value={
                    <a href={/^https?:\/\//i.test(ev.url) ? ev.url : undefined} target="_blank" rel="noreferrer" style={{ color: '#38bdf8' }}>
                      リリースを開く
                    </a>
                  }
                />
              )}
              {ev.date && <Field label="発表日" value={ev.date} />}
              <Field label="取得日" value={ev.retrieved} />
            </div>
          );
        })}
      </Section>
    </>
  );
}

export default function DetailPanel({ selection, onClose }) {
  if (!selection) return null;
  return (
    <div
      className="detail-panel"
      role="region"
      aria-label="企業・関係の詳細"
      style={{
        width: 320,
        minWidth: 320,
        height: '100%',
        overflowY: 'auto',
        borderLeft: '1px solid #1e293b',
        background: 'rgba(15, 23, 42, 0.97)',
        padding: 16,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: '#facc15' }}>詳細</span>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            color: '#94a3b8',
            cursor: 'pointer',
            fontSize: 14,
          }}
        >
          ✕ 閉じる
        </button>
      </div>
      {selection.kind === 'node' && (
        <CompanyDetail info={selection.info} refObj={selection.ref} />
      )}
      {selection.kind === 'edge' && <RelationDetail relation={selection.relation} />}
    </div>
  );
}
