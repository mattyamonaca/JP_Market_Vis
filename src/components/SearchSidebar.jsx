import React, { useMemo, useState } from 'react';
import { HUB_RANKING, SEGMENT_JA, searchCompanies } from '../data/graph.js';

const rowStyle = (active) => ({
  padding: '8px 10px',
  borderRadius: 8,
  cursor: 'pointer',
  background: active ? 'rgba(250, 204, 21, 0.12)' : 'transparent',
  border: active ? '1px solid rgba(250, 204, 21, 0.4)' : '1px solid transparent',
  marginBottom: 2,
});

export default function SearchSidebar({ selectedCode, onSelect }) {
  const [query, setQuery] = useState('');

  const results = useMemo(() => {
    if (query.trim()) return searchCompanies(query, 40);
    return HUB_RANKING.slice(0, 40);
  }, [query]);

  return (
    <div
      className="search-sidebar"
      style={{
        width: 280,
        minWidth: 280,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        borderRight: '1px solid #1e293b',
        background: 'rgba(15, 23, 42, 0.95)',
      }}
    >
      <div style={{ padding: 12 }}>
        <input
          aria-label="企業名・証券コードで検索"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="企業名・証券コードで検索"
          style={{
            width: '100%',
            padding: '9px 12px',
            borderRadius: 8,
            border: '1px solid #334155',
            background: '#1e293b',
            color: '#f1f5f9',
            fontSize: 14,
            outline: 'none',
          }}
        />
        <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 8 }}>
          {query.trim() ? `検索結果 ${results.length} 件` : '関係数ランキング（上位40社）'}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 12px' }}>
        {results.map(({ code, company, degree }, i) => (
          <button
            className="company-row"
            aria-pressed={code === selectedCode}
            key={code}
            style={rowStyle(code === selectedCode)}
            onClick={() => onSelect(code)}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: '#f1f5f9' }}>
                {!query.trim() && (
                  <span style={{ color: '#94a3b8', marginRight: 6, fontSize: 12 }}>{i + 1}.</span>
                )}
                {company.name}
              </span>
              {degree > 0 && (
                <span style={{ fontSize: 12, color: '#facc15', whiteSpace: 'nowrap', marginLeft: 6 }}>
                  {degree}件
                </span>
              )}
            </div>
            <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 2 }}>
              {code} ・ {SEGMENT_JA[company.market_segment]} ・ {company.industry_17}
            </div>
          </button>
        ))}
        {results.length === 0 && (
          <div style={{ padding: 16, color: '#94a3b8', fontSize: 12, textAlign: 'center' }}>
            該当する企業がありません
          </div>
        )}
      </div>
    </div>
  );
}
