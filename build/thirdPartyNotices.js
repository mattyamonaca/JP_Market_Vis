import fs from 'node:fs';
import path from 'node:path';

// 実際にバンドルされた依存だけを対象とし、許諾文が見つからなければビルドを止める。
export function thirdPartyNotices() {
  return {
    name: 'third-party-notices',
    generateBundle(_, bundle) {
      const packages = new Map();
      for (const output of Object.values(bundle)) {
        if (output.type !== 'chunk') continue;
        for (const id of Object.keys(output.modules)) {
          const clean = id.replace(/^\0/, '').split('?')[0];
          if (!clean.includes('/node_modules/') || !path.isAbsolute(clean)) continue;
          let dir = path.dirname(clean);
          while (dir.includes('node_modules')) {
            const manifest = path.join(dir, 'package.json');
            if (fs.existsSync(manifest)) {
              const pkg = JSON.parse(fs.readFileSync(manifest, 'utf8'));
              if (pkg.name && pkg.version) {
                packages.set(`${pkg.name}@${pkg.version}`, { dir, pkg });
                break;
              }
            }
            dir = path.dirname(dir);
          }
        }
      }
      const notices = ['Third-party software notices\nGenerated from modules included in this build.'];
      for (const [key, {dir, pkg}] of [...packages].sort(([a], [b]) => a.localeCompare(b))) {
        const files = fs.readdirSync(dir).filter(f => /^(licen[cs]e|copying|notice)([.-].*)?$/i.test(f) && fs.statSync(path.join(dir, f)).isFile());
        const supplement = path.join('build/licenses', `${key.replaceAll('/', '__')}.txt`);
        if (!files.some(f => /^(licen[cs]e|copying)/i.test(f)) && !fs.existsSync(supplement)) this.error(`License text missing: ${key}`);
        notices.push(`\n${'='.repeat(72)}\n${key}\nLicense: ${pkg.license ?? 'See below'}\n`);
        for (const file of files.sort()) notices.push(`--- ${file} ---\n${fs.readFileSync(path.join(dir, file), 'utf8')}`);
        if (fs.existsSync(supplement)) notices.push(fs.readFileSync(supplement, 'utf8'));
      }
      if (!packages.size) this.error('No bundled dependencies found for notices');
      this.emitFile({type: 'asset', fileName: 'THIRD_PARTY_NOTICES.txt', source: notices.join('\n')});
      this.emitFile({type: 'asset', fileName: 'LICENSE.txt', source: fs.readFileSync('LICENSE', 'utf8')});
    },
  };
}
