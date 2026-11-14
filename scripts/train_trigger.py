"""Treina o modelo de disparo com dados reais da NASA POWER e do Global Landslide Catalog.

Casos: dias com deslizamento registrado. Controles: dias comuns no mesmo lugar.
As variáveis são as mesmas calculadas em app.js (função feats), sempre relativas
ao clima do lugar no período 2001–2017.

Uso: python train_trigger.py train_events.json pasta_power/ saida.json
"""
import json, os, sys, random, datetime as dt
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.inspection import permutation_importance

EVENTS, POWER_DIR, OUT = sys.argv[1:4]
NAMES = ['r1','r3','r7','r14','r30','rante','pr1','pr3','pr7','pr14','gt','gr','pgt','pgr','map','ratio7']
NON_WEATHER = {'earthquake','mining','construction','dam_embankment_collapse','leaking_pipe','vibration','volcano','other'}
D0 = dt.date(2001,1,1)
rng = random.Random(42)

ev = json.load(open(EVENTS))
by_cell = {}
for e in ev:
    if e['trig'] in NON_WEATHER: continue
    d = dt.date(int(e['date'][:4]), int(e['date'][4:6]), int(e['date'][6:]))
    by_cell.setdefault(tuple(e['k']), set()).add((d - D0).days)

def roll(P, w):
    c = np.concatenate([[0.0], np.cumsum(np.nan_to_num(P))])
    nanc = np.concatenate([[0], np.cumsum(np.isnan(P))])
    out = np.full(len(P), np.nan)
    t = np.arange(w-1, len(P))
    s = c[t+1] - c[t+1-w]; bad = nanc[t+1] - nanc[t+1-w]
    out[t] = np.where(bad > 0, np.nan, s)
    return out

def pct(s, v): return np.searchsorted(s, v, side='right') / len(s)
def quant(s, q): return s[int(np.floor(q*(len(s)-1)))]

X, y, grp, year = [], [], [], []
fresh_neg = []
for k, days in by_cell.items():
    fn = os.path.join(POWER_DIR, '%d_%d.json' % k)
    if not os.path.exists(fn): continue
    d = json.load(open(fn))
    P = np.array(d['PRECTOTCORR'], float); GT = np.array(d['GWETTOP'], float); GR = np.array(d['GWETROOT'], float)
    for A in (P, GT, GR): A[A == -999] = np.nan
    R3, R7, R14, R30 = roll(P,3), roll(P,7), roll(P,14), roll(P,30)
    sD = np.sort(P[~np.isnan(P)]); sR3 = np.sort(R3[~np.isnan(R3)]); sR7 = np.sort(R7[~np.isnan(R7)]); sR14 = np.sort(R14[~np.isnan(R14)])
    sGT = np.sort(GT[~np.isnan(GT)]); sGR = np.sort(GR[~np.isnan(GR)])
    if len(sR7) < 1000: continue
    mp = np.nanmean(P) * 365.25; q95 = quant(sR7, .95)
    def feats(t):
        if t < 30 or np.isnan(P[t-29:t+1]).any() or np.isnan(GT[t-1]) or np.isnan(GR[t-1]): return None
        r1 = max(P[t], P[t-1]); r3, r7, r14, r30 = R3[t], R7[t], R14[t], R30[t]; gt, gr = GT[t-1], GR[t-1]
        return [r1, r3, r7, r14, r30, r30-r7, pct(sD,r1), pct(sR3,r3), pct(sR7,r7), pct(sR14,r14),
                gt, gr, pct(sGT,gt), pct(sGR,gr), mp, r7/max(1.0, q95)]
    lo, hi = (dt.date(2007,1,1)-D0).days, (dt.date(2017,12,31)-D0).days
    blocked = set(t+o for t in days for o in range(-10, 11))
    for t in sorted(days):
        f = feats(t)
        if f is None: continue
        X.append(f); y.append(1); grp.append(hash(k)); year.append((D0+dt.timedelta(t)).year)
        for _ in range(4):
            for _try in range(20):
                u = rng.randint(lo, hi)
                if u not in blocked:
                    g = feats(u)
                    if g is not None:
                        X.append(g); y.append(0); grp.append(hash(k)); year.append((D0+dt.timedelta(u)).year); break
        for _try in range(20):  # dia comum extra, nunca usado no treino, para calibrar as faixas
            u = rng.randint(lo, hi)
            if u not in blocked:
                g = feats(u)
                if g is not None: fresh_neg.append(g); break

X = np.array(X); y = np.array(y); grp = np.array(grp); year = np.array(year); fresh_neg = np.array(fresh_neg)
print('amostras', len(y), 'casos', int(y.sum()), 'lugares', len(set(grp)))

def make(): return HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_leaf_nodes=15,
                                                  min_samples_leaf=50, l2_regularization=1.0, early_stopping=False, random_state=7)
# 1) validação espacial: lugares inteiros fora do treino
oof = np.zeros(len(y))
for tr, te in GroupKFold(5).split(X, y, grp):
    m = make().fit(X[tr], y[tr]); oof[te] = m.predict_proba(X[te])[:, 1]
auc = roc_auc_score(y, oof); base_auc = roc_auc_score(y, X[:, NAMES.index('pr7')])
# 2) validação no tempo: treino até 2014, teste 2015–2017
tr, te = year <= 2014, year >= 2015
mt = make().fit(X[tr], y[tr]); auc_time = roc_auc_score(y[te], mt.predict_proba(X[te])[:, 1])
pi = permutation_importance(mt, X[te], y[te], scoring='roc_auc', n_repeats=3, random_state=1)
imp = sorted(zip(NAMES, pi.importances_mean), key=lambda t: -t[1])
neg_oof = np.sort(oof[y == 0]); alto_oof = quant(neg_oof, .97)
recall_alto = float((oof[y == 1] >= alto_oof).mean())
print('AUC espacial %.3f | só pr7 %.3f | AUC tempo %.3f | recall alto %.3f' % (auc, base_auc, auc_time, recall_alto))
print(imp[:6])

# modelo final e faixas calibradas em dias comuns que o modelo não viu
mf = make().fit(X, y)
sf = np.sort(mf.predict_proba(fresh_neg)[:, 1])
thr = {'elev': float(quant(sf, .90)), 'alto': float(quant(sf, .97)), 'muito': float(quant(sf, .99))}

# exporta as árvores para inferência em JavaScript
trees = []
for (pred,) in mf._predictors:
    nd = pred.nodes
    trees.append({'f': nd['feature_idx'].astype(int).tolist(), 'th': [float(v) for v in nd['num_threshold']],
                  'l': nd['left'].astype(int).tolist(), 'r': nd['right'].astype(int).tolist(),
                  'v': [float(v) for v in nd['value']], 'ml': nd['missing_go_to_left'].astype(int).tolist(),
                  'leaf': nd['is_leaf'].astype(int).tolist()})
base = float(np.ravel(mf._baseline_prediction)[0])
def js_predict(x):
    raw = base
    for t in trees:
        i = 0
        while not t['leaf'][i]:
            v = x[t['f'][i]]
            i = (t['l'][i] if (t['ml'][i] if np.isnan(v) else v <= t['th'][i]) else t['r'][i])
        raw += t['v'][i]
    return 1/(1+np.exp(-raw))
chk = max(abs(js_predict(X[i]) - mf.predict_proba(X[i:i+1])[0, 1]) for i in range(0, len(X), max(1, len(X)//300)))
print('diferença máxima Python x exportado: %.2e' % chk)
assert chk < 1e-4

json.dump({'feat': NAMES, 'base': base, 'trees': trees, 'thr': thr, 'imp': [[n, round(float(v), 4)] for n, v in imp],
           'metrics': {'auc': round(auc, 3), 'base_auc': round(base_auc, 3), 'auc_time': round(auc_time, 3),
                       'recall_alto': round(recall_alto, 3), 'spec_alto': 0.97, 'n': int(len(y)), 'cases': int(y.sum()),
                       'places': len(set(grp.tolist()))}},
          open(OUT, 'w'), separators=(',', ':'))
print('thr', thr)
