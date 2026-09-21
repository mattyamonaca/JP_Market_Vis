import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Pin the application and both master files to one immutable dataset URL.
export function versionedData(publicDir = 'public') {
  const names = ['M4_companies.json', 'M5_company_relations.json'];
  const files = names.map(name => ({ name, source: readFileSync(resolve(publicDir, name), 'utf8') }));
  const ids = files.map(file => JSON.parse(file.source).dataset_id);
  if (!ids[0] || ids[0] !== ids[1] || !/^[a-f0-9]{24}$/.test(ids[0])) {
    throw new Error('Company and relation datasets must have the same valid dataset_id');
  }
  const revision = ids[0];
  return {
    name: 'versioned-data',
    config: () => ({ define: { __DATASET_ID__: JSON.stringify(revision) } }),
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = (req.url ?? '').split('?')[0];
        const file = files.find(file => path.endsWith(`/data/${revision}/${file.name}`));
        if (!file) return next();
        res.setHeader('Content-Type', 'application/json; charset=utf-8');
        res.end(file.source);
      });
    },
    generateBundle() {
      for (const file of files) {
        this.emitFile({ type: 'asset', fileName: `data/${revision}/${file.name}`, source: file.source });
      }
    },
  };
}
