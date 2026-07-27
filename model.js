/*
 * model.js — DROP-IN SLOT FOR YOUR TRAINED MODEL
 * -----------------------------------------------------------------------
 * Your message mentioned a model.js with a native `score(input)` function,
 * but that file wasn't actually attached to this conversation (only
 * app_intelligence.json and the CSV came through). This file is a
 * placeholder so the app runs end-to-end today.
 *
 * TO GO LIVE WITH YOUR REAL MODEL:
 * Replace the body of `score()` below with your exported function.
 * It must accept the 2,513-length numeric array built by
 * preprocess.js's buildFeatureVector() (ordered per
 * MODEL_META.expected_feature_order) and return a single number
 * (the predicted true_walkability_score_v2).
 *
 * Until then, this fallback returns a rough, clearly-labeled estimate
 * using only the top-5 globally influential features (rho_phantom,
 * P_norm, highway_encoded, poi_count_400m, intersection_density) with
 * hand-picked weights — it is NOT the trained Gradient Boosting model
 * and will not match its accuracy.
 * -----------------------------------------------------------------------
 */

const MODEL_IS_PLACEHOLDER = true;

function score(inputVector) {
  const order = MODEL_META.expected_feature_order;
  const idx = name => order.indexOf(name);

  const rho = inputVector[idx('rho_phantom')] || 0;
  const p = inputVector[idx('P_norm')] || 0;
  const hwEnc = inputVector[idx('highway_encoded')] || 0;
  const poiScaled = inputVector[idx('poi_count_400m')] || 0;
  const idensScaled = inputVector[idx('intersection_density')] || 0;

  // Crude, transparent linear combination — demo purposes only.
  const raw =
    18 +
    rho * 22 +
    p * 20 +
    poiScaled * 6 -
    Math.abs(hwEnc - 4) * 2 +
    idensScaled * 5;

  return Math.max(0, Math.min(100, raw));
}
