import React, { useMemo, useState, useEffect } from 'react';
import {
  CATEGORY_TEXT_COLORS,
  CATEGORY_JA,
  COMPANIES,
  RELATIONS,
  RELATION_TYPES,
  STATUS_COLORS,
  STATUS_JA,
  nodeName,
  relationStatus,
} from '../data/graph.js';
import { filterRelations } from '../data/relationFilter.js';
import { RelationDetail } from './DetailPanel.jsx';

const MAX_ROWS = 300;

const selectStyle = {
  padding: '7px 10px',
  borderRadius: 6,
  border: '1px solid var(--border-strong)',
  background: 'var(--bg)',
  color: 'var(--text)',
  fontSize: 13,
};


export default function RelationTable({ request = null }) {
  const [category, setCategory] = useState('all');
  const [relType, setRelType] = useState('all');
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  // 企業コードによる絞り込み（導線から来たとき）。自由入力の部分一致検索とは別に、端点の完全一致で適用する
  const [companyCode, setCompanyCode] = useState(null);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(null);
  // 検索条件が変わったらページ位置と選択を先頭に戻す
  useEffect(() => { setPage(0); setSelected(null); }, [category, relType, status, query, companyCode]);
  // 個別グラフの省略案内などから「この企業で絞る」依頼が来たら条件を引き継ぐ
  useEffect(() => {
    if (!request?.code) return;
    setCategory('all');
    setRelType('all');
    setStatus('all');
    setQuery('');
    setCompanyCode(request.code);
  }, [request]);

  const typeOptions = useMemo(() => {
    const types = Object.entries(RELATION_TYPES);
    return category === 'all' ? types : types.filter(([, t]) => t.category === category);
  }, [category]);

  const filtered = useMemo(
    () => filterRelations(RELATIONS, { category, relType, status, query, companyCode }),
    [category, relType, status, query, companyCode],
  );

  return (
    <div className="table-view" style={{ display: 'flex', flex: 1, minHeight: 0 }}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 10, padding: 14, alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            aria-label="関係カテゴリ"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setRelType('all');
            }}
            style={selectStyle}
          >
            <option value="all">全カテゴリ</option>
            {Object.entries(CATEGORY_JA).map(([k, ja]) => (
              <option key={k} value={k}>
                {ja}
              </option>
            ))}
          </select>
          <select aria-label="関係タイプ" value={relType} onChange={(e) => setRelType(e.target.value)} style={selectStyle}>
            <option value="all">全タイプ</option>
            {typeOptions.map(([k, t]) => (
              <option key={k} value={k}>
                {t.ja}
              </option>
            ))}
          </select>
          <select aria-label="関係の状態" value={status} onChange={(e) => setStatus(e.target.value)} style={selectStyle}>
            <option value="all">全状態</option>
            {Object.entries(STATUS_JA).map(([k, ja]) => (
              <option key={k} value={k}>{ja}</option>
            ))}
          </select>
          <input
            aria-label="企業名・証券コードで関係を検索"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="企業名・証券コードで検索"
            style={{ ...selectStyle, width: 220 }}
          />
          {companyCode && (
            <span className="company-filter-chip" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, padding: '4px 8px', borderRadius: 999, border: '1px solid var(--accent)', color: 'var(--accent)', background: 'var(--accent-bg)' }}>
              企業: {COMPANIES[companyCode]?.name ?? companyCode}（{companyCode}）
              <button type="button" aria-label="企業の絞り込みを解除" onClick={() => setCompanyCode(null)} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', padding: 0, fontSize: 12 }}>✕</button>
            </span>
          )}
          <span style={{ fontSize: 12, color: 'var(--text-2)' }}>
            {filtered.length.toLocaleString()} 件
          </span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px' }}>
          <table className="data-table">
            <thead>
              <tr style={{ position: 'sticky', top: 0, background: 'var(--bg)', zIndex: 1 }}>
                {['ID', 'From（source）', '関係タイプ', 'To（target）', '比率', '状態', '出所'].map((h) => (
                  <th key={h}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.slice(page * MAX_ROWS, (page + 1) * MAX_ROWS).map((rel) => {
                const color = CATEGORY_TEXT_COLORS[rel.category] ?? 'var(--text-2)';
                const ratio = rel.attributes?.ownership_ratio ?? rel.attributes?.sales_ratio;
                const isSel = selected?.relation_id === rel.relation_id;
                return (
                  <tr
                    key={rel.relation_id}
                    className={isSel ? 'selected' : undefined}
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter') setSelected(isSel ? null : rel); }}
                    onClick={() => setSelected(isSel ? null : rel)}
                  >
                    <td style={{ color: 'var(--text-2)' }}>{rel.relation_id}</td>
                    <td>
                      {nodeName(rel.source)}
                      {rel.source.type === 'listed' && (
                        <span style={{ color: 'var(--text-2)', marginLeft: 4 }}>({rel.source.key})</span>
                      )}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span className="pill" style={{ background: `${color}14`, color, fontWeight: 500 }}>
                        {RELATION_TYPES[rel.relation_type]?.ja ?? rel.relation_type}
                        {rel.directed ? ' →' : ' ↔'}
                      </span>
                    </td>
                    <td>
                      {nodeName(rel.target)}
                      {rel.target.type === 'listed' && (
                        <span style={{ color: 'var(--text-2)', marginLeft: 4 }}>({rel.target.key})</span>
                      )}
                    </td>
                    <td style={{ color: 'var(--text-2)' }}>
                      {ratio != null ? `${(ratio * 100).toFixed(1)}%` : '—'}
                    </td>
                    <td style={{ whiteSpace: 'nowrap' }}>
                      <span style={{ color: STATUS_COLORS[relationStatus(rel)] ?? 'var(--text-2)', fontWeight: 600 }}>{STATUS_JA[relationStatus(rel)] ?? relationStatus(rel)}</span>
                      {rel.verification?.status === 'verified' && <span title="原本で検証済み" style={{ color: 'var(--status-confirmed)', marginLeft: 4 }}>✓</span>}
                    </td>
                    <td style={{ color: 'var(--text-2)' }}>
                      {[...new Set(rel.evidence.map((e) => e.source))].join(', ')}
                      {rel.evidence.some((e) => e.as_of) && <span style={{ marginLeft: 4 }}>{rel.evidence.map((e) => e.as_of).filter(Boolean).sort().at(-1)}</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!filtered.length && <p role="status">条件に一致する関係はありません。</p>}
        </div>
        <div className="pagination">
          <button disabled={page === 0} onClick={() => setPage(page - 1)}>← 前へ</button>
          <span>{page + 1} / {Math.max(1, Math.ceil(filtered.length / MAX_ROWS))} ページ</span>
          <button disabled={(page + 1) * MAX_ROWS >= filtered.length} onClick={() => setPage(page + 1)}>次へ →</button>
        </div>
      </div>
      {selected && (
        <div
          className="detail-panel"
          style={{
            width: 320,
            minWidth: 320,
            overflowY: 'auto',
            borderLeft: '1px solid var(--border)',
            padding: 16,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button
              onClick={() => setSelected(null)}
              style={{ background: 'none', border: 'none', color: 'var(--text-2)', cursor: 'pointer', fontSize: 14 }}
            >
              ✕ 閉じる
            </button>
          </div>
          <RelationDetail relation={selected} />
        </div>
      )}
    </div>
  );
}
