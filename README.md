# Manila Walkability — H3 res-9 transect explorer

A static single-page app. No backend, no build step, no framework.

```
index.html     the whole app — markup, CSS, logic
data.js        1,000 street segments + encoders + scaler params (generated)
model.js       score(input) → Number   ← replace with your export
README.md      this file
```

## Run it locally

**Option A — just open it.** Double-click `index.html`. Browsers allow
`<script src="...">` from `file://` in the same folder, so `data.js` and
`model.js` both load. Nothing here uses `fetch()`, which is what usually
breaks local pages.

**Option B — a local server** (recommended; avoids any `file://` edge cases):

```bash
cd manila-walkability
python3 -m http.server 8000
# → http://localhost:8000
```

or `npx serve .` if you prefer Node.

An internet connection is needed on first load for Leaflet, h3-js, the
basemap tiles, and the webfonts. Your data and model stay local.

## Plugging in your real model

`model.js` was not in the upload, so the file shipped here is a placeholder.
Replace it with your export. The only contract:

```js
window.score = function (input) { /* … */ return number; };
```

`input` is a `Float64Array` of length **2513**, ordered exactly as
`expected_feature_order` in `app_intelligence.json`:

| block | columns | index range |
|---|---|---|
| numeric (robust-scaled) | 12 | 0 – 11 |
| `osmid` one-hot | 999 | 12 – 1010 |
| `name` one-hot | 493 | 1011 – 1503 |
| `h3_res9` one-hot | 999 | 1504 – 2502 |
| `highway` one-hot | 7 | 2503 – 2509 |
| `sidewalk` one-hot | 3 | 2510 – 2512 |

One-hot blocks use `drop_first=True`, so a row whose category is the dropped
level (`osmid_[10131289, 10874204]`'s predecessor, `highway_footway`,
`sidewalk_both`) contributes an all-zero block. That is correct, not a bug —
rows legitimately carry between 2 and 5 set bits.

Set `window.MODEL_INFO = { kind: 'gbm' }` in your file and the status chip in
the header turns green.

### Scaled or raw?

`app_intelligence.json` names `robust` as the scaler but doesn't ship the
fitted medians and IQRs, so `data.js` recomputes them from the CSV. Whether
your export expects pre-scaled input depends on how you serialised it — the
**"feed robust-scaled vector to score()"** checkbox in the Predict tab flips
between the two. If predictions look wildly off, flip it.

## What the app does

**Route tab.** Click the map to drop A, click again for B. Clicks snap to the
nearest surveyed street. The route follows `h3.gridPathCells` across the res-9
grid; the app reports the mean walkability along it, path distance, straight-line
distance, and cell count. The *walk profile* strip underneath shows every cell
in the transect as a hexagon coloured by its score — faded, dashed hexagons are
inverse-distance estimates for cells with no surveyed segment, so you can see
at a glance how much of a route is measured versus interpolated.

**Predict tab.** All 17 original features. The five categorical columns are
dropdowns; their `*_encoded` partners fill in automatically, as do `P_norm`,
`T_norm`, `I_norm` and `rho_phantom` (untick **auto** to override any of them).
Clicking a hexagon on the map loads that segment into the form.

**Method tab.** Pipeline metadata and the caveats below.

## Two things worth knowing about the data

**1. The target is a closed-form rule.** Regressing the target on the
normalised components recovers, across all 1,000 rows:

```
true_walkability_score_v2 = rho_phantom × (40·P_norm + 30·T_norm + 30·I_norm)
```

Fitted coefficients: 40.0001 / 30.0000 / 29.9992, intercept −0.0003,
**R² = 0.99999996**, max absolute error 0.005 — pure 2-decimal rounding in the CSV.
The inputs are deterministic too: `P_norm` and `I_norm` are min-max scalings of
`poi_count_400m` and `intersection_density`; `T_norm` is a min-max scaling of
`1/dist_to_transit_m`; and `rho_phantom` is a lookup on `(highway, sidewalk)` —
footway/tertiary/unclassified 0.4, living_street/pedestrian 1.0, and
primary/residential/secondary penalised when the sidewalk is `no`/`none`.

Your saved GBM scores **0.9855**, which is *below* the three-term expression it
was trying to learn. That gap is the model losing ground to noise, not finding
signal. The placeholder `model.js` implements the exact rule, which is why the
Predict tab reproduces observed scores to the cent.

**2. About 2,500 of the 2,513 features are row identifiers.** `osmid` and
`h3_res9` are unique on all 1,000 rows, and `name` is near-unique at 494 levels.
One-hot encoding them gives the model a private column per row — it can memorise
the training set, and every one of those columns is zero for any street it has
not already seen. If you plan to score new streets, the honest feature set is the
eight real columns: `highway`, `sidewalk`, `poi_count_400m`, `dist_to_transit_m`,
`intersection_density`, and the three normalised terms. The app still builds the
full 2,513-length vector because that's what your metadata specifies.

## Known limits

- **OSMnx has no browser build.** It's a Python library that wraps GeoPandas,
  NetworkX and Shapely — none of which run client-side. The app uses **Leaflet**
  for rendering and **h3-js** for the res-9 grid, which together cover what
  OSMnx would have given you here. If you want true street-network routing
  rather than grid-path routing, export the OSMnx graph to GeoJSON from Python
  and load it as an extra layer.
- **No coordinates in the CSV.** Every position on the map is decoded from the
  `h3_res9` index via `h3.cellToLatLng`, so segments plot at cell centroids
  rather than along their real geometry.
- **The dashed outline is a convex hull** of the 1,000 surveyed centroids — the
  surveyed extent, not Manila's legal boundary. For the administrative border,
  define `window.MANILA_BOUNDARY` as a GeoJSON polygon before `index.html`'s
  main script runs and swap it into `boundLayer`.
- **Route distance is grid distance.** It sums haversine hops between res-9 cell
  centroids, so it approximates a walk over the hex lattice and will read a
  little longer than a straight line and a little shorter than the real
  pavement route.

## Regenerating `data.js`

`build_data.py` reads the CSV and the JSON and rewrites `data.js`:

```bash
python3 build_data.py
```
