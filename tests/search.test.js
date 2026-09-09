import test from 'node:test';
import assert from 'node:assert/strict';
import { companySearchKeys, createSearcher, toHiragana } from '../src/data/search.js';

const companies = {
  7203: { name: 'トヨタ自動車', name_en: 'TOYOTA MOTOR CORPORATION', name_kana: 'トヨタジドウシャカブシキカイシャ', aliases: ['トヨタ'] },
  9533: { name: '東邦瓦斯', name_en: 'TOHO GAS CO.,LTD.', name_kana: 'トウホウガスカブシキガイシャ', aliases: ['東邦ガス'] },
  6758: { name: 'ソニーグループ', name_en: 'SONY GROUP CORPORATION', aliases: ['ソニー'] },
  7512: { name: 'イオン北海道', name_kana: 'イオンホッカイドウカブシキガイシャ' },
};
const search = createSearcher(companies, (code) => ({ 7203: 5, 9533: 3, 6758: 4, 7512: 1 })[code] ?? 0);

test('readings are folded to hiragana without the legal form', () => {
  assert.equal(toHiragana('トヨタジドウシャカブシキカイシャ'), 'とよたじどうしゃ');
  assert.ok(companySearchKeys(companies[9533]).includes('とうほうがす'));
});
test('aliases, readings and full-width codes find the intended company', () => {
  assert.equal(search('東邦ガス')[0].code, '9533');
  assert.equal(search('とよた')[0].code, '7203');
  assert.equal(search('トヨタ')[0].code, '7203');
  assert.equal(search('７２０３')[0].code, '7203');
  assert.equal(search('ソニー')[0].code, '6758');
  assert.ok(search('いおん').some((r) => r.code === '7512'));
  assert.deepEqual(search('this-company-does-not-exist-1234'), []);
  assert.deepEqual(search('   '), []);
});
test('companies without readings or aliases still match by name', () => {
  const s = createSearcher({ 1301: { name: '極洋' } }, () => 0);
  assert.equal(s('極洋')[0].code, '1301');
});
