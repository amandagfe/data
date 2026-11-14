"""Gera data/catalog.json a partir do CSV do Global Landslide Catalog e dos contornos do world-atlas.
Uso: python build_catalog.py Global_Landslide_Catalog_Export_rows.csv countries-110m.json ../data/catalog.json
"""
import csv, json, sys, collections
src, countries, out = sys.argv[1:4]
rows=[]; e=collections.Counter(); f=collections.Counter()
for r in csv.DictReader(open(src, encoding='utf-8', errors='replace')):
    try: lat=float(r['latitude']); lon=float(r['longitude'])
    except ValueError: continue
    d=r['event_date'] or ''
    try: y=int(d[6:10]); m=int(d[0:2]); dd=int(d[3:5])
    except ValueError: y=0; m=0; dd=0
    fa=r['fatality_count']; fa=int(float(fa)) if fa.strip() else 0
    t=(r['landslide_trigger'] or 'unknown').strip().lower(); c=r['country_name'] or ''
    rows.append((round(lat,2),round(lon,2),y,m,fa,t,c,dd))
    if c: e[c]+=1; f[c]+=fa
tl=sorted(set(x[5] for x in rows)); ti={t:i for i,t in enumerate(tl)}
cl=sorted(set(x[6] for x in rows)); ci={c:i for i,c in enumerate(cl)}
json.dump({'pts':[[a,b,y,m,fa,ti[t],ci[c],dd] for a,b,y,m,fa,t,c,dd in rows],'trig':tl,'ctys':cl,'land':json.load(open(countries)),
  'cmp':[[c,e[c],f[c]] for c in ['United States','India','Philippines','China','Nepal','Brazil']]}, open(out,'w'), separators=(',',':'))
print(len(rows),'eventos')
