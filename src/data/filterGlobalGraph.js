// Work with copies: the force simulation mutates its node/link objects.
export function filterGlobalGraph(graph, categories, minDegree) {
  const links = graph.links.filter((link) => categories.has(link.category));
  const degrees = new Map();
  for (const link of links) {
    for (const id of [link.source, link.target]) degrees.set(id, (degrees.get(id) ?? 0) + 1);
  }
  const nodes = graph.nodes.filter((node) => (degrees.get(node.id) ?? 0) >= minDegree)
    .map((node) => ({ ...node, degree: degrees.get(node.id) }));
  const ids = new Set(nodes.map((node) => node.id));
  return { nodes, links: links.filter((link) => ids.has(link.source) && ids.has(link.target)).map((link) => ({ ...link })) };
}
