"""Junta os dois modelos em data/models.json.
Uso: python build_models.py structural.json trigger.json ../data/models.json
"""
import json, sys
g, t, out = sys.argv[1:4]
json.dump({'grid': json.load(open(g)), 'trig': json.load(open(t))}, open(out,'w'), separators=(',',':'))
