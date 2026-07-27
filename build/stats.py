import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
raw = (ROOT / 'manila.js').read_text(encoding='utf-8')
M = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])
S, names = M['streets'], M['names']
sc = sorted(s[7] for s in S)
def p(q): return sc[int(q / 100 * (len(sc) - 1))]
print('segments %d  nodes %d  hexes %d  area %.2f' %
      (M['meta']['counts']['streets'], M['meta']['counts']['nodes'],
       M['meta']['counts']['hexes'], M['areaKm2']))
st = M['stats']['score']
print('mean %.1f  median %.1f  min %.1f  max %.1f' % (st['mean'], st['median'], st['min'], st['max']))
print('bands: <%.1f | %.1f-%.1f | %.1f-%.1f | %.1f-%.1f | %.1f-%.1f | %.1f+' %
      (p(20), p(20), p(50), p(50), p(80), p(80), p(95), p(95), p(99), p(99)))
ss = M['meta']['sidewalk_sources']
print('sidewalk inferred %d of %d = %.0f%%' %
      (ss['inferred'], len(S), 100 * ss['inferred'] / len(S)))

def extreme(hi):
    best = None
    for i, s in enumerate(S):
        if best is None or (s[7] > S[best][7] if hi else s[7] < S[best][7]):
            best = i
    tie = [i for i, s in enumerate(S) if s[7] == S[best][7]]
    named = [i for i in tie if names[S[i][0]]]
    i = named[0] if named else best
    hw = M['hwCodes'][S[i][1]]
    return S[i][7], (names[S[i][0]] or ('unnamed ' + hw.replace('_', ' ') +
                     (' path' if hw == 'footway' else ' street'))), len(tie)
print('lowest  %.1f  %s  (%d tied)' % extreme(False))
print('highest %.1f  %s  (%d tied)' % extreme(True))
