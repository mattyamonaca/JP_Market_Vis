// Count each supported relation once; repeated excerpts/URLs do not add weight.
export function sourceContribution(relations) {
  const counts = { edinetOnly: 0, otherOnly: 0, both: 0 };
  for (const r of relations) {
    if (r.status !== 'confirmed' || r.source.type !== 'listed' || r.target.type !== 'listed') continue;
    const sources = new Set(r.evidence.filter(e => (e.support_status ?? 'confirmed') === 'confirmed').map(e => e.origin === 'edinet_republication' ? 'edinet' : e.source));
    const edinet = sources.has('edinet');
    const other = [...sources].some(s => s !== 'edinet');
    if (edinet && other) counts.both++;
    else if (edinet) counts.edinetOnly++;
    else if (other) counts.otherOnly++;
  }
  return { ...counts, edinet: counts.edinetOnly + counts.both, other: counts.otherOnly + counts.both };
}
