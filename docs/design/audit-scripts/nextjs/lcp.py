import os
import json, sys
rows=json.load(open(os.path.join(os.environ.get('REVIEW_DIR','.'),'digest-nx.json')))
kept={}
for x in rows:
    k=(x['pid'],x['form'])
    if k not in kept or (x['perf'],-x['lcp'])>(kept[k]['perf'],-kept[k]['lcp']): kept[k]=x
for pid in sys.argv[1:]:
    x=kept[(pid,'mobile')]
    r=json.load(open(x['file']))
    print('===',pid,x['lcp'])
    el=r['audits'].get('largest-contentful-paint-element',{}).get('details',{})
    for it in el.get('items',[]):
        t=it.get('type'); 
        if t=='table':
            for row in it['items']:
                n=row.get('node',{})
                print('  LCP node:', n.get('snippet','')[:200], '|', n.get('selector'))
        elif t=='list':
            for sub in it['items']:
                if sub.get('type')=='table':
                    for row in sub['items']:
                        print('  phase:', row)
                else: print('  ', str(sub)[:200])
    for aid in ('lcp-breakdown-insight','lcp-discovery-insight'):
        a=r['audits'].get(aid)
        if a:
            print(' ',aid,a.get('displayValue'), a.get('score'))
            d=a.get('details',{})
            for it in d.get('items',[])[:6]:
                if it.get('type')=='table':
                    for row in it['items']: print('    ',row)
                else: print('    ',str(it)[:300])
