import json, warnings, pathlib
warnings.filterwarnings('ignore')
import _shim  # noqa
import joblib, numpy as np, h3

HERE = pathlib.Path(__file__).resolve().parent.parent
m = joblib.load(HERE / 'winning_model.pkl')
s = joblib.load(HERE / 'scaler.pkl')

names = list(m.feature_names_in_)
used = sorted({int(f) for e in m.estimators_ for f in e[0].tree_.feature if f >= 0})
blocks = {'numeric': (0, 12), 'osmid': (12, 1011), 'name': (1011, 1504),
          'h3_res9': (1504, 2503), 'highway': (2503, 2510), 'sidewalk': (2510, 2513)}
print('features used in splits:', len(used))
for b, (lo, hi) in blocks.items():
    k = [i for i in used if lo <= i < hi]
    print('  %-9s %3d used  ->' % (b, len(k)), [names[i] for i in k][:8])

c, sc = s.center_, s.scale_
print()
print('scaler: cols 12+ all center==0 ?', bool(np.all(c[12:] == 0)),
      '| all scale==1 ?', bool(np.all(sc[12:] == 1)))
print('center[:12]', np.round(c[:12], 6).tolist())
print('scale [:12]', np.round(sc[:12], 6).tolist())

print()
raw = (HERE / 'data.js').read_text(encoding='utf-8')
payload = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])
cells = [r[2] for r in payload['segments']]
lat, lon = zip(*[h3.cell_to_latlng(x) for x in cells])
lat, lon = np.array(lat), np.array(lon)
print('SYNTHETIC H3 CELL EXTENT')
print('  lat %.5f .. %.5f   lon %.5f .. %.5f' % (lat.min(), lat.max(), lon.min(), lon.max()))
print('  Manila bbox      14.55080 .. 14.63955   120.79170 .. 121.02617')
inb = ((lat >= 14.5508) & (lat <= 14.6395) & (lon >= 120.7917) & (lon <= 121.0262))
print('  inside Manila bbox: %.1f%%   unique cells %d/%d' % (100 * inb.mean(), len(set(cells)), len(cells)))
print('  centroid of synthetic cells: %.5f, %.5f' % (lat.mean(), lon.mean()))
