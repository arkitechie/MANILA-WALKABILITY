# Manila Walkability

A static single-page app over the **real** street network of the City of Manila.
Click any street to score it, or drop two pins and compare three walking routes.
No backend, no build step at runtime, no framework.

```
index.html      the whole app — markup, CSS, logic
manila.js       21,135 real Manila street segments + features + scores  (1.9 MB, generated)
model.js        the analytic scorer            window.score(input) -> Number
model_gbm.js    winning_model.pkl ported to JS window.MODEL_GBM     (generated)
data.js         the original 1,000-row CSV export + encoders (kept for reference)
build/          the Python pipeline that regenerates manila.js and model_gbm.js
```

## Run it

```bash
python -m http.server 8000     # then open http://localhost:8000
```

Opening `index.html` directly off the filesystem also works — nothing uses
`fetch()`. An internet connection is needed for Leaflet, h3-js and the basemap
tiles; your data and both models stay local.

---

## What changed, and why

### 1. The map is now actually Manila

The previous version placed everything by decoding the `h3_res9` column from the
CSV. **All 1,000 of those values fail H3 validation** — `89653a32abc025d` and its
siblings are not real cell indices, they are hex-shaped strings. They decode to
nothing, so nothing could ever land in the right place.

```
H3 AUDIT: 0 of 1000 h3_res9 values are valid H3 cells (0.0%)
```

Street names, coordinates and features in that file were not consistent with one
another either — a row labelled *Roxas Boulevard* carried no information tying it
to Roxas Boulevard. So the map was rebuilt from OpenStreetMap.

### 2. Every street is real, and every street is clickable

`build/fetch_osm.py` pulls OSM relation **103703** (City of Manila) through
Overpass; `build/build_app_data.py` turns it into block-level segments and
measures each one:

| feature | how it is measured |
|---|---|
| `poi_count_400m` | destinations (amenity/shop/leisure/tourism/office/healthcare) within 400 m of the segment midpoint — 10,526 indexed |
| `dist_to_transit_m` | metres to the nearest bus, jeepney, LRT/MRT or rail stop — 906 indexed |
| `intersection_density` | true junctions (3+ way-ends) per km² within 400 m — 13,614 indexed |
| `highway` | OSM class, mapped onto the model's eight-level vocabulary |
| `sidewalk` | OSM tag where present; else a separately-mapped parallel sidewalk way within 22 m; else inferred from road class **and flagged** |

Result: **21,135 segments**, **17,362 junctions**, **42.55 km²**. Single click
scores the block you hit; double-click scores the whole named street,
length-weighted. Snapping runs off a ~245 m grid index, so it is instant.

### 3. Correct hexes

H3 res-9 cells are now computed from real segment positions with
`h3.latlng_to_cell`, and the build asserts every one of them validates. **449
cells** hold real streets, ~47 segments each.

### 4. Both boundaries

OSM relation 103703 covers **178.9 km²**, because the City of Manila's
administrative boundary extends far into Manila Bay. Cutting that polygon along
the real OSM coastline splits it into a 136 km² water face holding **zero**
street nodes and a 42.3 km² land face holding all of them.

- **City boundary** (solid black, on by default) — the land.
- **Legal boundary** (dashed grey, off by default) — the full admin relation,
  bay jurisdiction included.

### 5. `winning_model.pkl` → JavaScript

`build/export_model.py` reads the pickle and emits `model_gbm.js`: 100 trees,
depth 3, 1,400 nodes, plus the **real fitted RobustScaler** from `scaler.pkl`
(its columns 12+ are exactly identity, so only the 12 numeric columns transform).

Verified against scikit-learn 1.6.1 on all 1,000 training rows:

```
JS-mirror vs sklearn: max abs diff = 7.9e-11
```

The app re-runs a 24-row version of that check **in your browser on load** — the
chip in the header turns green with the measured Δ.

> The pickle was written where scikit-learn's Cython loss module answered to the
> bare name `_loss`, so `joblib.load` raises `ModuleNotFoundError: No module
> named '_loss'` on a clean install. `build/_shim.py` aliases it.

**Read the GBM's output with care.** About 2,500 of its 2,513 inputs are one-hot
*row identifiers* (`osmid`, `name`, `h3_res9`), which are all-zero for any street
it never saw. On real Manila streets only the eight genuine columns do any work.
The identifier `*_encoded` columns are fed the training median so that, after the
RobustScaler, they contribute exactly zero — the honest way to ask a memorising
model about new data. Switch models in the **Method** tab.

### 6. Three route alternatives

A* over the real pedestrian graph, minimising

```
sum( length x (1 + alpha x (1 - rank)) )
```

where `rank` is the segment's walkability percentile within Manila. The
multiplier bottoms out at 1, so straight-line distance stays an admissible
heuristic.

| route | alpha | reads as |
|---|---|---|
| Most walkable | 8 | willing to detour a long way for better streets |
| Balanced | 2 | a reasonable compromise |
| Shortest | 0 | pure distance |

Each is drawn in its own colour **and** dash pattern **and** carries a direct
label. Routes that come out identical are marked as such rather than padded out.

### 7. Colour

Palette sampled from `OS.png`: cream `#F5EBDE`, black, indigo `#50488E`, sage
`#B1D198`, coral `#F26B6C`, amber `#FFC234`. The basemap is greyscaled; colour is
reserved for data.

- **Walkability** — a 7-step single-hue indigo ramp, `#A399C9` → `#2C2358`,
  monotone in lightness, light end 2.24:1 against cream.
- **Routes** — `#2E7D32` / `#B8860B` / `#F26B6C`, validated all-pairs. Worst CVD
  ΔE is 7.2, inside the 6–8 band, which is why every route also gets a dash
  pattern and a label.

Real Manila scores bunch low (median 11.8 of 100), so the map colours by **rank
within Manila** by default — each shade then holds a similar number of streets.
The *Colour* button switches to the absolute scale; popups always show the true
score.

---

## Two things worth knowing about the numbers

**1. The target is a closed-form rule.** Regressing
`true_walkability_score_v2` on its normalised components recovers, across all
1,000 rows:

```
true_walkability_score_v2 = rho_phantom x (40*P_norm + 30*T_norm + 30*I_norm)
```

Coefficients 40.0001 / 30.0000 / 29.9992, intercept −0.0003, **R² = 0.99999996**,
max absolute error 0.005 — pure 2-decimal rounding in the CSV. That rule is
`model.js`, and it is the app's default because it uses only measured features
and therefore generalises to streets nobody surveyed. The saved GBM scores
0.9855, *below* the expression it was trying to learn.

**2. Normalisation was re-anchored.** P, T and I are min–max scaled on the **2nd
and 98th percentile** of real Manila values, then clamped. Raw min–max let one
segment standing on top of a jeepney stop drive `1/dist` to 1.0 and flatten
`T_norm` to zero everywhere else. The transit distance is also floored at 25 m.

## Known limits

- **46% of sidewalk values are inferred.** OSM carries no sidewalk tag on 9,700
  of the 21,135 segments, so road class stood in — arterials assumed to have one,
  residential assumed not. Those segments are flagged in the Street panel.
  Sidewalk presence multiplies the score through `rho_phantom`, so this is the
  largest single source of uncertainty on the map.
- **Scores are a rubric, not a survey.** Nothing here measures flooding, shade,
  crime, pavement condition or air quality.
- **Routing respects OSM's topology, including its gaps.** If two points are not
  connected in OSM, the app says so rather than inventing a path.
- **Light theme only** — a deliberate choice to match the `OS.png` look.
- The original 1,000 rows survive as the off-by-default *Original survey* layer,
  laid out on a reference grid and labelled as unplaced. Those dots are not real
  locations, because that data never had any.

## Regenerating

```bash
pip install scikit-learn==1.6.1 joblib numpy scipy shapely h3 requests

python build/export_model.py      # winning_model.pkl + scaler.pkl -> model_gbm.js
python build/fetch_osm.py         # Overpass -> build/cache/*.json   (~10 MB, cached)
python build/fetch_coastline.py
python build/build_app_data.py    # cache -> manila.js
```

`build/drive.py` and `build/zoomcheck.py` drive the app in headless Chrome over
the DevTools protocol — real clicks, console capture and screenshots — if you
want to re-verify after changing anything.
