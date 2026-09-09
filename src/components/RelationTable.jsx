import React, { useMemo, useState, useEffect } from 'react';
import {
  CATEGORY_COLORS,
  CATEGORY_JA,
  RELATIONS,
  RELATION_TYPES,
  STATUS_JA,
  nodeName,
  relationStatus,
} from '../data/graph.js';

const STATUS_COLOR = { confirmed: '#4ade80', needs_review: '#facc15', historical: '#94a3b8' };
import { RelationDetail } from './DetailPanel.jsx';

const MAX_ROWS = 300;

const selectStyle = {
  padding: '7px 10px',
  borderRadius: 8,
  border: '1px solid #334155',
  background: '#1e293b',
  color: '#f1f5f9',
  fontSize: 12,
  outline: 'none',
};

const normalize = (s) => (s ?? '').normalize('NFKC').toLowerCase().replace(/[\s　]+/g, '');

export default function RelationTable({ request = null }) {
  const [category, setCategory] = useState('all');
  const [relType, setRelType] = useState('all');
  const [status, setStatus] = useState('all');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(null);
  // 検索条件が変わったらページ位置と選択を先頭に戻す
  useEffect(() => { setPage(0); setSelected(null); }, [category, relType, status, query]);
  // 個別グラフの省略案内などから「この企業で絞る」依頼が来たら条件を引き継ぐ
  useEffect(() => {
    if (!request?.code) return;
    setCategory('all');
    setRelType('all');
    setStatus('all');
    setQuery(request.code);
  }, [request]);

  const typeOptions = useMemo(() => {
    const types = Object.entries(RELATION_TYPES);
    return category === 'all' ? types : types.filter(([, t]) => t.category === category);
  }, [category]);

  const filtered = useMemo(() => {
    const q = normalize(query);
    return RELATIONS.filter((rel) => {
      if (category !== 'all' && rel.category !== category) return false;
      if (relType !== 'all' && rel.relation_type !== relType) return false;
      if (status !== 'all' && relationStatus(rel) !== status) return false;
      if (q) {
        const s = normalize(nodeName(rel.source));
        const t = normalize(nodeName(rel.target));
        if (!s.includes(q) && !t.includes(q) && !rel.source.key.toLowerCase().includes(q) && !rel.target.key.toLowerCase().includes(q)) return false;
      }
      return true;
    });
  }, [category, relType, status, query]);

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
          <span style={{ fontSize: 12, color: '#64748b' }}>
            {filtered.length.toLocaleString()} 件
          </span>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 14px 14px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ position: 'sticky', top: 0, background: '#0f172a', zIndex: 1 }}>
                {['ID', 'From（source）', '関係タイプ', 'To（target）', '比率', '状態', '出所'].map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: 'left',
                      padding: '8px 10px',
                      color: '#64748b',
                      borderBottom: '1px solid #334155',
                      fontWeight: 600,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.slice(page * MAX_ROWS, (page + 1) * MAX_ROWS).map((rel) => {
                const color = CATEGORY_COLORS[rel.category];
                const ratio = rel.attributes?.ownership_ratio ?? rel.attributes?.sales_ratio;
                const isSel = selected?.relation_id === rel.relation_id;
                return (
                  <tr
                    key={rel.relation_id}
                    tabIndex={0}
                    onKeyDown={(e) => { if (e.key === 'Enter') setSelected(isSel ? null : rel); }}
                    onClick={() => setSelected(isSel ? null : rel)}
                    style={{
                      cursor: 'pointer',
                      background: isSel ? 'rgba(250, 204, 21, 0.08)' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '7px 10px', color: '#64748b', borderBottom: '1px solid #1e293b' }}>
                      {rel.relation_id}
                    </td>
                    <td style={{ padding: '7px 10px', color: '#f1f5f9', borderBottom: '1px solid #1e293b' }}>
                      {nodeName(rel.source)}
                      {rel.source.type === 'listed' && (
                        <span style={{ color: '#64748b', marginLeft: 4 }}>({rel.source.key})</span>
                      )}
                    </td>
                    <td style={{ padding: '7px 10px', borderBottom: '1px solid #1e293b', whiteSpace: 'nowrap' }}>
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: 999,
                          fontSize: 12,
                          background: `${color}22`,
                          border: `1px solid ${color}`,
                          color,
                        }}
                      >
                        {RELATION_TYPES[rel.relation_type]?.ja ?? rel.relation_type}
                        {rel.directed ? ' →' : ' ↔'}
                      </span>
                    </td>
                    <td style={{ padding: '7px 10px', color: '#f1f5f9', borderBottom: '1px solid #1e293b' }}>
                      {nodeName(rel.target)}
                      {rel.target.type === 'listed' && (
                        <span style={{ color: '#64748b', marginLeft: 4 }}>({rel.target.key})</span>
                      )}
                    </td>
                    <td style={{ padding: '7px 10px', color: '#cbd5e1', borderBottom: '1px solid #1e293b' }}>
                      {ratio != null ? `${(ratio * 100).toFixed(1)}%` : '—'}
                    </td>
                    <td style={{ padding: '7px 10px', borderBottom: '1px solid #1e293b', whiteSpace: 'nowrap' }}>
                      <span style={{ color: STATUS_COLOR[relationStatus(rel)] ?? '#94a3b8' }}>{STATUS_JA[relationStatus(rel)] ?? relationStatus(rel)}</span>
                      {rel.verification?.status === 'verified' && <span title="原本で検証済み" style={{ color: '#4ade80', marginLeft: 4 }}>✓</span>}
                    </td>
                    <td style={{ padding: '7px 10px', color: '#94a3b8', borderBottom: '1px solid #1e293b' }}>
                      {[...new Set(rel.evidence.map((e) => e.source))].join(', ')}
                      {rel.evidence.some((e) => e.as_of) && <span style={{ marginLeft: 4, color: '#a8b7cb' }}>{rel.evidence.map((e) => e.as_of).filter(Boolean).sort().at(-1)}</span>}
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
            borderLeft: '1px solid #1e293b',
            padding: 16,
            background: 'rgba(15, 23, 42, 0.97)',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
            <button
              onClick={() => setSelected(null)}
              style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: 14 }}
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
