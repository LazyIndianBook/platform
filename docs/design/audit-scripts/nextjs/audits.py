import os
import json, sys, re
rows=json.load(open(os.path.join(os.environ.get('REVIEW_DIR','.'),'digest-nx.json')))
kept={}
for x in rows:
    k=(x['pid'],x['form'])
    if k not in kept or (x['perf'],-x['lcp'])>(kept[k]['perf'],-kept[k]['lcp']): kept[k]=x
want=sys.argv[1:] 
for k,x in sorted(kept.items()):
    if want and x['pid'] not in want: continue
    r=json.load(open(x['file']))
    print('='*3, k, f"#{x['n']} perf={x['perf']} lcp={x['lcp']/1000:.2f}")
    for aid,a in r['audits'].items():
        if a.get('score') is None or a['score']>=1: continue
        if a.get('scoreDisplayMode') in ('notApplicable','manual','informative'): continue
        dv=a.get('displayValue','')
        print(f"  [{a['score']:.2f}] {aid}: {a['title']} {dv}")
        d=a.get('details',{})
        items=d.get('items',[]) if isinstance(d,dict) else []
        for it in items[:4]:
            s={kk:(vv if not isinstance(vv,dict) else (vv.get('snippet') or vv.get('selector') or vv.get('url') or str(vv)[:80])) for kk,vv in it.items() if kk in ('url','node','source','description','wastedBytes','totalBytes','wastedMs','statusCode','sourceLocation','subItems','label','groupLabel')}
            print('     ', str(s)[:260])
