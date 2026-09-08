import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { filterGlobalGraph } from '../src/data/filterGlobalGraph.js';
const originalFetch = globalThis.fetch;
globalThis.fetch = async (url) => ({ ok: true, json: async () => JSON.parse(await readFile(new URL(`../public${url}`, import.meta.url), 'utf8')) });
const graph = await import('../src/data/graph.js');
const { buildEgoNetwork } = await import('../src/flow/egoNetwork.js');
globalThis.fetch = originalFetch;

test('every relation has valid endpoints, a unique ID and provenance', () => {
  const ids = new Set();
  for (const relation of graph.RELATIONS) {
    assert.ok(!ids.has(relation.relation_id), `duplicate ${relation.relation_id}`);
    ids.add(relation.relation_id);
    assert.ok(graph.nodeInfo(relation.source), `missing source ${relation.relation_id}`);
    assert.ok(graph.nodeInfo(relation.target), `missing target ${relation.relation_id}`);
    assert.ok(relation.evidence.length > 0);
    assert.ok(graph.RELATION_TYPES[relation.relation_type]);
  }
});
test('search normalizes full-width codes and Japanese spacing', () => {
  assert.equal(graph.searchCompanies('７２０３')[0].code, '7203');
  assert.ok(graph.searchCompanies('ト ヨ タ').some((r) => r.code === '7203'));
  assert.deepEqual(graph.searchCompanies('this-company-does-not-exist-1234'), []);
});
test('turning off every category removes ego edges', () => {
  const data = buildEgoNetwork('7203', { categoryFilter: new Set() });
  assert.equal(data.nodes.length, 1);
  assert.equal(data.edges.length, 0);
});
test('ego graph filters and endpoints remain consistent for all five categories', () => {
  for (const category of Object.keys(graph.CATEGORY_JA)) {
    const data = buildEgoNetwork('7203', { categoryFilter: new Set([category]) });
    const ids = new Set(data.nodes.map((n) => n.id));
    for (const edge of data.edges) {
      assert.equal(edge.data.relation.category, category);
      assert.ok(ids.has(edge.source) && ids.has(edge.target));
    }
  }
});
test('global graph includes precisely the listed-to-listed records', () => {
  assert.equal(graph.GLOBAL_GRAPH.links.length, graph.STATS.listedToListed);
  const ids = new Set(graph.GLOBAL_GRAPH.nodes.map((node) => node.id));
  for (const link of graph.GLOBAL_GRAPH.links) assert.ok(ids.has(link.source) && ids.has(link.target));
});
test('global filtering excludes disabled categories and copies simulation objects', () => {
  const data = filterGlobalGraph(graph.GLOBAL_GRAPH, new Set(['capital']), 5);
  const ids = new Set(data.nodes.map((node) => node.id));
  assert.ok(data.nodes.length > 0);
  for (const node of data.nodes) assert.ok(node.degree >= 5);
  for (const link of data.links) {
    assert.equal(link.category, 'capital');
    assert.ok(ids.has(link.source) && ids.has(link.target));
  }
  data.nodes[0].x = 100;
  data.links[0].source = data.nodes[0];
  assert.ok(graph.GLOBAL_GRAPH.nodes.every((node) => node.x === undefined));
  assert.ok(graph.GLOBAL_GRAPH.links.every((link) => typeof link.source === 'string'));
  assert.deepEqual(filterGlobalGraph(graph.GLOBAL_GRAPH, new Set(), 1), { nodes: [], links: [] });
});
