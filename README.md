# Manila Walkability Explorer

A static, single-page app that maps the 1,000 street segments in
`Manila_City_True_Walkability_ML_Ready_v2.csv` on an interactive H3 res‑9
grid. Click any two hex cells to get the average walkability score and
distance of the walking route between them.

## Run it locally

No build step, no backend. From this folder:

```bash
python3 -m http.server 8000
```

Then open **http://localhost:8000** in a browser. (A plain `file://` open
mostly works too, but some browsers block `fetch`/module-adjacent behavior
on `file://`, so the local server is the safe route.)

## Files

| File | Purpose |
|---|---|
| `index.html` | Page shell / layout |
| `style.css` | "Manila folder" civic-map visual design |
| `segments_data.js` | The 1,000 CSV rows, pre-parsed into JS |
| `app_meta.js` | Your `app_intelligence.json`, embedded as JS |
| `preprocess.js` | One-hot encoding + robust scaling → 2,513-wide feature vector |
| `model.js` | **Placeholder** `score(input)` — see below |
| `app.js` | Map rendering, routing graph, all UI wiring |

## Two things I had to work around

**1. `model.js` wasn't actually attached to the conversation.**
Only `app_intelligence.json` and the CSV came through — no file with a
`score(input)` function. I built a placeholder `model.js` with a clearly
labeled fallback formula so the app runs end-to-end today. To go live:
replace the body of `score()` in `model.js` with your real exported
function. It must accept the 2,513-length array built by
`preprocess.js`'s `buildFeatureVector()` (already in your training
feature order) and return one number.

**2. The CSV has no lat/lng or street polylines — only an H3 res‑9 index.**
So the map plots each segment's H3 hex boundary/centroid (via `h3-js`),
not a literal traced street shape. It's genuinely tied to your real data,
just at hex-grid resolution rather than vector-street resolution.

Also, a small correction on the tooling: **OSMnx is a Python library and
can't run in a browser**, so it isn't part of this static app. In its
place, `app.js` builds a k-nearest-neighbor graph (k=6) over the H3
centroids and runs Dijkstra's algorithm on it for routing — this is what
powers the "click point A, click point B" average score + distance.

**3. Robust-scaler statistics weren't in `app_intelligence.json`.**
The metadata says `"scaler_used": "robust"` but doesn't ship the
training-set median/IQR. `preprocess.js` computes median/IQR from the
1,000-row sample instead, as a documented stand-in — swap in your real
values (`ROBUST_STATS` in `preprocess.js`) once you have them.

## What's fully real vs. approximated

- **Real, from your data:** every segment's name, road type, sidewalk
  status, POI count, transit distance, intersection density, and its
  actual `true_walkability_score_v2` from the trained model.
- **Approximated:** the walking route between two clicked points (k-NN
  graph over hex centroids rather than true street topology), and the
  what-if predictor (placeholder model + estimated scaler stats).

## What-if predictor panel

Since the one-hot-encoded `osmid`/`name`/`h3_res9` columns are really a
memorized identity for ~1,000 specific segments (not a generalizable
"describe any street" input), the predictor panel lets you pick an
**existing** segment and then tweak its numeric context (POI count,
transit distance, intersection density, road type, sidewalk, rho_phantom)
to see how the score would shift — a "what if we added a sidewalk here"
style tool, wired through your real encoding pipeline.
