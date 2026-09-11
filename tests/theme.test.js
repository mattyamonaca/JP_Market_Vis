// 白基調デザイン（Issue #23）の色トークンが、通常文字で WCAG 4.5:1 以上のコントラストを保つことを確認する
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const css = await readFile(new URL('../src/styles.css', import.meta.url), 'utf8');
const tokens = Object.fromEntries([...css.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2].toLowerCase()]));

const luminance = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
export const contrast = (a, b) => {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (l1 + 0.05) / (l2 + 0.05);
};

test('text tokens reach 4.5:1 on every background token', () => {
  const backgrounds = ['bg', 'surface', 'surface-2', 'accent-bg'];
  const texts = ['text', 'text-2', 'accent', 'danger', 'status-confirmed', 'status-needs-review', 'status-historical',
    'cat-capital-text', 'cat-transaction-text', 'cat-alliance-text', 'cat-personnel-text', 'cat-group-text'];
  for (const bg of backgrounds) {
    for (const fg of texts) {
      assert.ok(tokens[bg] && tokens[fg], `${bg}/${fg} defined`);
      const ratio = contrast(tokens[fg], tokens[bg]);
      assert.ok(ratio >= 4.5, `--${fg} on --${bg}: ${ratio.toFixed(2)}`);
    }
  }
  // --text-3 は補助用途（小さな文字には使わない）だが、白背景では 4.5:1 を満たす
  assert.ok(contrast(tokens['text-3'], tokens.bg) >= 4.5);
});

test('category, status, tier and segment text colors in graph.js match the tokens and pass on white', async () => {
  const src = await readFile(new URL('../src/data/graph.js', import.meta.url), 'utf8');
  const block = (name) => Object.fromEntries([...src.match(new RegExp(`export const ${name} = \\{([^}]*)\\}`, 's'))[1].matchAll(/(\w+): '(#[0-9a-f]{6})'/g)].map((m) => [m[1], m[2]]));
  const categoryText = block('CATEGORY_TEXT_COLORS');
  for (const [key, hex] of Object.entries(categoryText)) assert.equal(hex, tokens[`cat-${key}-text`], key);
  for (const hex of Object.values(block('STATUS_COLORS'))) assert.ok(contrast(hex, '#ffffff') >= 4.5, hex);
  for (const hex of Object.values(block('TIER_COLORS'))) assert.ok(contrast(hex, '#ffffff') >= 4.5, hex);
  for (const hex of Object.values(block('SEGMENT_COLORS'))) assert.ok(contrast(hex, '#ffffff') >= 4.5, hex);
});

test('the light theme has no dark-mode leftovers', () => {
  assert.match(css, /color-scheme:\s*light/);
  assert.equal(tokens.bg, '#ffffff');
});
