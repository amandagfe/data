import json, sys, os, time, urllib.request, concurrent.futures as cf
ev=json.load(open(sys.argv[1])); outdir=sys.argv[2]
cells={}
for e in ev: cells.setdefault(tuple(e['k']), (e['lat'], e['lon']))
def get(k):
    fn=os.path.join(outdir,'%d_%d.json'%k)
    if os.path.exists(fn) and os.path.getsize(fn)>1000: return 'skip'
    lat=k[0]*0.5; lon=k[1]*0.625
    url=('https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR,GWETTOP,GWETROOT'
         '&community=AG&longitude=%.4f&latitude=%.4f&start=20010101&end=20171231&format=JSON'%(lon,lat))
    for a in range(5):
        try:
            with urllib.request.urlopen(url, timeout=120) as r: b=r.read()
            d=json.loads(b); p=d['properties']['parameter']
            json.dump({k2:[v[x] for x in sorted(v)] for k2,v in p.items()}|{'start':'20010101'}, open(fn,'w'), separators=(',',':'))
            return 'ok'
        except Exception as ex:
            time.sleep(5*(a+1)); err=str(ex)
    return 'fail '+err
done=0
with cf.ThreadPoolExecutor(3) as ex:
    for res in ex.map(get, cells):
        done+=1
        if done%100==0 or res.startswith('fail'): print(done, len(cells), res, flush=True)
print('finished', done)
