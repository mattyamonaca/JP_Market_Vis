// Work with copies: the force simulation mutates its node/link objects.
// 最小関係数は「選択カテゴリ内で、その企業が上場企業と持つ関係の数」に対して判定する。
// この数には閾値未満で非表示になった企業との関係も含まれるため、残った企業同士の線がない
// （表示線なし）の企業が出ることがある。isolated にその企業数を返し、UI で説明する。
export function filterGlobalGraph(graph, categories, minDegree) {
  const links = graph.links.filter((link) => categories.has(link.category));
  const degrees = new Map();
  for (const link of links) {
    for (const id of [link.source, link.target]) degrees.set(id, (degrees.get(id) ?? 0) + 1);
  }
  const nodes = graph.nodes.filter((node) => (degrees.get(node.id) ?? 0) >= minDegree)
    .map((node) => ({ ...node, degree: degrees.get(node.id) }));
  const ids = new Set(nodes.map((node) => node.id));
  const visibleLinks = links.filter((link) => ids.has(link.source) && ids.has(link.target)).map((link) => ({ ...link }));
  const linked = new Set();
  for (const link of visibleLinks) { linked.add(link.source); linked.add(link.target); }
  const isolated = nodes.filter((node) => !linked.has(node.id)).length;
  return { nodes, links: visibleLinks, isolated };
}
