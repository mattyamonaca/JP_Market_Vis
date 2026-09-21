import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceContribution } from '../src/data/sourceContribution.js';

test('source contribution excludes unverified excerpts, deduplicates evidence and reports overlap', () => {
  const base = { status: 'confirmed', source: { type: 'listed' }, target: { type: 'listed' } };
  const result = sourceContribution([
    { ...base, evidence: [{ source: 'edinet' }, { source: 'ir_disclosure', support_status: 'needs_review' }] },
    { ...base, evidence: [{ source: 'edinet' }, { source: 'issuer_website' }, { source: 'issuer_website' }] },
    { ...base, evidence: [{ source: 'official_release' }] },
    { ...base, status: 'needs_review', evidence: [{ source: 'official_release' }] },
    { ...base, target: { type: 'entity' }, evidence: [{ source: 'official_release' }] },
  ]);
  assert.deepEqual(result, { edinetOnly: 1, otherOnly: 1, both: 1, edinet: 2, other: 2 });
});

test('an issuer-hosted EDINET filing is not an independent origin', () => {
  const result = sourceContribution([{ status: 'confirmed', source: { type: 'listed' }, target: { type: 'listed' },
    evidence: [{ source: 'official_release', origin: 'edinet_republication' }] }]);
  assert.deepEqual(result, { edinetOnly: 1, otherOnly: 0, both: 0, edinet: 1, other: 0 });
});
