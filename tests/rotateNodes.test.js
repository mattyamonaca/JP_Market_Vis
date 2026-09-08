import test from 'node:test';
import assert from 'node:assert/strict';
import { rotateNodes } from '../src/data/rotateNodes.js';
const close = (a, b) => assert.ok(Math.abs(a - b) < 1e-9, `${a} != ${b}`);
test('rotation preserves center, distances, node references and pinning', () => {
  const a = { x: 10, y: 20, vx: 2, vy: 0, fx: 10, fy: 20 };
  const b = { x: 30, y: 20 };
  const link = { source: a, target: b };
  rotateNodes([a, b], Math.PI / 2);
  close(a.x, 20); close(a.y, 10); close(b.x, 20); close(b.y, 30);
  close(Math.hypot(a.x - b.x, a.y - b.y), 20);
  close(a.fx, a.x); close(a.fy, a.y); close(a.vx, 0); close(a.vy, 2);
  assert.equal(link.source, a); assert.equal(b.fx, undefined);
  rotateNodes([a, b], -Math.PI / 2);
  close(a.x, 10); close(a.y, 20); close(b.x, 30); close(b.y, 20);
});
test('empty and not-yet-positioned nodes remain safe', () => {
  const node = { id: 'pending' };
  rotateNodes([], Math.PI); rotateNodes([node], Math.PI);
  assert.deepEqual(node, { id: 'pending' });
});
