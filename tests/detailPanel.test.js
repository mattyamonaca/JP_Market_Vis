import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import React from 'react';
import { renderToString } from 'react-dom/server';
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url) => ({ ok: true, json: async () => JSON.parse(await readFile(new URL(`../public${url}`, import.meta.url), 'utf8')) });
const { RelationDetail, EvidenceCard, mergeRatio } = await import('../src/components/DetailPanel.jsx');
globalThis.fetch = originalFetch;

const relation = (attributes) => ({
  relation_id: 'R0000001', source: { type: 'listed', key: '8267' }, target: { type: 'listed', key: '7512' },
  relation_type: 'parent_subsidiary', category: 'capital', directed: true, status: 'confirmed', attributes,
  evidence: [{ source: 'edinet', tier: 'primary', as_of: '2026-02-28' }],
});
// 初期描画（シャード取得前・取得失敗時と同じ状態）を SSR で確認する
const html = (attrs) => renderToString(React.createElement(RelationDetail, { relation: relation(attrs) }));

test('evidence shows extracted facts and provenance without rendering legacy quotations', () => {
  const out = renderToString(React.createElement(EvidenceCard, { ev: {
    source: 'edinet', published: '2025-06-20', as_of: '2025-03-31',
    doc_id: 'S1', url: 'https://example.com/report', table_ref: 'table0/row2',
    quote: 'HIDDEN_QUOTE', relationship_note: 'HIDDEN_NOTE', note: 'HIDDEN_MEMO',
    extraction: { cue: 'HIDDEN_CUE' },
    facts: { deal_status: 'agreed', contract_date: '2025-02', person: '人物名', role_at_counterparty: '社外取締役' },
  } }));
  for (const text of ['合意・予定', '2025-02', '2025-06-20', '2025-03-31', '社外取締役', 'table0/row2', 'https://example.com/report']) assert.ok(out.includes(text));
  assert.doesNotMatch(out, /HIDDEN_|実行済み/);
  const missing = renderToString(React.createElement(EvidenceCard, { ev: { source: 'ir_disclosure' } }));
  assert.match(missing, /未確認/);
  assert.doesNotMatch(missing, /実行済み/);
});

test('known ratio in the core file is shown before the evidence shard loads', () => {
  const out = html({ ownership_ratio: 0.672, ownership: { kind: 'voting', scope: 'total', as_of: '2026-02-28' } });
  assert.match(out, /議決権 67\.20%/);
  assert.doesNotMatch(out, /合計不明/);
  assert.match(out, /2026-02-28/);
});
test('indirect-only and unresolved values stay unknown', () => {
  assert.match(html({ ownership: { kind: 'voting', scope: 'indirect_only', as_of: '2025-03-31' } }), /合計不明（間接のみ（合計不明））/);
  const out = html({ ownership: { kind: 'voting', scope: 'unresolved', as_of: '2025-03-31', conflicting_values: [0.2, 0.3] } });
  assert.match(out, /合計不明（同じ時点の記載が食い違い（未確定））/);
  assert.match(out, /20\.00% ／ 30\.00%/);
});
test('mergeRatio keeps detail breakdown and never invents a total for indirect-only', () => {
  const merged = mergeRatio({ kind: 'voting', scope: 'total', as_of: '2026-02-28' }, { value: 0.672, direct: 0.656, indirect: 0.016 }, 0.672);
  assert.equal(merged.direct, 0.656);
  assert.equal(mergeRatio({ kind: 'voting', scope: 'indirect_only' }, null, 0.5).value, undefined);
  assert.equal(mergeRatio(null, null, 0.4).value, 0.4);
  assert.equal(mergeRatio(null, null, null), null);
});

test('retired officer evidence and persons are explicitly distinguished from current ties', () => {
  const out = renderToString(React.createElement(EvidenceCard, { ev: { source: 'issuer_website', support_status: 'historical' } }));
  assert.match(out, /過去/);
  const r = { ...relation({ persons: [{ name: '退任者', roles: { '8267': '取締役' }, status: 'historical', valid_until: '2026-06-24' }, { name: '要確認者', roles: {}, status: 'needs_review' }] }), relation_type: 'interlocking_director' };
  const detail = renderToString(React.createElement(RelationDetail, { relation: r }));
  assert.match(detail, /退任済み/);
  assert.match(detail, /2026-06-24/);
  assert.match(detail, /現任か要確認/);
  assert.doesNotMatch(detail, /人手/);
});
