import test from 'node:test';
import assert from 'node:assert/strict';
import {loadDataset} from '../src/data/loadDataset.js';
import {versionedData} from '../build/versionedData.js';

test('startup bypasses stale fixed URLs and fetches the pinned dataset', async () => {
  const urls=[];
  const result=await loadDataset(async url => {
    urls.push(url);
    return {ok:true,json:async()=>({dataset_id:url.includes('/data/new/')?'new':'old'})};
  }, '/JP_Market_Vis/', 'new');
  assert.equal(result[0].dataset_id,'new');
  assert.deepEqual(urls,['/JP_Market_Vis/data/new/M4_companies.json','/JP_Market_Vis/data/new/M5_company_relations.json']);
});
test('a missing pinned file fails instead of silently using unrelated current data', async () => {
  await assert.rejects(loadDataset(async()=>({ok:false,status:404}), '/', 'new'),/404/);
});
test('even matching master files must match the version pinned in the application', async () => {
  await assert.rejects(loadDataset(async()=>({ok:true,json:async()=>({dataset_id:'old'})}), '/', 'new'),/更新中/);
});
test('build emits both masters at exactly the version injected into the app', () => {
  const plugin=versionedData();
  const id=JSON.parse(plugin.config().define.__DATASET_ID__);
  const emitted=[];
  plugin.generateBundle.call({emitFile:file=>emitted.push(file)});
  assert.equal(emitted.length,2);
  for(const file of emitted){
    assert.ok(file.fileName.startsWith(`data/${id}/`));
    assert.equal(JSON.parse(file.source).dataset_id,id);
  }
});
