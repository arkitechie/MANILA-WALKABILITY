/* app.js — Manila Walkability Explorer
 * Vanilla JS + Leaflet + h3-js + a client-side k-NN graph over H3 res-9 cells.
 *
 * IMPORTANT CONTEXT FOR ANYONE EXTENDING THIS FILE:
 * - The source CSV has no lat/lng or street polylines, only an H3 res-9
 *   index per segment. Positions here are H3 cell centroids/boundaries
 *   (via h3-js), not the literal street geometry.
 * - "osmnx" is a Python library and cannot run in a browser, so it isn't
 *   used here. Instead, connectivity between segments is approximated
 *   with a k-nearest-neighbour graph built from H3 centroids (k=6),
 *   which — combined with the real H3 grid — gives sensible, walkable-
 *   looking routes without needing a live OSM/Overpass fetch.
 */

(function () {
  // ---------- 1. Precompute centroid + boundary for every segment ----------
  SEGMENTS.forEach((s, idx) => {
    const [lat, lng] = h3.cellToLatLng(s.h);
    s.lat = lat;
    s.lng = lng;
    s.idx = idx;
  });

  // ---------- 2. Score color scale ----------
  const scores = SEGMENTS.map(s => s.score);
  const sMin = Math.min(...scores), sMax = Math.max(...scores);
  function scoreColor(v) {
    const t = Math.max(0, Math.min(1, (v - sMin) / (sMax - sMin)));
    // coral -> amber -> teal
    if (t < 0.5) return lerpColor('#d94f30', '#d9a441', t / 0.5);
    return lerpColor('#d9a441', '#1f8f6b', (t - 0.5) / 0.5);
  }
  function lerpColor(a, b, t) {
    const pa = hexToRgb(a), pb = hexToRgb(b);
    const r = Math.round(pa.r + (pb.r - pa.r) * t);
    const g = Math.round(pa.g + (pb.g - pa.g) * t);
    const bl = Math.round(pa.b + (pb.b - pa.b) * t);
    return `rgb(${r},${g},${bl})`;
  }
  function hexToRgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
  }

  // ---------- 3. Haversine distance (meters) ----------
  function haversine(lat1, lng1, lat2, lng2) {
    const R = 6371000;
    const toRad = d => (d * Math.PI) / 180;
    const dLat = toRad(lat2 - lat1), dLng = toRad(lng2 - lng1);
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(a));
  }

  // ---------- 4. Build k-NN proximity graph over H3 centroids (k=6) ----------
  function buildGraph(k) {
    const n = SEGMENTS.length;
    const adj = Array.from({ length: n }, () => []);
    for (let i = 0; i < n; i++) {
      const dists = [];
      for (let j = 0; j < n; j++) {
        if (i === j) continue;
        dists.push([haversine(SEGMENTS[i].lat, SEGMENTS[i].lng, SEGMENTS[j].lat, SEGMENTS[j].lng), j]);
      }
      dists.sort((a, b) => a[0] - b[0]);
      for (let m = 0; m < k && m < dists.length; m++) {
        const [d, j] = dists[m];
        adj[i].push([j, d]);
        adj[j].push([i, d]);
      }
    }
    return adj;
  }
  const GRAPH = buildGraph(6);

  // ---------- 5. Dijkstra ----------
  function shortestPath(src, dst) {
    const n = GRAPH.length;
    const dist = new Array(n).fill(Infinity);
    const prev = new Array(n).fill(-1);
    const visited = new Array(n).fill(false);
    dist[src] = 0;
    for (let iter = 0; iter < n; iter++) {
      let u = -1, best = Infinity;
      for (let v = 0; v < n; v++) if (!visited[v] && dist[v] < best) { best = dist[v]; u = v; }
      if (u === -1) break;
      visited[u] = true;
      if (u === dst) break;
      for (const [v, w] of GRAPH[u]) {
        if (dist[u] + w < dist[v]) { dist[v] = dist[u] + w; prev[v] = u; }
      }
    }
    if (dist[dst] === Infinity) return null;
    const path = [];
    for (let cur = dst; cur !== -1; cur = prev[cur]) path.push(cur);
    path.reverse();
    return { path, distance: dist[dst] };
  }

  // ---------- 6. Map setup ----------
  const map = L.map('map', { preferCanvas: true, zoomControl: true }).setView([14.5995, 120.9842], 15);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution: '&copy; OpenStreetMap &copy; CARTO',
    maxZoom: 19,
  }).addTo(map);

  // Guard against any layout-timing quirks where the container reports
  // a stale size right after creation (e.g. slow CSS/font load).
  setTimeout(() => map.invalidateSize(), 50);
  window.addEventListener('resize', () => map.invalidateSize());

  const hexLayer = L.layerGroup().addTo(map);
  const polys = [];

  SEGMENTS.forEach((s, idx) => {
    const boundary = h3.cellToBoundary(s.h);
    const color = scoreColor(s.score);
    const poly = L.polygon(boundary, {
      color, weight: 1, fillColor: color, fillOpacity: 0.55,
    });
    poly.bindTooltip(`<b>${s.n}</b><br>${s.hw} · sidewalk: ${s.sw}<br>score: ${s.score.toFixed(1)}`, { sticky: true });
    poly.on('click', () => handleClick(idx));
    hexLayer.addLayer(poly);
    polys.push(poly);
  });

  document.getElementById('statSegments').textContent = SEGMENTS.length.toLocaleString();
  document.getElementById('statAvg').textContent = (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1);

  // ---------- 7. Selection + routing state ----------
  let originIdx = null, destIdx = null;
  let routeLine = null, originMarker = null, destMarker = null;

  function resetSelection() {
    originIdx = null; destIdx = null;
    polys.forEach((p, i) => p.setStyle({ weight: 1, color: scoreColor(SEGMENTS[i].score) }));
    if (routeLine) { map.removeLayer(routeLine); routeLine = null; }
    if (originMarker) { map.removeLayer(originMarker); originMarker = null; }
    if (destMarker) { map.removeLayer(destMarker); destMarker = null; }
    document.getElementById('routeResult').classList.add('hidden');
    document.getElementById('routeEmpty').classList.remove('hidden');
  }
  document.getElementById('resetRouteBtn').addEventListener('click', resetSelection);

  function pinMarker(idx, color) {
    return L.circleMarker([SEGMENTS[idx].lat, SEGMENTS[idx].lng], {
      radius: 7, color: '#12161d', weight: 2, fillColor: color, fillOpacity: 1,
    }).addTo(map);
  }

  function handleClick(idx) {
    if (originIdx === null) {
      originIdx = idx;
      polys[idx].setStyle({ weight: 3, color: '#1f8f6b' });
      if (originMarker) map.removeLayer(originMarker);
      originMarker = pinMarker(idx, '#1f8f6b');
      return;
    }
    if (destIdx === null && idx !== originIdx) {
      destIdx = idx;
      polys[idx].setStyle({ weight: 3, color: '#b8341f' });
      if (destMarker) map.removeLayer(destMarker);
      destMarker = pinMarker(idx, '#b8341f');
      computeRoute();
      return;
    }
    // Both already set (or clicked the same origin again) -> start a fresh selection
    resetSelection();
    handleClick(idx);
  }

  function computeRoute() {
    const result = shortestPath(originIdx, destIdx);
    if (!result) {
      alert('No connected walking route found between those two points in the loaded grid.');
      return;
    }
    const { path, distance } = result;
    const pathScores = path.map(i => SEGMENTS[i].score);
    const avg = pathScores.reduce((a, b) => a + b, 0) / pathScores.length;
    const worstIdx = path[pathScores.indexOf(Math.min(...pathScores))];

    if (routeLine) map.removeLayer(routeLine);
    routeLine = L.polyline(path.map(i => [SEGMENTS[i].lat, SEGMENTS[i].lng]), {
      color: '#f2e6c9', weight: 3, dashArray: '2 8', opacity: 0.95,
    }).addTo(map);

    document.getElementById('routeEmpty').classList.add('hidden');
    document.getElementById('routeResult').classList.remove('hidden');
    document.getElementById('originName').textContent = SEGMENTS[originIdx].n;
    document.getElementById('destName').textContent = SEGMENTS[destIdx].n;
    document.getElementById('avgScoreNum').textContent = avg.toFixed(1);
    document.getElementById('avgScoreNum').style.color = scoreColor(avg);
    document.getElementById('distanceVal').textContent =
      distance >= 1000 ? (distance / 1000).toFixed(2) + ' km' : Math.round(distance) + ' m';
    document.getElementById('hopsVal').textContent = path.length - 1;
    document.getElementById('worstVal').textContent = SEGMENTS[worstIdx].score.toFixed(1);

    const strip = document.getElementById('pathStrip');
    strip.innerHTML = '';
    path.forEach(i => {
      const d = document.createElement('div');
      d.style.background = scoreColor(SEGMENTS[i].score);
      d.title = `${SEGMENTS[i].n}: ${SEGMENTS[i].score.toFixed(1)}`;
      strip.appendChild(d);
    });

    const avgPoi = path.reduce((a, i) => a + SEGMENTS[i].poi, 0) / path.length;
    const avgIdens = path.reduce((a, i) => a + SEGMENTS[i].idens, 0) / path.length;
    const avgRho = path.reduce((a, i) => a + SEGMENTS[i].rho, 0) / path.length;
    const hwCounts = {};
    path.forEach(i => { hwCounts[SEGMENTS[i].hw] = (hwCounts[SEGMENTS[i].hw] || 0) + 1; });
    const dominantHw = Object.entries(hwCounts).sort((a, b) => b[1] - a[1])[0][0];

    document.getElementById('routeProfile').innerHTML = `
      <div><b>Avg. POIs / 400m:</b> ${avgPoi.toFixed(0)}</div>
      <div><b>Avg. intersection density:</b> ${avgIdens.toFixed(1)}</div>
      <div><b>Avg. rho_phantom:</b> ${avgRho.toFixed(2)}</div>
      <div><b>Dominant road type:</b> ${dominantHw}</div>
    `;
  }

  // ---------- 8. Top-5 driver list ----------
  const DRIVER_DESCRIPTIONS = {
    rho_phantom: 'Composite "phantom infrastructure" proxy — captures unmapped/informal walking infrastructure.',
    P_norm: 'Normalized pedestrian-provision score (sidewalk & crossing coverage).',
    highway_encoded: 'Road classification (residential, primary, pedestrian, etc.) — sets the baseline traffic context.',
    poi_count_400m: 'Points of interest within a 400m walk — density of destinations worth walking to.',
    intersection_density: 'Intersections per area — a classic proxy for street-network permeability.',
  };
  const driverList = document.getElementById('driverList');
  MODEL_META.top_5_influential_features.forEach(f => {
    const li = document.createElement('li');
    li.innerHTML = `<b>${f}</b><span>${DRIVER_DESCRIPTIONS[f] || 'Influential input feature for the model.'}</span>`;
    driverList.appendChild(li);
  });

  // ---------- 9. What-if predictor panel ----------
  const toggleBtn = document.getElementById('toggleWhatIf');
  const whatIfBody = document.getElementById('whatIfBody');
  toggleBtn.addEventListener('click', () => {
    whatIfBody.classList.toggle('hidden');
    toggleBtn.textContent = whatIfBody.classList.contains('hidden') ? 'expand ▾' : 'collapse ▴';
  });

  document.getElementById('whatIfNotice').innerHTML = MODEL_IS_PLACEHOLDER
    ? `⚠ <b>model.js</b> wasn't attached to this project, so predictions below come from a rough placeholder
       formula (see model.js), not your trained Gradient Boosting model. Also, exact robust-scaler
       median/IQR values weren't in app_intelligence.json, so this demo estimates them from the 1,000-row
       sample instead of the real training set. Swap in your real model.js + scaler stats to make this exact.`
    : `Predictions use your trained model via score().`;

  const segSelect = document.getElementById('segSelect');
  SEGMENTS.forEach((s, idx) => {
    const opt = document.createElement('option');
    opt.value = idx;
    opt.textContent = `${s.n} (${s.hw})`;
    segSelect.appendChild(opt);
  });

  const hwSelect = document.getElementById('hwSelect');
  const swSelect = document.getElementById('swSelect');
  [...new Set(SEGMENTS.map(s => s.hw))].sort().forEach(v => {
    const o = document.createElement('option'); o.value = v; o.textContent = v; hwSelect.appendChild(o);
  });
  [...new Set(SEGMENTS.map(s => s.sw))].sort().forEach(v => {
    const o = document.createElement('option'); o.value = v; o.textContent = v; swSelect.appendChild(o);
  });

  function fillFormFromSegment(idx) {
    const s = SEGMENTS[idx];
    hwSelect.value = s.hw;
    swSelect.value = s.sw;
    document.getElementById('poiInput').value = s.poi;
    document.getElementById('distInput').value = s.dist;
    document.getElementById('idensInput').value = s.idens;
    document.getElementById('rhoInput').value = s.rho;
  }
  segSelect.addEventListener('change', () => fillFormFromSegment(Number(segSelect.value)));
  fillFormFromSegment(0);

  document.getElementById('predictBtn').addEventListener('click', () => {
    const base = SEGMENTS[Number(segSelect.value)];
    const record = {
      ...base,
      hw: hwSelect.value,
      hwe: base.hwe, // encoded id kept from the selected real segment (identity feature)
      sw: swSelect.value,
      swe: base.swe,
      poi: Number(document.getElementById('poiInput').value),
      dist: Number(document.getElementById('distInput').value),
      idens: Number(document.getElementById('idensInput').value),
      rho: Number(document.getElementById('rhoInput').value),
    };
    const vector = buildFeatureVector(record);
    const prediction = score(vector);
    document.getElementById('predictResult').classList.remove('hidden');
    document.getElementById('predictResult').innerHTML = `
      Predicted walkability for <b>${base.n}</b> under these conditions:
      <div class="score-big" style="margin:8px 0;">
        <div class="score-number" style="font-size:32px;color:${scoreColor(prediction)}">${prediction.toFixed(1)}</div>
      </div>
      <div class="fine-print" style="margin:0;">Baseline (unedited) score for this segment: ${base.score.toFixed(1)}</div>
    `;
  });

  resetSelection();
})();
