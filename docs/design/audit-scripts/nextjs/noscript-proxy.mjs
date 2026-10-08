// A rewriting proxy for one experiment: the same pages with every <script> and script preload removed (what the lab LCP costs
// without any JavaScript). node noscript-proxy.mjs <listenPort> <upstreamPort>
import http from 'node:http';
import zlib from 'node:zlib';
const [listen, upstream] = process.argv.slice(2).map(Number);
http.createServer((req, res) => {
  const up = http.request({ host: 'localhost', port: upstream, path: req.url, method: req.method, headers: req.headers }, (ur) => {
    const type = ur.headers['content-type'] || '';
    if (!/text\/html/.test(type)) { res.writeHead(ur.statusCode, ur.headers); ur.pipe(res); return; }
    const chunks = [];
    ur.on('data', (c) => chunks.push(c));
    ur.on('end', () => {
      let buf = Buffer.concat(chunks);
      const enc = ur.headers['content-encoding'];
      if (enc === 'gzip') buf = zlib.gunzipSync(buf);
      let html = buf.toString('utf8');
      html = html.replace(/<script\b(?![^>]*application\/ld\+json)[^>]*>[\s\S]*?<\/script>/g, '').replace(/<link[^>]*as="script"[^>]*>/g, '');
      const out = enc === 'gzip' ? zlib.gzipSync(Buffer.from(html)) : Buffer.from(html);
      const headers = { ...ur.headers }; delete headers['content-length']; delete headers['transfer-encoding']; headers['content-length'] = out.length;
      delete headers.link; // the Link header preloads fonts only: keep them, but drop script preloads
      if (ur.headers.link) headers.link = String(ur.headers.link).split(/,\s*(?=<)/).filter((l) => !/as="script"/.test(l)).join(', ');
      res.writeHead(ur.statusCode, headers); res.end(out);
    });
  });
  up.on('error', () => { res.writeHead(502); res.end(); });
  req.pipe(up);
}).listen(listen, () => console.log('proxy', listen, '->', upstream));
