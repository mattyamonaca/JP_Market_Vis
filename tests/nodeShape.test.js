import test from 'node:test';
import assert from 'node:assert/strict';
import { isInsideNodeCircle, keepCircleHits } from '../src/data/nodeShape.js';

test('UV points inside the circle hit, the transparent corners do not', () => {
  assert.ok(isInsideNodeCircle({ x: 0.5, y: 0.5 }));
  assert.ok(isInsideNodeCircle({ x: 0.5 + 0.35, y: 0.5 + 0.35 })); // 距離 0.495 < 0.5
  assert.ok(!isInsideNodeCircle({ x: 0.5 + 0.36, y: 0.5 + 0.36 })); // 距離 0.509 > 0.5
  assert.ok(!isInsideNodeCircle({ x: 0.02, y: 0.02 })); // 四隅
  assert.ok(!isInsideNodeCircle({ x: 0.98, y: 0.02 }));
  assert.ok(!isInsideNodeCircle(undefined));
});

test('keepCircleHits removes only this sprite corner hits and keeps earlier intersections', () => {
  const other = { uv: { x: 0.01, y: 0.01 }, object: 'earlier' };
  const hits = [other, { uv: { x: 0.5, y: 0.5 } }, { uv: { x: 0.05, y: 0.95 } }, { uv: undefined }];
  keepCircleHits(hits, 1);
  assert.deepEqual(hits.map((h) => h.object ?? 'sprite'), ['earlier', 'sprite']);
  assert.deepEqual(hits[1].uv, { x: 0.5, y: 0.5 });
});
