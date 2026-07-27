/*
 * preprocess.js
 * -----------------------------------------------------------------------
 * Rebuilds, in vanilla JS, the exact preprocessing pipeline described in
 * app_intelligence.json:
 *   1. One-hot encode osmid, name, h3_res9, highway, sidewalk
 *   2. Assemble the 2,513-wide vector in MODEL_META.expected_feature_order
 *   3. Robust-scale the raw-scale numeric columns
 *
 * NOTE ON AN UNAVOIDABLE ASSUMPTION:
 * app_intelligence.json tells us `scaler_used: "robust"` but does NOT ship
 * the actual training-set median/IQR used to fit that scaler. Those numbers
 * live inside the (missing) trained pipeline, not in the metadata file.
 * As the closest available substitute, this file computes median/IQR from
 * the 1,000-row sample embedded in segments_data.js and uses that as a
 * stand-in. It is a reasonable local approximation, NOT the original
 * scaler — swap in the real values below (ROBUST_STATS) if you have them.
 * P_norm / T_norm / I_norm / rho_phantom already look pre-normalized to
 * 0–1 in the source data, so they are passed through unscaled.
 * -----------------------------------------------------------------------
 */

const RAW_SCALE_COLUMNS = ['poi_count_400m', 'dist_to_transit_m', 'intersection_density'];

function median(arr) {
  const s = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}
function quartile(arr, q) {
  const s = [...arr].sort((a, b) => a - b);
  const pos = (s.length - 1) * q;
  const base = Math.floor(pos), rest = pos - base;
  return s[base + 1] !== undefined ? s[base] + rest * (s[base + 1] - s[base]) : s[base];
}

// Computed once from the embedded sample (see note above).
const ROBUST_STATS = (() => {
  const cols = { poi_count_400m: [], dist_to_transit_m: [], intersection_density: [] };
  SEGMENTS.forEach(s => {
    cols.poi_count_400m.push(s.poi);
    cols.dist_to_transit_m.push(s.dist);
    cols.intersection_density.push(s.idens);
  });
  const stats = {};
  for (const k in cols) {
    const med = median(cols[k]);
    const iqr = quartile(cols[k], 0.75) - quartile(cols[k], 0.25);
    stats[k] = { median: med, iqr: iqr || 1 };
  }
  return stats;
})();

function robustScale(value, colName) {
  const st = ROBUST_STATS[colName];
  if (!st) return value;
  return (value - st.median) / st.iqr;
}

/**
 * Build the 2,513-length model input vector for a given segment-like record.
 * record = { o, n, h, hw, sw, oe, ne, he, hwe, swe, poi, dist, idens, p, t, i, rho }
 */
function buildFeatureVector(record) {
  const order = MODEL_META.expected_feature_order;
  const vec = new Array(order.length).fill(0);

  const scaled = {
    poi_count_400m: robustScale(record.poi, 'poi_count_400m'),
    dist_to_transit_m: robustScale(record.dist, 'dist_to_transit_m'),
    intersection_density: robustScale(record.idens, 'intersection_density'),
  };

  const directValues = {
    osmid_encoded: record.oe,
    name_encoded: record.ne,
    h3_res9_encoded: record.he,
    highway_encoded: record.hwe,
    sidewalk_encoded: record.swe,
    poi_count_400m: scaled.poi_count_400m,
    dist_to_transit_m: scaled.dist_to_transit_m,
    intersection_density: scaled.intersection_density,
    P_norm: record.p,
    T_norm: record.t,
    I_norm: record.i,
    rho_phantom: record.rho,
  };

  const oneHotChecks = [
    { prefix: 'osmid_', match: record.o },
    { prefix: 'name_', match: record.n },
    { prefix: 'h3_res9_', match: record.h },
    { prefix: 'highway_', match: record.hw },
    { prefix: 'sidewalk_', match: record.sw },
  ];

  order.forEach((colName, idx) => {
    if (colName in directValues) {
      vec[idx] = directValues[colName];
      return;
    }
    for (const { prefix, match } of oneHotChecks) {
      if (colName.startsWith(prefix) && colName.slice(prefix.length) === String(match)) {
        vec[idx] = 1;
        return;
      }
    }
  });

  return vec;
}
