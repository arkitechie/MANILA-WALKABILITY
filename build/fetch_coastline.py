"""OSM coastline around Manila Bay, used to cut the legal city polygon into its
land part and its maritime part."""
import json, pathlib, requests, time
HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / 'cache'; CACHE.mkdir(exist_ok=True)
Q = """
[out:json][timeout:300];
(
  way["natural"="coastline"](14.50,120.75,14.70,121.06);
  way["natural"="water"]["water"!="pond"](14.53,120.93,14.66,121.03);
  way["waterway"="riverbank"](14.53,120.93,14.66,121.03);
);
out geom;
"""
p = CACHE / 'coastline.json'
if p.exists():
    print('cached:', len(json.loads(p.read_text(encoding='utf-8'))['elements']), 'elements')
else:
    for ep in ['https://overpass.kumi.systems/api/interpreter',
               'https://overpass-api.de/api/interpreter']:
        try:
            print('fetching from', ep.split('/')[2], '...')
            r = requests.post(ep, data={'data': Q}, timeout=400,
                              headers={'User-Agent': 'manila-walkability-build/2.0'})
            r.raise_for_status()
            d = r.json(); p.write_text(json.dumps(d), encoding='utf-8')
            print('OK:', len(d['elements']), 'elements'); break
        except Exception as e:
            print('  failed:', type(e).__name__, str(e)[:120]); time.sleep(5)
    else:
        raise SystemExit('coastline fetch failed')
d = json.loads(p.read_text(encoding='utf-8'))
cl = [e for e in d['elements'] if e.get('tags', {}).get('natural') == 'coastline']
print('coastline ways:', len(cl), '| total pts:', sum(len(e.get('geometry', [])) for e in cl))
