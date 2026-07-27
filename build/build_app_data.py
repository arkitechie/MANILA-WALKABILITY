"""
Turn the raw OSM extract into everything the app needs.

Produces manila.js containing:
  boundary   the legal City of Manila polygon (relation 103703)
  nodes      every intersection / endpoint, delta-encoded
  streets    one record per block-level segment: real geometry, real features,
             real walkability score, ready to click
  hexes      H3 res-9 aggregation computed from the real segment positions
  norms      the min/max constants used for P_norm / T_norm / I_norm

Features are measured, not invented:
  poi_count_400m       destinations within 400 m of the segment midpoint
  dist_to_transit_m    metres to the nearest bus / jeepney / LRT / rail stop
  intersection_density junctions per km2 within 400 m
  sidewalk             OSM tag where present, a parallel mapped sidewalk where
                       one exists, otherwise inferred from road class and flagged
"""
import json, math, pathlib, collections
import numpy as np
from scipy.spatial import cKDTree
import h3

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / 'cache'

LAT0, LON0 = 14.5995, 120.9842
MPD_LAT = 110574.0
MPD_LON = 111320.0 * math.cos(math.radians(LAT0))
PREC = 1e5  # ~1.1 m coordinate precision on disk

def xy(lat, lon):
    return ((lon - LON0) * MPD_LON, (lat - LAT0) * MPD_LAT)

def load(name):
    return json.loads((CACHE / f'{name}.json').read_text(encoding='utf-8'))

# --------------------------------------------------------------- boundary --
print('boundary ...')
brel = load('boundary')['elements'][0]
outers, inners = [], []
for mem in brel['members']:
    if mem['type'] != 'way' or 'geometry' not in mem:
        continue
    ring = [(p['lon'], p['lat']) for p in mem['geometry']]
    (outers if mem.get('role') != 'inner' else inners).append(ring)

# stitch the outer ways into closed rings
def stitch(ways):
    ways = [list(w) for w in ways]
    rings, pool = [], ways[:]
    while pool:
        cur = pool.pop(0)
        changed = True
        while changed and cur[0] != cur[-1]:
            changed = False
            for i, w in enumerate(pool):
                if w[0] == cur[-1]:
                    cur += w[1:]; pool.pop(i); changed = True; break
                if w[-1] == cur[-1]:
                    cur += w[::-1][1:]; pool.pop(i); changed = True; break
                if w[-1] == cur[0]:
                    cur = w[:-1] + cur; pool.pop(i); changed = True; break
                if w[0] == cur[0]:
                    cur = w[::-1][:-1] + cur; pool.pop(i); changed = True; break
        if len(cur) > 3:
            if cur[0] != cur[-1]:
                cur.append(cur[0])
            rings.append(cur)
    return rings

boundary_rings = stitch(outers)
boundary_rings.sort(key=len, reverse=True)
print('  %d outer ring(s), largest has %d points' % (len(boundary_rings), len(boundary_rings[0])))

from shapely.geometry import Polygon, MultiPolygon, Point, LineString, box
from shapely.ops import unary_union, polygonize
from shapely.prepared import prep
polys = [Polygon(r) for r in boundary_rings if len(r) > 3]
polys = [p if p.is_valid else p.buffer(0) for p in polys]
city = unary_union([p for p in polys if p.area > 0])
KM2 = MPD_LAT * MPD_LON / 1e6
print('  legal boundary ~%.1f km2 (includes the Manila Bay jurisdiction)' % (city.area * KM2))

# The admin relation reaches far out into Manila Bay. Cut it along the real OSM
# coastline so we can draw the land the city actually stands on as well.
print('clipping to the coastline ...')
coast = [LineString([(p['lon'], p['lat']) for p in e['geometry']])
         for e in load('coastline')['elements']
         if e.get('tags', {}).get('natural') == 'coastline' and len(e.get('geometry', [])) > 1]
ring = LineString(city.exterior.coords) if isinstance(city, Polygon) else \
    unary_union([LineString(g.exterior.coords) for g in city.geoms])
faces = list(polygonize(unary_union([ring] + coast)))
faces = [f for f in faces if f.within(city.buffer(1e-9))]
print('  coastline cut the polygon into %d face(s)' % len(faces))

# ------------------------------------------------------------------ input --
print('parsing streets ...')
sel = load('streets')['elements']
coords, ways = {}, []
for el in sel:
    if el['type'] == 'node':
        coords[el['id']] = (el['lat'], el['lon'])
    elif el['type'] == 'way':
        ways.append(el)
print('  %d ways, %d nodes' % (len(ways), len(coords)))

# A face is land if streets stand on it. Sample the street nodes into the faces.
sample = list(coords.values())[::37]
counts = []
for f in faces:
    pf = prep(f)
    counts.append(sum(1 for la, lo in sample if pf.contains(Point(lo, la))))
for f, c in sorted(zip(faces, counts), key=lambda t: -t[0].area):
    b = f.bounds
    print('    face %7.2f km2  %4d sampled street nodes  lon %.3f..%.3f lat %.3f..%.3f'
          % (f.area * KM2, c, b[0], b[2], b[1], b[3]))
land_parts = [f for f, c in zip(faces, counts) if c > 0 and f.area * KM2 > 0.02]
land = unary_union(land_parts) if land_parts else city
print('  land area ~%.1f km2 across %d part(s)  (Manila: 24.98 km2 land, 42.88 km2 total)'
      % (land.area * KM2, len(land_parts)))
city_prep = prep(land.buffer(0.0009))   # ~100 m of slack at the shoreline

HW_MAP = {
    'trunk': 'primary', 'trunk_link': 'primary',
    'primary': 'primary', 'primary_link': 'primary',
    'secondary': 'secondary', 'secondary_link': 'secondary',
    'tertiary': 'tertiary', 'tertiary_link': 'tertiary',
    'residential': 'residential',
    'living_street': 'living_street',
    'pedestrian': 'pedestrian',
    'footway': 'footway', 'path': 'footway', 'steps': 'footway',
    'corridor': 'footway', 'cycleway': 'footway', 'track': 'footway',
    'unclassified': 'unclassified', 'service': 'unclassified', 'road': 'unclassified',
}

def walkable(tags):
    if tags.get('foot') in ('no', 'private'):
        return False
    if tags.get('access') in ('private', 'no') and tags.get('foot') not in ('yes', 'designated'):
        return False
    return HW_MAP.get(tags.get('highway', '')) is not None

kept = [w for w in ways if walkable(w.get('tags', {}))]
print('  %d walkable ways' % len(kept))

# separately-mapped sidewalks, so we can *measure* sidewalk presence
side_pts = []
for w in ways:
    t = w.get('tags', {})
    if t.get('footway') == 'sidewalk' or (t.get('highway') == 'footway' and t.get('footway') == 'sidewalk'):
        for n in w.get('nodes', []):
            if n in coords:
                side_pts.append(xy(*coords[n]))
print('  %d nodes on separately-mapped sidewalks' % len(side_pts))
side_tree = cKDTree(np.array(side_pts)) if side_pts else None

# --------------------------------------------------------- graph topology --
print('building topology ...')
use = collections.Counter()
for w in kept:
    ns = w.get('nodes', [])
    for n in ns:
        use[n] += 1
    if ns:
        use[ns[0]] += 1; use[ns[-1]] += 1   # endpoints always break

junction = {n for n, c in use.items() if c >= 2 and n in coords}
print('  %d junction/endpoint nodes' % len(junction))

# every junction that three or more walkable ways touch = a real intersection
real_isect = np.array([xy(*coords[n]) for n, c in use.items()
                       if c >= 3 and n in coords]) if junction else np.zeros((0, 2))
isect_tree = cKDTree(real_isect)
print('  %d true intersections (3+ way-ends)' % len(real_isect))

# ------------------------------------------------------------ split edges --
def hav(a, b):
    dx = (a[0] - b[0]); dy = (a[1] - b[1])
    return math.hypot(dx, dy)

segments = []
for w in kept:
    ns = [n for n in w.get('nodes', []) if n in coords]
    if len(ns) < 2:
        continue
    t = w.get('tags', {})
    hw = HW_MAP[t['highway']]
    run = [ns[0]]
    for n in ns[1:]:
        run.append(n)
        if n in junction and len(run) >= 2:
            segments.append((w['id'], t, hw, run))
            run = [n]
    if len(run) >= 2:
        segments.append((w['id'], t, hw, run))
print('  %d raw segments' % len(segments))

# keep only what lies inside the city, and drop hairline stubs
recs = []
for wid, t, hw, run in segments:
    pts = [coords[n] for n in run]
    mid_i = len(pts) // 2
    mlat, mlon = pts[mid_i]
    if not city_prep.contains(Point(mlon, mlat)):
        continue
    P = [xy(la, lo) for la, lo in pts]
    length = sum(hav(P[i], P[i + 1]) for i in range(len(P) - 1))
    if length < 8:
        continue
    recs.append({'wid': wid, 'tags': t, 'hw': hw, 'nodes': run,
                 'pts': pts, 'xy': P, 'len': length})
print('  %d segments inside the city boundary' % len(recs))

# ---------------------------------------------------------------- sidewalk --
SW_TAG = {'both': 'both', 'left': 'yes', 'right': 'yes', 'yes': 'yes',
          'no': 'no', 'none': 'none', 'separate': 'both'}
INFER = {'primary': 'yes', 'secondary': 'yes', 'tertiary': 'yes',
         'residential': 'no', 'unclassified': 'no',
         'living_street': 'both', 'pedestrian': 'both', 'footway': 'both'}

def sidewalk_of(r):
    t = r['tags']
    for k in ('sidewalk', 'sidewalk:both'):
        v = t.get(k)
        if v in SW_TAG:
            return SW_TAG[v], 0                       # 0 = straight from OSM
    l, rt = t.get('sidewalk:left'), t.get('sidewalk:right')
    if l or rt:
        yes = sum(1 for v in (l, rt) if v not in (None, 'no', 'none', 'separate'))
        return ('both' if yes == 2 else 'yes' if yes == 1 else 'no'), 0
    if r['hw'] in ('footway', 'pedestrian', 'living_street'):
        return 'both', 0                              # the way *is* the walkway
    if side_tree is not None:
        mid = r['xy'][len(r['xy']) // 2]
        if len(side_tree.query_ball_point(mid, 22.0)) > 0:
            return 'both', 1                          # 1 = measured off a parallel sidewalk way
    return INFER[r['hw']], 2                          # 2 = inferred from road class

for r in recs:
    r['sw'], r['sw_src'] = sidewalk_of(r)

src_counts = collections.Counter(r['sw_src'] for r in recs)
print('  sidewalk source: %d tagged, %d parallel-footway, %d inferred'
      % (src_counts[0], src_counts[1], src_counts[2]))

# ----------------------------------------------------------------- POIs -----
print('features ...')
poi_pts = []
for el in load('pois')['elements']:
    la = el.get('lat', (el.get('center') or {}).get('lat'))
    lo = el.get('lon', (el.get('center') or {}).get('lon'))
    if la is None:
        continue
    poi_pts.append(xy(la, lo))
poi_tree = cKDTree(np.array(poi_pts))

tr_pts = []
for el in load('transit')['elements']:
    la = el.get('lat', (el.get('center') or {}).get('lat'))
    lo = el.get('lon', (el.get('center') or {}).get('lon'))
    if la is None:
        continue
    tr_pts.append(xy(la, lo))
tr_tree = cKDTree(np.array(tr_pts))
print('  %d POIs, %d transit stops' % (len(poi_pts), len(tr_pts)))

mids = np.array([r['xy'][len(r['xy']) // 2] for r in recs])
poi_counts = np.array([len(ix) for ix in poi_tree.query_ball_point(mids, 400.0)], float)
tdist, _ = tr_tree.query(mids, k=1)
DISK_KM2 = math.pi * 0.4 ** 2
idn = np.array([len(ix) for ix in isect_tree.query_ball_point(mids, 400.0)], float) / DISK_KM2
# Below ~25 m you are standing at the stop; without a floor a single segment
# touching a stop sends 1/d to 1.0 and flattens T_norm to zero everywhere else.
tdist = np.maximum(tdist, 25.0)

print('  poi_count_400m       %5.0f .. %-5.0f  median %.0f' % (poi_counts.min(), poi_counts.max(), np.median(poi_counts)))
print('  dist_to_transit_m    %5.0f .. %-5.0f  median %.0f' % (tdist.min(), tdist.max(), np.median(tdist)))
print('  intersection_density %5.0f .. %-5.0f  median %.0f' % (idn.min(), idn.max(), np.median(idn)))

# ------------------------------------------------------ normalise + score --
inv = 1.0 / tdist
# Min-max over the raw extremes lets a single outlier own the whole scale, so we
# anchor on the 2nd/98th percentile and clamp. Same shape as the original
# formula, but the resulting P/T/I actually use their full 0..1 range.
def bounds(v):
    return [float(np.percentile(v, 2)), float(np.percentile(v, 98))]

NORM = {'poi': bounds(poi_counts), 'inv': bounds(inv), 'idn': bounds(idn),
        'dist': [float(tdist.min()), float(tdist.max())],
        'method': 'min-max anchored on the 2nd and 98th percentile, clamped to [0,1]'}

def mm(v, lo, hi):
    return np.zeros_like(v) if hi == lo else np.clip((v - lo) / (hi - lo), 0, 1)

P = mm(poi_counts, *NORM['poi'])
T = mm(inv, *NORM['inv'])
I = mm(idn, *NORM['idn'])
for nm, v in (('P_norm', P), ('T_norm', T), ('I_norm', I)):
    print('  %-7s mean %.3f  median %.3f  frac<0.05 %.1f%%'
          % (nm, v.mean(), np.median(v), 100 * (v < 0.05).mean()))

wd = json.loads((ROOT / 'data.js').read_text(encoding='utf-8').split('=', 1)[1].strip().rstrip(';'))
RHO = wd['rho']
rho = np.array([RHO[r['hw']][r['sw']] for r in recs])
score = rho * (40 * P + 30 * T + 30 * I)
print('  walkability score    %5.1f .. %-5.1f  mean %.1f  median %.1f'
      % (score.min(), score.max(), score.mean(), np.median(score)))
hist, _ = np.histogram(score, bins=10, range=(0, 100))
print('  deciles 0-100:', ' '.join('%d' % h for h in hist))

# ------------------------------------------- the GBM's take on the same rows --
# Its ~2,500 one-hot identifier columns are all zero for streets it never saw;
# the three identifier *encoded* columns get the training median so that, after
# the RobustScaler, they contribute exactly zero. This is the honest way to ask
# a memorising model about new data.
sp = json.loads((HERE / 'scaler_params.json').read_text(encoding='utf-8'))
CEN, SCA = np.array(sp['center']), np.array(sp['scale'])
enc = wd['encoders']
NUM = np.zeros((len(recs), 12))
NUM[:, 0] = CEN[0]; NUM[:, 1] = CEN[1]; NUM[:, 2] = CEN[2]
NUM[:, 3] = [enc['highway'][r['hw']] for r in recs]
NUM[:, 4] = [enc['sidewalk'][r['sw']] for r in recs]
NUM[:, 5], NUM[:, 6], NUM[:, 7] = poi_counts, tdist, idn
NUM[:, 8], NUM[:, 9], NUM[:, 10], NUM[:, 11] = P, T, I, rho
NUMS = (NUM - CEN) / SCA

import warnings; warnings.filterwarnings('ignore')
import _shim, joblib  # noqa
gbm = joblib.load(ROOT / 'winning_model.pkl')
order = list(gbm.feature_names_in_)
oi = {n: i for i, n in enumerate(order)}
BIG = np.zeros((len(recs), gbm.n_features_in_))
BIG[:, :12] = NUMS
for k, r in enumerate(recs):
    for col, val in (('highway', r['hw']), ('sidewalk', r['sw'])):
        j = oi.get(col + '_' + val)
        if j is not None:
            BIG[k, j] = 1.0
gbm_score = gbm.predict(BIG)
print('  GBM score            %5.1f .. %-5.1f  mean %.1f  (%d distinct values)'
      % (gbm_score.min(), gbm_score.max(), gbm_score.mean(), len(np.unique(np.round(gbm_score, 3)))))

# ---------------------------------------------------------------- encode ----
print('encoding ...')
name_ix, names = {}, []
def nid(s):
    if s not in name_ix:
        name_ix[s] = len(names); names.append(s)
    return name_ix[s]

HW_CODES = ['footway', 'living_street', 'pedestrian', 'primary',
            'residential', 'secondary', 'tertiary', 'unclassified']
SW_CODES = ['both', 'yes', 'no', 'none']
hwc = {h: i for i, h in enumerate(HW_CODES)}
swc = {s: i for i, s in enumerate(SW_CODES)}

# routing nodes: the junctions that survive, renumbered
node_ix, node_ll = {}, []
def gid(osm_node):
    if osm_node not in node_ix:
        node_ix[osm_node] = len(node_ll)
        node_ll.append(coords[osm_node])
    return node_ix[osm_node]

streets = []
for k, r in enumerate(recs):
    a, b = gid(r['nodes'][0]), gid(r['nodes'][-1])
    geom = []
    plat = plon = 0
    for la, lo in r['pts']:
        ila, ilo = round(la * PREC), round(lo * PREC)
        geom.append(ila - plat); geom.append(ilo - plon)
        plat, plon = ila, ilo
    streets.append([
        nid(r['tags'].get('name') or r['tags'].get('ref') or ''),
        hwc[r['hw']], swc[r['sw']], r['sw_src'],
        int(poi_counts[k]), round(float(tdist[k]), 1), round(float(idn[k]), 1),
        round(float(score[k]), 2), round(float(gbm_score[k]), 2),
        a, b, round(r['len'], 1),
        geom,
    ])

nodes_enc = []
plat = plon = 0
for la, lo in node_ll:
    ila, ilo = round(la * PREC), round(lo * PREC)
    nodes_enc.append(ila - plat); nodes_enc.append(ilo - plon)
    plat, plon = ila, ilo

# --------------------------------------------------- H3 res-9, for real ----
print('h3 ...')
cells = collections.defaultdict(list)
for k, r in enumerate(recs):
    la, lo = r['pts'][len(r['pts']) // 2]
    cells[h3.latlng_to_cell(la, lo, 9)].append(k)
hexes = [[c, round(float(np.mean([score[i] for i in ix])), 2),
          round(float(np.mean([gbm_score[i] for i in ix])), 2), len(ix)]
         for c, ix in sorted(cells.items())]
print('  %d res-9 cells hold real streets (avg %.1f segments per cell)'
      % (len(hexes), len(recs) / max(1, len(hexes))))
assert all(h3.is_valid_cell(h[0]) for h in hexes), 'generated an invalid H3 cell'

# ---------------------------------------------------------------- boundary --
def rings(geom, tol=0.00004):
    g = geom.simplify(tol, preserve_topology=True)
    parts = g.geoms if isinstance(g, MultiPolygon) else [g]
    return [[[round(lo, 5), round(la, 5)] for lo, la in p.exterior.coords]
            for p in parts if p.area * KM2 > 0.02]

land_rings = rings(land)
legal_rings = rings(city, tol=0.0002)
print('  land outline: %d ring(s), %d points | legal: %d ring(s), %d points'
      % (len(land_rings), sum(len(r) for r in land_rings),
         len(legal_rings), sum(len(r) for r in legal_rings)))

payload = {
    'meta': {
        'source': 'OpenStreetMap via Overpass, City of Manila relation 103703',
        'generated_from': 'build/build_app_data.py',
        'precision': PREC,
        'counts': {'streets': len(streets), 'nodes': len(node_ll), 'hexes': len(hexes),
                   'pois': len(poi_pts), 'transit': len(tr_pts),
                   'intersections': int(len(real_isect))},
        'sidewalk_sources': {'osm_tag': src_counts[0], 'parallel_footway': src_counts[1],
                             'inferred': src_counts[2]},
    },
    'schema': ['name', 'hw', 'sw', 'swSrc', 'poi', 'dist', 'idn',
               'score', 'gbm', 'a', 'b', 'len', 'geom'],
    'hwCodes': HW_CODES,
    'swCodes': SW_CODES,
    'swSrcCodes': ['OSM tag', 'mapped sidewalk nearby', 'inferred from road class'],
    'names': names,
    'nodes': nodes_enc,
    'streets': streets,
    'hexes': hexes,
    'norms': NORM,
    # Real Manila scores bunch up in the bottom fifth of the 0-100 rubric, so an
    # absolute colour ramp renders the whole city one flat colour. These decile
    # breaks let the map colour by rank within Manila while popups keep showing
    # the true score.
    'breaks': {
        'score': [round(float(np.percentile(score, q)), 2) for q in range(0, 101, 10)],
        'gbm': [round(float(np.percentile(gbm_score, q)), 2) for q in range(0, 101, 10)],
    },
    'stats': {
        'score': {'min': round(float(score.min()), 2), 'max': round(float(score.max()), 2),
                  'mean': round(float(score.mean()), 2), 'median': round(float(np.median(score)), 2)},
        'gbm': {'min': round(float(gbm_score.min()), 2), 'max': round(float(gbm_score.max()), 2),
                'mean': round(float(gbm_score.mean()), 2), 'median': round(float(np.median(gbm_score)), 2)},
    },
    'rho': RHO,
    'boundary': land_rings,        # the land the city stands on
    'boundaryLegal': legal_rings,  # the admin relation, incl. the bay jurisdiction
    'areaKm2': round(land.area * KM2, 2),
}

out = ROOT / 'manila.js'
with out.open('w', encoding='utf-8') as f:
    f.write('/* Auto-generated by build/build_app_data.py from OpenStreetMap.\n')
    f.write('   City of Manila (OSM relation 103703). Do not hand-edit. */\n')
    f.write('window.MANILA = ')
    json.dump(payload, f, ensure_ascii=False, separators=(',', ':'))
    f.write(';\n')
print('manila.js written: %.2f MB' % (out.stat().st_size / 1e6))
