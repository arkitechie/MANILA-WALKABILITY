"""Diagnose why a drawn route can look like it is not the direct way there.

Checks, in order of how likely they are to be the real cause:
  1. is the graph connected, or are there islands that force huge detours?
  2. does alpha=0 actually return the true shortest path? (A* vs plain Dijkstra)
  3. how far does "most walkable" (alpha=8) detour compared with shortest?
  4. how much error does snapping to a segment ENDPOINT introduce when you
     click the middle of a long street?
"""
import json, math, pathlib, random, heapq
from collections import deque

ROOT = pathlib.Path(__file__).resolve().parent.parent
raw = (ROOT / 'manila.js').read_text(encoding='utf-8')
M = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])

PREC = M['meta']['precision']
S = M['streets']
N = len(S)
F = dict(NAME=0, HW=1, SW=2, SWSRC=3, POI=4, DIST=5, IDN=6, SCORE=7, GBM=8, A=9, B=10, LEN=11, GEOM=12)

nodes, la, lo = [], 0, 0
arr = M['nodes']
for i in range(0, len(arr), 2):
    la += arr[i]; lo += arr[i + 1]
    nodes.append((la / PREC, lo / PREC))
NC = len(nodes)
print('nodes %d  segments %d' % (NC, N))

# ---------------------------------------------------------------- 1. islands
adj = [[] for _ in range(NC)]
for i, s in enumerate(S):
    a, b = s[F['A']], s[F['B']]
    if a != b:
        adj[a].append((b, i)); adj[b].append((a, i))

seen = [False] * NC
comps = []
for s0 in range(NC):
    if seen[s0]:
        continue
    q = deque([s0]); seen[s0] = True; size = 0
    while q:
        u = q.popleft(); size += 1
        for v, _ in adj[u]:
            if not seen[v]:
                seen[v] = True; q.append(v)
    comps.append((size, s0))
comps.sort(reverse=True)
print('\n1. CONNECTIVITY')
print('   components: %d' % len(comps))
print('   largest   : %d nodes (%.1f%% of the graph)' % (comps[0][0], 100 * comps[0][0] / NC))
print('   next five : %s' % [c[0] for c in comps[1:6]])
isolated = sum(1 for c in comps if c[0] <= 2)
print('   components of 1-2 nodes: %d' % isolated)

comp_id = [-1] * NC
for cid, (_, root) in enumerate(comps):
    if comp_id[root] != -1:
        continue
    q = deque([root]); comp_id[root] = cid
    while q:
        u = q.popleft()
        for v, _ in adj[u]:
            if comp_id[v] == -1:
                comp_id[v] = cid; q.append(v)

LAT0 = 14.5995
MPD_LAT, MPD_LON = 110574.0, 111320.0 * math.cos(math.radians(LAT0))
def dist_m(u, v):
    dy = (nodes[u][0] - nodes[v][0]) * MPD_LAT
    dx = (nodes[u][1] - nodes[v][1]) * MPD_LON
    return math.hypot(dx, dy)

# rank, exactly as the app computes it
order = sorted(range(N), key=lambda i: S[i][F['SCORE']])
rank = [0.0] * N
for r, i in enumerate(order):
    rank[i] = r / (N - 1)

def astar(src, dst, alpha):
    INF = float('inf')
    g = {src: 0.0}
    prev = {}
    pq = [(dist_m(src, dst), src)]
    done = set()
    while pq:
        _, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        if u == dst:
            break
        for v, si in adj[u]:
            nd = g[u] + S[si][F['LEN']] * (1 + alpha * (1 - rank[si]))
            if nd < g.get(v, INF):
                g[v] = nd; prev[v] = (u, si)
                heapq.heappush(pq, (nd + dist_m(v, dst), v))
    if dst not in done:
        return None
    edges, cur = [], dst
    while cur != src:
        u, si = prev[cur]; edges.append(si); cur = u
    return edges[::-1]

def dijkstra(src, dst):
    INF = float('inf')
    g = {src: 0.0}; prev = {}; pq = [(0.0, src)]; done = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        if u == dst:
            break
        for v, si in adj[u]:
            nd = g[u] + S[si][F['LEN']]
            if nd < g.get(v, INF):
                g[v] = nd; prev[v] = (u, si); heapq.heappush(pq, (nd, v))
    if dst not in done:
        return None
    edges, cur = [], dst
    while cur != src:
        u, si = prev[cur]; edges.append(si); cur = u
    return edges[::-1]

def length(edges):
    return sum(S[i][F['LEN']] for i in edges)

def mean_score(edges):
    L = length(edges)
    return sum(S[i][F['SCORE']] * S[i][F['LEN']] for i in edges) / L if L else 0

random.seed(7)
big = [n for n in range(NC) if comp_id[n] == 0]
pairs = []
while len(pairs) < 40:
    a, b = random.choice(big), random.choice(big)
    if a != b and 800 < dist_m(a, b) < 4000:
        pairs.append((a, b))

print('\n2. IS alpha=0 REALLY THE SHORTEST PATH? (A* vs Dijkstra, 40 pairs)')
worst = 0.0
for a, b in pairs:
    e1, e2 = astar(a, b, 0.0), dijkstra(a, b)
    if e1 is None or e2 is None:
        print('   !! no path'); continue
    worst = max(worst, length(e1) - length(e2))
print('   max extra metres A* took over true shortest: %.6f  -> %s'
      % (worst, 'CORRECT' if worst < 0.01 else 'BUG: A* IS NOT OPTIMAL'))

print('\n3. HOW FAR DOES "MOST WALKABLE" (alpha=8) DETOUR?')
ratios = []
for a, b in pairs:
    e0, e8, e2 = astar(a, b, 0.0), astar(a, b, 8.0), astar(a, b, 2.0)
    if not (e0 and e8):
        continue
    l0, l8 = length(e0), length(e8)
    ratios.append((l8 / l0, l0, l8, mean_score(e0), mean_score(e8), length(e2) / l0))
ratios.sort(reverse=True)
print('   detour of alpha=8 vs shortest, over %d pairs:' % len(ratios))
print('     median %.2fx   mean %.2fx   worst %.2fx'
      % (sorted(r[0] for r in ratios)[len(ratios)//2],
         sum(r[0] for r in ratios)/len(ratios), ratios[0][0]))
print('     alpha=2 (balanced): median %.2fx  worst %.2fx'
      % (sorted(r[5] for r in ratios)[len(ratios)//2], max(r[5] for r in ratios)))
print('   the five worst detours:')
for r in ratios[:5]:
    print('     %.2fx longer (%4.0f m -> %4.0f m) for walkability %.1f -> %.1f'
          % (r[0], r[1], r[2], r[3], r[4]))

print('\n4. SNAPPING ERROR: clicking mid-street but routing from an ENDPOINT')
lens = sorted(s[F['LEN']] for s in S)
def q(p): return lens[int(p / 100 * (len(lens) - 1))]
print('   segment length: median %.0f m  75th %.0f m  90th %.0f m  99th %.0f m  max %.0f m'
      % (q(50), q(75), q(90), q(99), lens[-1]))
print('   worst-case error is half a segment: up to %.0f m on the median segment,' % (q(50)/2))
print('   but up to %.0f m on the longest 1%%.' % (q(99)/2))
over = sum(1 for L in lens if L > 200)
print('   %d segments (%.1f%%) are longer than 200 m — clicking the middle of one of' % (over, 100*over/N))
print('   these puts the pin up to %.0f m away from where the drawn route begins.' % (max(lens)/2))
