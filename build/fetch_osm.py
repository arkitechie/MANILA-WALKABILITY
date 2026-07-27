"""
Pull the raw OpenStreetMap extract for the City of Manila and cache it.

Four queries, cached separately under build/cache/ so re-runs are free:
  boundary.json  the legal city boundary, relation 103703
  streets.json   every highway=* way inside it, with node refs + node coords
  pois.json      amenity / shop / leisure / tourism / office destinations
  transit.json   bus, jeepney, LRT/MRT and rail stops
"""
import json, pathlib, sys, time
import requests

HERE = pathlib.Path(__file__).resolve().parent
CACHE = HERE / 'cache'
CACHE.mkdir(exist_ok=True)

ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.osm.ch/api/interpreter',
]
MANILA_REL = 103703

QUERIES = {
    'boundary': f"""
[out:json][timeout:180];
rel({MANILA_REL});
out geom;
""",
    'streets': f"""
[out:json][timeout:300];
rel({MANILA_REL}); map_to_area->.a;
way["highway"]
   ["highway"!~"^(motorway|motorway_link|construction|proposed|raceway|bus_guideway|escape)$"]
   ["area"!="yes"]
   (area.a);
out body;
>;
out skel qt;
""",
    'pois': f"""
[out:json][timeout:300];
rel({MANILA_REL}); map_to_area->.a;
(
  nwr["amenity"](area.a);
  nwr["shop"](area.a);
  nwr["leisure"](area.a);
  nwr["tourism"](area.a);
  nwr["office"](area.a);
  nwr["healthcare"](area.a);
);
out center tags;
""",
    'transit': f"""
[out:json][timeout:300];
rel({MANILA_REL}); map_to_area->.a;
(
  node["highway"="bus_stop"](area.a);
  nwr["public_transport"~"^(platform|stop_position|station)$"](area.a);
  nwr["railway"~"^(station|halt|tram_stop)$"](area.a);
  nwr["amenity"="bus_station"](area.a);
);
out center tags;
""",
}


def run(name, query, force=False):
    path = CACHE / f'{name}.json'
    if path.exists() and not force:
        size = path.stat().st_size / 1e6
        n = len(json.loads(path.read_text(encoding='utf-8')).get('elements', []))
        print(f'  {name:<9} cached   {n:>8,} elements  {size:6.1f} MB')
        return path
    last = None
    for ep in ENDPOINTS:
        for attempt in range(3):
            try:
                print(f'  {name:<9} fetching from {ep.split("/")[2]} (try {attempt + 1}) ...',
                      flush=True)
                r = requests.post(ep, data={'data': query}, timeout=400,
                                  headers={'User-Agent': 'manila-walkability-build/2.0'})
                if r.status_code in (429, 504):
                    print(f'    HTTP {r.status_code}, backing off'); time.sleep(20); continue
                r.raise_for_status()
                data = r.json()
                if 'elements' not in data:
                    raise ValueError('no elements key')
                path.write_text(json.dumps(data), encoding='utf-8')
                print(f'  {name:<9} OK       {len(data["elements"]):>8,} elements  '
                      f'{path.stat().st_size / 1e6:6.1f} MB')
                return path
            except Exception as e:
                last = e
                print(f'    failed: {type(e).__name__}: {str(e)[:120]}')
                time.sleep(8)
    raise SystemExit(f'{name}: all endpoints failed, last error {last}')


if __name__ == '__main__':
    force = '--force' in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith('-')]
    print('Fetching OpenStreetMap extract for the City of Manila (relation %d)' % MANILA_REL)
    for name, q in QUERIES.items():
        if only and name not in only:
            continue
        run(name, q, force=force)
    print('done')
