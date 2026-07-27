# Manila Walkability Score

A static single-page app over the **real** street network of the City of Manila.
Click any street to score it, or drop two pins and compare three walking routes.
No backend, no build step at runtime, no framework.

```
index.html      the whole app — markup, CSS, logic
manila.js       24,442 real Manila street segments + features + scores  (2.2 MB, generated)
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

Result: **24,442 segments**, **18,293 junctions**, **42.55 km²**. Single click
scores the block you hit; double-click scores the whole named street,
length-weighted. Snapping runs off a ~245 m grid index, so it is instant.

### 3. Correct hexes

H3 res-9 cells are now computed from real segment positions with
`h3.latlng_to_cell`, and the build asserts every one of them validates. **449
cells** hold real streets, ~54 segments each.

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

### 6. One direct route, two alternatives

A* over the real pedestrian graph, minimising

```
sum( length x (1 + alpha x (1 - rank)) )
```

where `rank` is the segment's walkability percentile within Manila. The
multiplier bottoms out at 1, so straight-line distance stays an admissible
heuristic — verified against a plain Dijkstra on 40 random pairs, **identical to
0.000000 m**.

| route | alpha | colour | dash | shown as |
|---|---|---|---|---|
| **Direct route** | 0 | `#C08A00` golden | short | the default — genuinely the nearest way |
| Alternative — more walkable | 8 | `#1F6FB2` blue | long | detours for better streets |
| Alternative — balanced | 2 | `#2E7D32` green | medium | a mild compromise |

**The direct route is what you get by default**, painted in the walkability ramp.
Earlier the *most walkable* route led, and because it detours a median 1.10× and
up to 1.81× further, routes routinely looked like the app had ignored the obvious
way there. The two alternatives now have to justify their extra metres, and the
cards say so explicitly: *"+209 m (7% longer) for +11.3 walkability."* When an
alternative buys nothing it says *"for no real gain — skip it."*

The alternatives keep their identity as **coloured broken lines**. Validated
all-pairs against the cream surface — worst CVD ΔE 9.6, comfortably clear of the
floor. Gold is the one below 3:1, so every alternate also carries a cream casing,
its own dash length and a named card; colour never has to carry it alone.

**Routes start and finish at your pins, not at the nearest junction.** The search
is seeded from *both* ends of the segment you clicked and finishes at whichever
end of the destination segment is cheaper once its own tail walk is counted — one
search per profile, not four. Before this, the line began at a junction that on a
long street could be **hundreds of metres** from the marker (the longest segment
in Manila is 1,221 m), which looked exactly like a routing error. The tail walk
is included in the reported distance and in the walk profile.

Where all three come back as the same path — which happens often in Manila's
grid — the app says so plainly instead of padding the list out.

### 7. Colour, and staying out of the way

Palette sampled from `OS.png`: cream `#F5EBDE`, black, indigo `#50488E`, sage
`#B1D198`, coral `#F26B6C`, amber `#FFC234`. The basemap is greyscaled; colour is
reserved for data.

**The walkability ramp runs dark purple → coral**, least walkable to most:

```
#2c2358  #4d2676  #742687  #9c298b  #c03583  #dd4d77  #f26b6c
```

Generated in OKLCH so lightness climbs evenly — ΔL 0.065–0.067 at every step,
light end 2.51:1 against cream, hue spread 16°. It travels two hues rather than
the usual one, which is safe **only** because lightness is strictly monotonic:
the ramp survives greyscale, print and every colour-blindness simulation on
lightness alone, with hue as a bonus channel rather than the carrier.

**The overlay is off by default.** Coloured lines drawn over every street sit on
top of the basemap's street labels and make them unreadable, so the map opens
clean and monochrome. The colour appears where it earns its place:

- **Hover** any street → a bubble with its name, score and rank, and a chip in
  its ramp colour.
- **Draw a route** → the selected route is painted *segment by segment* in the
  ramp, so you can see which stretches are pleasant and which are grim. The two
  alternatives sit underneath as coloured broken lines; click a card to swap.
- **Walkability button** → paints the ramp across all 24,442 streets. While a
  route is on screen the overlay dims to 32% so the two never fight.

Real Manila scores bunch low (median 11.8 of 100), so the map colours by **rank
within Manila** by default — each shade then holds a similar number of streets.
The *Colour* button switches to the absolute scale; popups always show the true
score.

### 8. Click anywhere

You never have to hit a line. Click a building, a block, a park — the nearest
street is found through a ~245 m grid index and the pin snaps to it. First click
sets **A**, second sets **B**, third starts a fresh pair. *Set A* / *Set B*
override that order.

The map opens over the city core (Binondo / Intramuros / Ermita) at zoom 14.75,
close enough that street names and hover bubbles are immediately usable.
*Fit Manila* pulls back to the whole city.

### 9. Reading the number

A bare "13.7" means nothing without context, so the Route tab carries a
**What the score means** card and the header carries the city average
permanently:

```
city-wide average   13.6      median 11.8  (half of Manila is below this)
across all 24,442 segments · scale runs 0-100, Manila uses 0.0-79.7

  under 6.1     Poor                       bottom 20% of Manila
  6.1-11.8      Below average for Manila   bottom half
  11.8-19.9     Typical Manila street      middle of the pack
  19.9-30.8     Good                       top 20%
  30.8-44.9     Very good                  top 5%
  44.9 and up   Exceptional                top 1%

  lowest   0.0   MICT South Access Road        [show]
  highest  79.7  unnamed pedestrian street     [show]
```

The **mean leads and the median sits beside it**, because Manila's distribution
is skewed — a handful of excellent streets pull the mean above what a typical
street actually scores, and showing both makes that visible instead of hiding it.
The band edges are real percentiles recomputed from the data, not hardcoded, so
they stay correct when you switch models. Lowest and highest are clickable: the
map flies there and opens the street's panel.

The Method tab carries the fuller breakdown, including why the practical ceiling
is 79.7 rather than 100 — reaching 100 would need a pedestrian-only street that
is simultaneously in Manila's densest commercial block, on top of a transit stop,
and at its busiest junction. Nowhere is all four at once.

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

- **45% of sidewalk values are inferred.** OSM carries no sidewalk tag on 10,892
  of the 24,442 segments, so road class stood in — arterials assumed to have one,
  residential assumed not. Those segments are flagged in the Street panel.
  Sidewalk presence multiplies the score through `rho_phantom`, so this is the
  largest single source of uncertainty on the map.
- **Scores are a rubric, not a survey.** Nothing here measures flooding, shade,
  crime, pavement condition or air quality.
- **Routing respects OSM's topology, including its gaps.** If two points are not
  connected in OSM, the app says so rather than inventing a path. The graph is
  now **99 components with 97.5% of nodes in the largest** — it was 572 components
  and 82% until the build stopped discarding segments under 8 m. Those stubs
  carry nobody on their own but they are exactly what holds a street network
  together, and dropping them was cutting Manila into islands.
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

`build/drive.py`, `build/drive2.py` and `build/zoomcheck.py` drive the app in
headless Chrome over the DevTools protocol — real clicks, real hover, console
capture and screenshots — if you want to re-verify after changing anything.
`drive2.py` additionally reads the overlay canvas back pixel by pixel to confirm
the ramp is actually painting, which a screenshot alone cannot prove.
