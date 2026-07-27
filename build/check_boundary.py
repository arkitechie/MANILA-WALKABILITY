import json, pathlib, math
HERE = pathlib.Path(__file__).resolve().parent
b = json.loads((HERE / 'cache' / 'boundary.json').read_text(encoding='utf-8'))['elements'][0]
print('tags:', {k: v for k, v in b['tags'].items() if k in
                ('name', 'admin_level', 'boundary', 'type', 'place', 'wikidata')})
roles = {}
for m in b['members']:
    roles[m.get('role', '')] = roles.get(m.get('role', ''), 0) + 1
print('member roles:', roles)
for m in b['members'][:60]:
    if m['type'] == 'way' and 'geometry' in m:
        g = m['geometry']
        lo = [p['lon'] for p in g]; la = [p['lat'] for p in g]
        print('  way %-12d role=%-8s n=%-4d lon %.4f..%.4f  lat %.4f..%.4f'
              % (m['ref'], m.get('role', ''), len(g), min(lo), max(lo), min(la), max(la)))
