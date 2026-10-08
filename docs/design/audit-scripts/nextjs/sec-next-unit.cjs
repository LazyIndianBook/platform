const { load } = require('./ts-run.cjs');
const FE = (process.env.FRONTEND_DIR || require('path').resolve(__dirname, '../../../../examleaf-frontend')) + '/src/lib';
const { safeNext, withNext } = load(FE + '/auth/next-url.ts');
const vectors = ['/..//evil.com', '/.//evil.com', '/././/evil.com', '/a/..//evil.com', '/%2e%2e//evil.com', '/%2e//evil.com', '/..%2f/evil.com', '/..///evil.com', '/.././/evil.com', '/a/../..//evil.com/path?x=1#h', '/account/../..//evil.com'];
for (const v of vectors) { const r = safeNext(v); console.log('safeNext', JSON.stringify(v).padEnd(36), '->', JSON.stringify(r), r.startsWith('//') ? '  <== PROTOCOL-RELATIVE (another host)' : ''); }
console.log('withNext', withNext('/account/login/', '/..//evil.com'));
// how the browser reads the result
for (const r of ['//evil.com', '//evil.com/path?x=1#h']) console.log('new URL(' + JSON.stringify(r) + ', "https://examleaf.in/account/login/").href =', new URL(r, 'https://examleaf.in/account/login/').href);
