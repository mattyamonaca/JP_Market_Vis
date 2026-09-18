import test from 'node:test';
import assert from 'node:assert/strict';
import { HOVER_SCALE, LABEL_MIN_DEGREE, NODE_MIN_RADIUS, nodeRadius, ringWidth, shade, showsLabel } from '../src/data/nodeShape.js';

test('node radius grows with the square root of the degree and never drops below the minimum', () => {
  assert.equal(nodeRadius(0), NODE_MIN_RADIUS);
  assert.equal(nodeRadius(1), NODE_MIN_RADIUS);
  assert.equal(nodeRadius(undefined), NODE_MIN_RADIUS);
  assert.ok(nodeRadius(4) < nodeRadius(9));
  assert.ok(Math.abs(nodeRadius(100) / nodeRadius(25) - 2) < 1e-9); // 関係数 4 倍で半径 2 倍（面積 4 倍）
  assert.ok(nodeRadius(400) * HOVER_SCALE > nodeRadius(400));
});

test('the ring stays inside the circle at every size', () => {
  for (const degree of [0, 1, 3, 10, 50, 110, 400]) {
    const r = nodeRadius(degree);
    assert.ok(ringWidth(r) < r, `normal ring ${ringWidth(r)} < radius ${r}`);
    assert.ok(ringWidth(r, true) < r, `hover ring ${ringWidth(r, true)} < radius ${r}`);
    assert.ok(ringWidth(r, true) > ringWidth(r));
  }
});

test('shade darkens every channel by the given ratio', () => {
  assert.equal(shade('#ffffff', 0.5), '#808080');
  assert.equal(shade('#6b8fbb', 0), '#6b8fbb');
  assert.equal(shade('#6b8fbb', 1), '#000000');
});

test('labels appear for hubs and hover, and for smaller companies as the map is zoomed in', () => {
  assert.ok(showsLabel(LABEL_MIN_DEGREE, 0.5));
  assert.ok(showsLabel(1, 0.5, true));
  assert.ok(!showsLabel(50, 0.5));
  assert.ok(showsLabel(30, 1) && !showsLabel(29, 1));
  assert.ok(showsLabel(8, 2) && !showsLabel(7, 2));
  assert.ok(showsLabel(3, 4) && !showsLabel(2, 4));
  assert.ok(showsLabel(1, 8));
});
