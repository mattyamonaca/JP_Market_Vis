import test from 'node:test';
import assert from 'node:assert/strict';
import { HOVER_SCALE, INSIDE_FONT, LABEL_MIN_DEGREE, NODE_MIN_RADIUS, insideLayout, nodeRadius, ringWidth, showsLabel, splitCandidates } from '../src/data/nodeShape.js';

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

test('labels appear for hubs and hover, and for smaller companies as the map is zoomed in', () => {
  assert.ok(showsLabel(LABEL_MIN_DEGREE, 0.5));
  assert.ok(showsLabel(1, 0.5, true));
  assert.ok(!showsLabel(50, 0.5));
  assert.ok(showsLabel(30, 1) && !showsLabel(29, 1));
  assert.ok(showsLabel(8, 2) && !showsLabel(7, 2));
  assert.ok(showsLabel(3, 4) && !showsLabel(2, 4));
  assert.ok(showsLabel(1, 8));
});

test('the name is written inside the circle only when it fits, with a font between 11 and 20px', () => {
  const measure12 = (text) => text.length * 12; // 1 文字 12px とみなす
  assert.deepEqual(insideLayout(60, '日本製鉄', measure12), { font: INSIDE_FONT.max, lines: ['日本製鉄'] }); // 大きい円: 20px（幅 80px ≤ 103px）
  assert.deepEqual(insideLayout(27, '日本製鉄', measure12), { font: INSIDE_FONT.min, lines: ['日本製鉄'] }); // 幅 44px ≤ 46.4px
  assert.deepEqual(insideLayout(20, '日本製鉄', measure12), { font: INSIDE_FONT.min, lines: ['日本', '製鉄'] }); // 1 行は入らないが 2 行なら入る
  assert.equal(insideLayout(12, '日本製鉄', measure12), null); // 2 行でも入らない
  const long = insideLayout(100, 'ＧＭＯインターネットグループ', measure12); // 1 行 280px は入らず、語の境界で 2 行に分けて 17px
  assert.deepEqual(long, { font: 17, lines: ['ＧＭＯインターネット', 'グループ'] });
  assert.equal(insideLayout(30, 'ＧＭＯインターネットグループ', measure12), null); // 小さい円は 2 行でも入らない
  const mid = insideLayout(40, '三菱電機', measure12);
  assert.ok(mid.font > INSIDE_FONT.min && mid.font < INSIDE_FONT.max && mid.lines.length === 1);
});

test('long names split at a separator or word boundary closest to the middle, then in the middle', () => {
  assert.deepEqual(splitCandidates('日本酸素ホールディングス')[0], ['日本酸素', 'ホールディングス']);
  assert.deepEqual(splitCandidates('ソニーグループ')[0], ['ソニー', 'グループ']);
  assert.deepEqual(splitCandidates('ＧＭＯインターネットグループ').slice(0, 2), [['ＧＭＯインターネット', 'グループ'], ['ＧＭＯ', 'インターネットグループ']]);
  const ufj = splitCandidates('三菱ＵＦＪフィナンシャル・グループ');
  assert.ok(ufj.some(([a, b]) => a === '三菱ＵＦＪフィナンシャル・' && b === 'グループ'));
  assert.deepEqual(splitCandidates('東京センチュリー'), [['東京セン', 'チュリー']]); // 語の境界がなければ中央
  for (const [a, b] of splitCandidates('三菱ＵＦＪフィナンシャル・グループ')) assert.equal((a + b).replace(/\s/g, ''), '三菱ＵＦＪフィナンシャル・グループ');
});
