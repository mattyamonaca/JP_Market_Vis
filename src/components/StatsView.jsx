import React from 'react';
import {
  CATEGORY_COLORS,
  CATEGORY_JA,
  HUB_RANKING,
  META,
  RELATION_TYPES,
  SEGMENT_JA,
  STATS,
  STATUS_JA,
  TIER_JA,
} from '../data/graph.js';

function Card({ label, value, sub, accent = '#38bdf8' }) {
  return (
    <div
      style={{
        background: '#1e293b',
        borderRadius: 12,
        padding: '16px 20px',
        minWidth: 170,
        border: '1px solid #334155',
      }}
    >
      <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: accent }}>{value.toLocaleString()}</div>
      {sub && <div style={{ fontSize: 12, color: '#94a3b8', marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function BarList({ title, items, colorOf, labelOf }) {
  const max = Math.max(...items.map(([, v]) => v), 1);
  return (
    <div style={{ background: '#1e293b', borderRadius: 12, padding: 18, border: '1px solid #334155' }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9', marginBottom: 12 }}>{title}</div>
      {items.map(([key, value]) => {
        const color = colorOf(key);
        return (
          <div key={key} style={{ marginBottom: 9 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
              <span style={{ color: '#cbd5e1' }}>{labelOf(key)}</span>
              <span style={{ color }}>{value.toLocaleString()}</span>
            </div>
            <div style={{ height: 6, background: '#0f172a', borderRadius: 3 }}>
              <div
                style={{
                  height: '100%',
                  width: `${(value / max) * 100}%`,
                  background: color,
                  borderRadius: 3,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function StatsView({ onSelectCompany }) {
  const typeItems = Object.entries(STATS.byType).sort((a, b) => b[1] - a[1]);
  const categoryItems = Object.entries(STATS.byCategory).sort((a, b) => b[1] - a[1]);
  const sourceItems = Object.entries(STATS.bySource).sort((a, b) => b[1] - a[1]);
  const tierItems = Object.entries(STATS.byTier).sort((a, b) => b[1] - a[1]);
  const statusItems = ['confirmed', 'needs_review', 'historical'].filter((k) => STATS.byStatus[k]).map((k) => [k, STATS.byStatus[k]]);

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: 20 }}>
      <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 20 }}>
        <Card label="収録上場企業" value={STATS.companies} sub="東証内国株式" accent="#facc15" />
        <Card label="確定関係" value={STATS.relations} sub={`うち上場間 ${STATS.listedToListed.toLocaleString()} 件 · 要確認・過去を除く`} />
        <Card label="要確認の関係" value={STATS.byStatus.needs_review ?? 0} sub="出所から関係タイプ・方向を確定できない" accent="#facc15" />
        <Card label="非上場エンティティ" value={STATS.entities} sub="子会社・グループ等" accent="#94a3b8" />
        <Card
          label="関係を持つ上場企業"
          value={STATS.companiesWithEdges}
          sub={`カバレッジ ${((STATS.companiesWithEdges / STATS.companies) * 100).toFixed(1)}%`}
          accent="#4ade80"
        />
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 320px), 1fr))',
          gap: 14,
          marginBottom: 20,
        }}
      >
        <BarList
          title="関係タイプ別エッジ数"
          items={typeItems}
          colorOf={(k) => CATEGORY_COLORS[RELATION_TYPES[k]?.category] ?? '#64748b'}
          labelOf={(k) => RELATION_TYPES[k]?.ja ?? k}
        />
        <BarList
          title="カテゴリ別エッジ数"
          items={categoryItems}
          colorOf={(k) => CATEGORY_COLORS[k] ?? '#64748b'}
          labelOf={(k) => CATEGORY_JA[k] ?? k}
        />
        <BarList
          title="エビデンス出所（確定関係）"
          items={sourceItems}
          colorOf={() => '#38bdf8'}
          labelOf={(k) => ({ wikidata: 'Wikidata', edinet: 'EDINET 有報', ir_disclosure: '企業IR（LLM抽出）', official_release: '公式開示（原本確認）' }[k] ?? k)}
        />
        <BarList
          title="出所の種別（抽出の正しさとは別）"
          items={tierItems}
          colorOf={(k) => ({ primary: '#7dd3fc', secondary: '#c4b5fd', llm_extraction: '#fdba74' }[k] ?? '#64748b')}
          labelOf={(k) => TIER_JA[k] ?? k}
        />
        <BarList
          title="関係の状態（全関係）"
          items={statusItems}
          colorOf={(k) => ({ confirmed: '#4ade80', needs_review: '#facc15', historical: '#94a3b8' }[k] ?? '#64748b')}
          labelOf={(k) => STATUS_JA[k] ?? k}
        />
      </div>

      <div style={{ background: '#1e293b', borderRadius: 12, padding: 18, border: '1px solid #334155', marginBottom: 20 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: '#f1f5f9', marginBottom: 12 }}>
          ハブ企業ランキング（関係数 上位20社）
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr>
              {['#', '企業名', 'コード', '市場', '17業種', '関係数'].map((h) => (
                <th
                  key={h}
                  style={{
                    textAlign: 'left',
                    padding: '6px 10px',
                    color: '#94a3b8',
                    borderBottom: '1px solid #334155',
                  }}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {HUB_RANKING.slice(0, 20).map(({ code, company, degree }, i) => (
              <tr
                key={code}
                tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter') onSelectCompany(code); }}
                onClick={() => onSelectCompany(code)}
                style={{ cursor: 'pointer' }}
                title="クリックで関係グラフを表示"
              >
                <td style={{ padding: '6px 10px', color: '#94a3b8', borderBottom: '1px solid #0f172a' }}>{i + 1}</td>
                <td style={{ padding: '6px 10px', color: '#38bdf8', borderBottom: '1px solid #0f172a' }}>
                  {company.name}
                </td>
                <td style={{ padding: '6px 10px', color: '#cbd5e1', borderBottom: '1px solid #0f172a' }}>{code}</td>
                <td style={{ padding: '6px 10px', color: '#cbd5e1', borderBottom: '1px solid #0f172a' }}>
                  {SEGMENT_JA[company.market_segment]}
                </td>
                <td style={{ padding: '6px 10px', color: '#cbd5e1', borderBottom: '1px solid #0f172a' }}>
                  {company.industry_17}
                </td>
                <td style={{ padding: '6px 10px', color: '#facc15', borderBottom: '1px solid #0f172a' }}>{degree}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="data-notes" style={{ fontSize: 14, color: '#94a3b8', paddingBottom: 16 }}>
        <h2>このデータについて</h2>
        <p>生成日 {META.generatedAt}。東証プライム・スタンダード・グロースの内国株式を対象にした収録データです。地方単独上場・ETF・REIT等は対象外です。</p>
        <p>全体マップは上場企業同士の関係のみを表示します。個別グラフと関係一覧には非上場の関係先も含みます。円の大きさは収録関係数で、株価や時価総額ではありません。位置・距離に地理的な意味はありません。</p>
        <p>出所：<a href="https://www.jpx.co.jp/markets/statistics-equities/misc/01.html" target="_blank" rel="noreferrer">JPX 東証上場銘柄一覧</a>、<a href="https://disclosure2.edinet-fsa.go.jp/" target="_blank" rel="noreferrer">金融庁 EDINET</a>、<a href="https://www.wikidata.org/" target="_blank" rel="noreferrer">Wikidata</a>、企業IR開示。出所別・信頼度別はエビデンス件数で、関係数とは一致しません。</p>
        <p>自動抽出・名寄せおよびLLMによるIR情報抽出を含み、誤り・欠落・古い関係が残る可能性があります。「一次開示」は出所の種別であり、抽出内容の正しさを保証するものではありません。人手で原本と照合した関係は {STATS.verified.toLocaleString()} 件で、詳細に「原本で検証済み」と表示します。基準日のある関係は {STATS.withAsOf.toLocaleString()} 件、それ以外は基準日不明として表示します。各関係の詳細と企業の最新開示を確認してください。</p>
      </div>
    </div>
  );
}
