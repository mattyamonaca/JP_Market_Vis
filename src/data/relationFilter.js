// 関係一覧の絞り込み。企業コードによる導線（companyCode）は端点の完全一致で、自由入力の部分一致検索（query）とは別に適用する
import { nodeName, relationStatus } from './graph.js';

export const normalizeText = (s) => (s ?? '').normalize('NFKC').toLowerCase().replace(/[\s　]+/g, '');

export function touchesListed(rel, code) {
  return (rel.source.type === 'listed' && rel.source.key === code) || (rel.target.type === 'listed' && rel.target.key === code);
}

export function filterRelations(relations, { category = 'all', relType = 'all', status = 'all', query = '', companyCode = null } = {}) {
  const q = normalizeText(query);
  return relations.filter((rel) => {
    if (companyCode && !touchesListed(rel, companyCode)) return false;
    if (category !== 'all' && rel.category !== category) return false;
    if (relType !== 'all' && rel.relation_type !== relType) return false;
    if (status !== 'all' && relationStatus(rel) !== status) return false;
    if (q) {
      const s = normalizeText(nodeName(rel.source));
      const t = normalizeText(nodeName(rel.target));
      const sCode = rel.source.type === 'listed' && rel.source.key.toLowerCase().includes(q);
      const tCode = rel.target.type === 'listed' && rel.target.key.toLowerCase().includes(q);
      if (!s.includes(q) && !t.includes(q) && !sCode && !tCode) return false;
    }
    return true;
  });
}
