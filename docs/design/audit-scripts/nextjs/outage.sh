#!/bin/bash
SP=${REVIEW_DIR:-.}
SID=$(python3 -c "import json;print([c['value'] for c in json.load(open('$SP/cookies.json')) if c['name']=='sessionid'][0])")
while read -r path who; do
  if [ "$who" = auth ]; then hdr=(-H "Cookie: sessionid=$SID"); else hdr=(); fi
  printf "%-40s %-5s " "$path" "$who"
  curl -s "${hdr[@]}" -o $SP/dn.html -w "%{http_code} " "http://localhost:3003$path"
  python3 - "$SP/dn.html" <<'PY'
import re, sys
h=open(sys.argv[1],errors='ignore').read()
h2=re.sub(r'<script.*?</script>','',h,flags=re.S); h2=re.sub(r'<style.*?</style>','',h2,flags=re.S)
i=h2.find('<main'); j=h2.find('</main>')
t=re.sub(r'<[^>]+>',' ',h2[i:j]); t=re.sub(r'\s+',' ',t).strip()
leak=[w for w in ('ECONNREFUSED','localhost:81','8103','fetch failed','Error:','stack','node_modules','.next/') if w in h]
print(t[:150].ljust(152),'| leak words:',leak)
PY
done <<'LIST'
/ anon
/shop/ anon
/shop/physics-sample-papers-2027/ anon
/shop/no-such-product/ anon
/s/PHY-E01/ anon
/s/PHY-M05/ anon
/privacy/ anon
/account/login/ anon
/account/ auth
/cart/ auth
/checkout/ auth
/account/orders/EL-2026-000003/ auth
/orders/t/anything/ anon
LIST
