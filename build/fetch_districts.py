"""Manila's sub-areas (districts / barangays) cover only land, so their union
gives us the coastline-accurate land outline to draw alongside the legal
boundary (which extends far into Manila Bay)."""
import json, pathlib, requests, time

HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / 'cache'; CACHE.mkdir(exist_ok=True)
Q = """
[out:json][timeout:300];
area(id:3600103703)->.a;
rel(area.a)["boundary"="administrative"]["admin_level"~"^(9|10)$"];
out geom;
"""
ENDPOINTS = ['https://overpass.kumi.systems/api/interpreter',
             'https://overpass-api.de/api/interpreter']
p = CACHE / 'districts.json'
if p.exists():
    d = json.loads(p.read_text(encoding='utf-8'))
    print('cached:', len(d['elements']), 'elements')
else:
    for ep in ENDPOINTS:
        try:
            print('fetching from', ep.split('/')[2], '...')
            r = requests.post(ep, data={'data': Q}, timeout=400,
                              headers={'User-Agent': 'manila-walkability-build/2.0'})
            r.raise_for_status()
            d = r.json()
            p.write_text(json.dumps(d), encoding='utf-8')
            print('OK:', len(d['elements']), 'elements', p.stat().st_size / 1e6, 'MB')
            break
        except Exception as e:
            print('  failed:', type(e).__name__, str(e)[:120]); time.sleep(5)
    else:
        raise SystemExit('districts fetch failed')

lv = {}
for e in d['elements']:
    k = e.get('tags', {}).get('admin_level')
    lv[k] = lv.get(k, 0) + 1
print('admin_levels present:', lv)
for e in d['elements'][:5]:
    print('  ', e.get('tags', {}).get('admin_level'), e.get('tags', {}).get('name'),
          '| members:', len(e.get('members', [])))
