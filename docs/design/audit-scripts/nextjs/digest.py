import json, glob, os, re, sys
J=os.environ.get('REVIEW_DIR','.')+'/json'
tag=sys.argv[1] if len(sys.argv)>1 else 'nx'
def num(r,k): 
    a=r['audits'].get(k); return a.get('numericValue') if a else None
rows=[]
for f in sorted(glob.glob(f'{J}/{tag}-*.report.json')):
    m=re.match(rf'{J}/{tag}-(\w+)-(mobile|desktop)-(\d)\.report\.json',f)
    if not m: continue
    pid,form,n=m.groups()
    r=json.load(open(f))
    if r.get('runtimeError'): continue
    cat={k:round(v['score']*100) for k,v in r['categories'].items()}
    net=r['audits']['network-requests']['details']['items']
    def tr(i): return i.get('transferSize',0)
    js=[i for i in net if i.get('resourceType')=='Script']
    rs={i['resourceType']:(i['transferSize'],i['requestCount']) for i in r['audits']['resource-summary']['details']['items']}
    rows.append(dict(pid=pid,form=form,n=int(n),perf=cat['performance'],a11y=cat['accessibility'],bp=cat['best-practices'],seo=cat['seo'],
      fcp=num(r,'first-contentful-paint'),lcp=num(r,'largest-contentful-paint'),tbt=num(r,'total-blocking-time'),cls=num(r,'cumulative-layout-shift'),si=num(r,'speed-index'),
      ttfb=num(r,'server-response-time'),bytes=num(r,'total-byte-weight'),req=len(net),js_bytes=sum(tr(i) for i in js),js_res=sum(i.get('resourceSize',0) for i in js),js_n=len(js),
      rs=rs,bench=round(r['environment']['benchmarkIndex']),file=f,final=r['finalDisplayedUrl']))
json.dump(rows,open(f'{J}/../digest-{tag}.json','w'),indent=1)
for x in rows:
    print(f"{x['pid']:10s} {x['form']:7s} #{x['n']} perf={x['perf']:3d} a11y={x['a11y']} bp={x['bp']} seo={x['seo']} fcp={x['fcp']/1000:.2f} lcp={x['lcp']/1000:.2f} tbt={x['tbt']:.0f} cls={x['cls']:.3f} si={x['si']/1000:.2f} ttfb={x['ttfb']:.0f} bytes={x['bytes']/1024:.0f}K req={x['req']} js={x['js_bytes']/1024:.0f}K({x['js_n']}) bench={x['bench']}")
