import React from 'react';

const FIELDS = { name: '企業名', market_segment: '市場区分', industry_33: '33業種' };

export default function CompanySources({ sources = {}, collectedOn }) {
  return <section aria-label="企業情報の出典" style={{ fontSize: 12, marginTop: 16 }}>
    <h3 style={{ fontSize: 12, marginBottom: 8 }}>企業情報の出典</h3>
    {Object.entries(FIELDS).map(([field, label]) => {
      const source = sources[field];
      const url = /^https?:\/\//i.test(source?.source_url ?? '') ? source.source_url : null;
      return <div key={field} style={{ marginBottom: 12, overflowWrap: 'anywhere' }}>
        <strong>{label}</strong>{'：'}
        {url ? <a href={url} target="_blank" rel="noreferrer">出典を開く ↗</a> : '出典未確認'}
        {source && <>
          <div>資料日：{source.document_date || '記載なし・不明'}</div>
          <div>取得・確認日：{source.retrieved || collectedOn || '不明'}</div>
          {source.verification === 'machine_extracted' && <div>自動抽出（原本照合前）</div>}
        </>}
      </div>;
    })}
    <p style={{ color: 'var(--text-2)' }}>取得・確認日は資料の作成日や情報の有効日を意味しません。</p>
  </section>;
}
