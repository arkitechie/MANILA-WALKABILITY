"""Wheel-zoom into Ermita/Malate with real input events and confirm the
walkability ramp is legible at street level. Also flips on the hex layer."""
import json, subprocess, sys, time, pathlib, base64
import requests, websocket

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
W, H = 1500, 950

proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
    '--hide-scrollbars', '--remote-debugging-port=9334', '--remote-allow-origins=*',
    f'--window-size={W},{H}', '--user-data-dir=' + str(OUT / 'cp2'), 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ws_url = None
    for _ in range(60):
        try:
            t = [x for x in requests.get('http://127.0.0.1:9334/json', timeout=2).json()
                 if x['type'] == 'page']
            if t: ws_url = t[0]['webSocketDebuggerUrl']; break
        except Exception: pass
        time.sleep(0.5)
    ws = websocket.create_connection(ws_url, timeout=60); mid = [0]; errors = []

    def send(m, **p):
        mid[0] += 1
        ws.send(json.dumps({'id': mid[0], 'method': m, 'params': p}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('method') == 'Runtime.exceptionThrown':
                d = msg['params']['exceptionDetails']
                errors.append(d.get('exception', {}).get('description') or d.get('text', ''))
            elif msg.get('id') == mid[0]:
                return msg.get('result', {})

    def js(e):
        r = send('Runtime.evaluate', expression=e, returnByValue=True, awaitPromise=True)
        if 'exceptionDetails' in r:
            return {'__err': r['exceptionDetails'].get('exception', {}).get('description')}
        return r.get('result', {}).get('value')

    def wheel(x, y, dy, times=1):
        for _ in range(times):
            send('Input.dispatchMouseEvent', type='mouseWheel', x=x, y=y,
                 deltaX=0, deltaY=dy, buttons=0)
            time.sleep(0.55)

    def move(x, y):
        send('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y, buttons=0)
        time.sleep(0.3)

    def shot(n):
        (OUT / n).write_bytes(base64.b64decode(send('Page.captureScreenshot', format='png')['data']))
        print('  shot ->', n)

    send('Page.enable'); send('Runtime.enable')
    send('Page.navigate', url='http://localhost:8765/index.html')
    time.sleep(12)
    print('loaded:', js('document.getElementById("s-seg").textContent'))

    PX, PY = 980, 600            # Ermita / Malate in the fitted view

    AUDIT = '''(function(){
      var cs = document.querySelectorAll(".walk-streets canvas"), tally = {}, painted = 0, total = 0;
      for (var n = 0; n < cs.length; n++) {
        var c = cs[n];
        if (!c.width) continue;
        var d;
        try { d = c.getContext("2d").getImageData(0,0,c.width,c.height).data; } catch(e){ continue; }
        for (var i = 0; i < d.length; i += 4) {
          total++;
          if (d[i+3] > 40) {
            painted++;
            var k = (d[i]>>5)+"-"+(d[i+1]>>5)+"-"+(d[i+2]>>5);
            tally[k] = (tally[k]||0)+1;
          }
        }
      }
      var top = Object.keys(tally).sort(function(a,b){return tally[b]-tally[a];}).slice(0,8)
                  .map(function(k){ var p=k.split("-");
                    return "rgb("+(p[0]*32)+","+(p[1]*32)+","+(p[2]*32)+")x"+tally[k]; });
      return {canvases: cs.length, paintedPx: painted,
              pct: total ? +(100*painted/total).toFixed(2) : 0,
              distinctBuckets: Object.keys(tally).length, top: top};
    })()'''

    for steps, tag in ((1, 'z_mid'), (1, 'z_street')):
        print('wheel-zooming in %d steps -> %s ...' % (steps, tag))
        wheel(PX, PY, -400, times=steps)
        time.sleep(4)
        a = js(AUDIT)
        print('   canvases=%s  painted=%.2f%% of px  distinct colour buckets=%s'
              % (a['canvases'], a['pct'], a['distinctBuckets']))
        print('   dominant:', ', '.join(a['top'][:6]))
        move(PX, PY); time.sleep(0.8)
        print('   hover highlight:', js('document.querySelectorAll(".leaflet-overlay-pane path").length'))
        shot(tag + '.png')

    print('hex layer on ...')
    js('document.getElementById("tab-about").click(); document.getElementById("mb-hex").click()')
    time.sleep(3)
    shot('zoom_hex.png')

    print('absolute colour scale ...')
    js('document.getElementById("mb-hex").click(); document.getElementById("mb-colour").click()')
    time.sleep(3)
    shot('zoom_absolute.png')
    print('  legend:', js('document.getElementById("lg-note").innerText'))
    print('errors:', errors[:6] or 'none')
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate()
