import csv, sys, json, math, collections
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score, average_precision_score
from sklearn.inspection import permutation_importance
src, out = sys.argv[1:3]
RAIN={'downpour','rain','continuous_rain','monsoon','tropical_cyclone'}
ev=[]
for r in csv.DictReader(open(src, encoding='utf-8', errors='replace')):
    try: lat=float(r['latitude']); lng=float(r['longitude']); d=r['event_date']; y=int(d[6:10]); m=int(d[0:2])
    except: continue
    if not (2007<=y<=2017): continue
    f=r['fatality_count']; f=int(float(f)) if f.strip() else 0
    ev.append((int(math.floor(lat))+90, int(math.floor(lng))+180, y, m, f, (r['landslide_trigger'] or '').lower() in RAIN))
has=set((a,b) for a,b,*_ in ev)
C=set()
for a,b in has:
    for da in range(-2,3):
        for db in range(-2,3):
            if 0<=a+da<180: C.add((a+da,(b+db)%360))
C=sorted(C); print('cells',len(C),'events',len(ev))
def agg(y0,y1):
    cnt=collections.Counter(); cm=collections.Counter(); fat=collections.Counter(); rain=collections.Counter(); yrs=collections.defaultdict(set)
    for a,b,y,m,f,rn in ev:
        if y0<=y<=y1: cnt[a,b]+=1; cm[a,b,m]+=1; fat[a,b]+=f; rain[a,b]+=rn; yrs[a,b].add(y)
    return cnt,cm,fat,rain,yrs,sum(cnt.values())
def nb(D,a,b,r,m=None,excl=True):
    s=0
    for da in range(-r,r+1):
        for db in range(-r,r+1):
            if excl and da==0 and db==0: continue
            k=(a+da,(b+db)%360) if m is None else (a+da,(b+db)%360,m)
            s+=D.get(k,0)
    return s
NAMES=['eventos_celula','eventos_celula_mes','vizinhos_1','vizinhos_1_mes','vizinhos_2','vizinhos_2_mes','mortes_regiao','fracao_chuva','anos_ativos','lat','abs_lat','sin_lon','cos_lon','sin_mes','cos_mes','hemisferio_x_mes']
def feats(y0,y1):
    cnt,cm,fat,rain,yrs,T=agg(y0,y1); k=1000.0/T
    X=[];keys=[]
    for a,b in C:
        lat=a-90+.5; lng=b-180+.5
        c=cnt.get((a,b),0); n1=nb(cnt,a,b,1); n2=nb(cnt,a,b,2)-n1
        f3=fat.get((a,b),0)+nb(fat,a,b,1); r3=rain.get((a,b),0)+nb(rain,a,b,1); t3=c+n1
        ya=set()
        for da in (-1,0,1):
            for db in (-1,0,1): ya|=yrs.get((a+da,(b+db)%360),set())
        for m in range(1,13):
            cmm=cm.get((a,b,m),0); n1m=nb(cm,a,b,1,m); n2m=nb(cm,a,b,2,m)-n1m
            X.append([c*k,cmm*k,n1*k,n1m*k,n2*k,n2m*k,math.log1p(f3),(r3/t3 if t3 else -1),len(ya),lat,abs(lat),math.sin(math.radians(lng)),math.cos(math.radians(lng)),math.sin(2*math.pi*m/12),math.cos(2*math.pi*m/12),(1 if lat>=0 else -1)*math.cos(2*math.pi*m/12)])
            keys.append((a,b,m))
    return np.array(X),keys
def labels(keys,y0,y1):
    s=set((a,b,m) for a,b,y,m,*_ in ev if y0<=y<=y1)
    return np.array([1 if k in s else 0 for k in keys])
Xtr,ktr=feats(2007,2012); ytr=labels(ktr,2013,2014)
Xte,kte=feats(2009,2014); yte=labels(kte,2015,2016)
print('pos rate train',ytr.mean(),'test',yte.mean())
mdl=HistGradientBoostingClassifier(max_iter=300,learning_rate=.05,max_leaf_nodes=24,min_samples_leaf=40,l2_regularization=1.0,random_state=7)
mdl.fit(Xtr,ytr); p=mdl.predict_proba(Xte)[:,1]
base=Xte[:,1]+Xte[:,3]*.5+Xte[:,0]*.1
auc=roc_auc_score(yte,p); ap=average_precision_score(yte,p); bauc=roc_auc_score(yte,base); bap=average_precision_score(yte,base)
order=np.argsort(-p); top=order[:int(len(p)*.10)]; cap=yte[top].sum()/yte.sum()
border=np.argsort(-base); btop=border[:int(len(p)*.10)]; bcap=yte[btop].sum()/yte.sum()
print('AUC',auc,'AP',ap,'| baseline AUC',bauc,'AP',bap,'| top10 capture',cap,'base',bcap)
pi=permutation_importance(mdl,Xte,yte,scoring='roc_auc',n_repeats=3,random_state=1)
imp=sorted(zip(NAMES,pi.importances_mean),key=lambda x:-x[1]); print(imp[:8])
# final: retrain on most recent labelled split (feat 2009-2014 -> 2015-2016) plus earlier, forecast with feat 2012-2017
Xall=np.vstack([Xtr,Xte]); yall=np.concatenate([ytr,yte]); mdl.fit(Xall,yall)
Xf,kf=feats(2012,2017); pf=mdl.predict_proba(Xf)[:,1]
q=np.quantile(pf,[.60,.85,.95]); print('quantiles',q)
cells={}
for (a,b,m),v in zip(kf,pf): cells.setdefault((a,b),[0]*12)[m-1]=int(round(v*1000))
rows=[[a-90,b-180]+v for (a,b),v in cells.items() if max(v)>=1]
json.dump({'cells':rows,'q':[round(float(x)*1000,1) for x in q],
  'metrics':{'auc':round(auc,3),'ap':round(ap,3),'base_auc':round(bauc,3),'base_ap':round(bap,3),'top10':round(float(cap),3),'base_top10':round(float(bcap),3),'pos_rate':round(float(yte.mean()),4),'n_test':int(len(yte)),'n_cells':len(C)},
  'imp':[[n,round(float(v),4)] for n,v in imp]}, open(out,'w'), separators=(',',':'))
print('rows',len(rows))
