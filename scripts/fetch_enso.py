"""Baixa o Oceanic Niño Index (ONI) da NOAA CPC e gera data/enso.json.
O ONI é a média móvel de 3 meses da anomalia de TSM no Niño 3.4 (5°N–5°S, 120°–170°W).
Cada estação de 3 meses é atribuída ao mês central (DJF → janeiro, ..., NDJ → dezembro).
Uso: python fetch_enso.py ../data/enso.json
"""
import json, sys, datetime, urllib.request
URL = 'https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt'
SEAS = ['DJF','JFM','FMA','MAM','AMJ','MJJ','JJA','JAS','ASO','SON','OND','NDJ']
txt = urllib.request.urlopen(URL, timeout=60).read().decode()
rows = []
for line in txt.splitlines()[1:]:
    p = line.split()
    if len(p) == 4 and p[0] in SEAS:
        rows.append([int(p[1]), SEAS.index(p[0]) + 1, float(p[3])])
json.dump({'source': URL, 'updated': datetime.date.today().isoformat(), 'oni': rows},
          open(sys.argv[1], 'w'), separators=(',', ':'))
print(len(rows), 'meses; último', rows[-1])
