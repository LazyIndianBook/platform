// Experiment: keep only the framework's scripts (react-dom, the Next router, the runtime) and every inline script; drop the app's own chunks.
import http from 'node:http';
import zlib from 'node:zlib';
const [listen, upstream] = process.argv.slice(2).map(Number);
const KEEP = (process.env.KEEP || '').split(',').filter(Boolean);
http.createServer((req, res) => {
  const up = http.request({ host: 'localhost', port: upstream, path: req.url, method: req.method, headers: req.headers }, (ur) => {
    const type = ur.headers['content-type'] || '';
    if (!/text\/html/.test(type)) { res.writeHead(ur.statusCode, ur.headers); ur.pipe(res); return; }
    const chunks = []; ur.on('data', (c) => chunks.push(c));
    ur.on('end', () => {
      let buf = Buffer.concat(chunks); const enc = ur.headers['content-encoding']; if (enc === 'gzip') buf = zlib.gunzipSync(buf);
      let html = buf.toString('utf8');
      html = html.replace(/<script\b[^>]*\bsrc="([^"]*)"[^>]*><\/script>/g, (m, src) => (KEEP.some((k) => src.includes(k)) ? m : ''));
      html = html.replace(/<link[^>]*rel="preload"[^>]*as="script"[^>]*>/g, (m) => (KEEP.some((k) => m.includes(k)) ? m : ''));
      const out = enc === 'gzip' ? zlib.gzipSync(Buffer.from(html)) : Buffer.from(html);
      const headers = { ...ur.headers }; delete headers['transfer-encoding']; headers['content-length'] = out.length;
      res.writeHead(ur.statusCode, headers); res.end(out);
    });
  });
  up.on('error', () => { res.writeHead(502); res.end(); }); req.pipe(up);
}).listen(listen, () => console.log('proxy', listen, '->', upstream, 'keeping', KEEP));
