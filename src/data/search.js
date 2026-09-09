// 企業検索の索引（Issue #4）。
// 名称・英文名・証券コードに加え、生成側（pipeline/aliases.json）で確認した別名 `aliases` と
// EDINET コードリストのヨミ `name_kana` を索引にする。読みはひらがなに畳み込んで比較するので、
// 「とよた」「トヨタ」のどちらでもトヨタ自動車に一致する。
const LEGAL_KANA = /カブシキ(カイシャ|ガイシャ)|ユウゲン(カイシャ|ガイシャ)|ゴウドウ(カイシャ|ガイシャ)/g;

export const normalizeText = (s) => (s ?? '').normalize('NFKC').toLowerCase().replace(/[\s　・･\-－—–]+/g, '');

// カタカナ → ひらがな（長音・空白を除く）
export function toHiragana(s) {
  return (s ?? '')
    .normalize('NFKC')
    .replace(LEGAL_KANA, '')
    .replace(/[\s　・･\-－ー]+/g, '')
    .replace(/[ァ-ヶ]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0x60))
    .toLowerCase();
}

// 1 社分の照合キー（重複除去済み）
export function companySearchKeys(company) {
  const keys = new Set();
  for (const s of [company.name, company.name_en, company.name_edinet, ...(company.aliases ?? [])]) {
    const k = normalizeText(s);
    if (k) keys.add(k);
    const h = toHiragana(s);
    if (h && h !== k) keys.add(h);
  }
  const kana = toHiragana(company.name_kana);
  if (kana) keys.add(kana);
  return [...keys];
}

// クエリを照合用に正規化。カタカナ・ひらがなの両方で試すため 2 種類返す
export function queryKeys(query) {
  const q = normalizeText(query);
  const h = toHiragana(query);
  return [...new Set([q, h].filter(Boolean))];
}

export function createSearcher(companies, degreeOf) {
  const index = Object.entries(companies).map(([code, company]) => ({
    code,
    company,
    keys: companySearchKeys(company),
  }));
  return function searchCompanies(query, limit = 30) {
    const qs = queryKeys(query);
    if (!qs.length) return [];
    const hits = [];
    for (const { code, company, keys } of index) {
      const codeHit = qs.some((q) => code.toLowerCase().includes(q));
      const keyHit = keys.some((k) => qs.some((q) => k.includes(q)));
      if (codeHit || keyHit) {
        hits.push({ code, company, degree: degreeOf(code) });
      }
    }
    return hits.sort((a, b) => b.degree - a.degree).slice(0, limit);
  };
}
