import csv, sys, collections, json
c=collections.Counter(); acc=collections.Counter()
ev=[]
for r in csv.DictReader(open(sys.argv[1], encoding='utf-8', errors='replace')):
    try: lat=float(r['latitude']); lon=float(r['longitude']); d=r['event_date']; y=int(d[6:10]); m=int(d[0:2]); dd=int(d[3:5])
    except: continue
    acc[r['location_accuracy']]+=1
    if not (2007<=y<=2017): continue
    if r['location_accuracy'] not in ('exact','1km','5km','10km','25km'): continue
    k=(round(lat/0.5), round(lon/0.625)); c[k]+=1
    ev.append({'k':list(k),'lat':lat,'lon':lon,'date':'%04d%02d%02d'%(y,m,dd),'trig':(r['landslide_trigger'] or '').lower()})
print(acc.most_common()); print('events',len(ev),'cells',len(c)); print(sum(1 for v in c.values() if v>=2),'cells with >=2')
json.dump(ev, open(sys.argv[2],'w'))
