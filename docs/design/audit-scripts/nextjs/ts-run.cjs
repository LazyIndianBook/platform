// Transpile one TS file of the frontend (read-only) to run its pure functions: node ts-run.cjs
const FRONTEND = process.env.FRONTEND_DIR || require('path').resolve(__dirname, '../../../../examleaf-frontend');
const ts = require(FRONTEND + '/node_modules/typescript');
const fs = require('fs'); const path = require('path'); const vm = require('vm');
function load(file) { const src = fs.readFileSync(file, 'utf8'); const out = ts.transpileModule(src, { compilerOptions: { module: 'commonjs', target: 'es2020' } }).outputText; const m = { exports: {} }; vm.runInNewContext(out, { module: m, exports: m.exports, require: (n) => { throw new Error('require ' + n); }, process: { env: {} }, URL, console }); return m.exports; }
module.exports = { load };
