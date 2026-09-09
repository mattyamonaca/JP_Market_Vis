// node:test で .jsx をそのまま import できるようにする（esbuild で変換）。package.json の test から --import で読み込む
import { register } from 'node:module';
register('./jsx-loader.mjs', import.meta.url);
