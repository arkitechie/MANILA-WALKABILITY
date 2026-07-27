"""Round 4: the direct route is the default, alternatives are named as such,
and the drawn line must actually start and finish at the pins."""
import json, subprocess, sys, time, pathlib, base64, math
import requests, websocket

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
W, H = 1600, 1000

proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
    '--hide-scrollbars', '--remote-debugging-port=9338', '--remote-allow-origins=*',
    f'--window-size={W},{H}', '--user-data-dir=' + str(OUT / 'cp6'), 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ws_url = None
    for _ in range(60):
        try:
            t = [x for x in requests.get('http://127.0.0.1:9338/json', timeout=2).json()
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
                errors.append('EXCEPTION: ' + (d.get('exception', {}).get('description') or d.get('text', '')))
            elif msg.get('method') == 'Runtime.consoleAPICalled' and msg['params']['type'] in ('error', 'warning'):
                errors.append('console: ' + ' '.join(str(a.get('value', '')) for a in msg['params']['args']))
            elif msg.get('id') == mid[0]:
                return msg.get('result', {})

    def js(e):
        r = send('Runtime.evaluate', expression=e, returnByValue=True, awaitPromise=True)
        if 'exceptionDetails' in r:
            return {'__err': r['exceptionDetails'].get('exception', {}).get('description')}
        return r.get('result', {}).get('value')

    def click(x, y):
        send('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y, buttons=0); time.sleep(0.3)
        send('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y, button='left', buttons=1, clickCount=1)
        send('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y, button='left', buttons=0, clickCount=1)
        time.sleep(0.1)

    def shot(n):
        (OUT / n).write_bytes(base64.b64decode(send('Page.captureScreenshot', format='png')['data']))
        print('  shot ->', n)

    send('Page.enable'); send('Runtime.enable')
    send('Page.navigate', url='http://localhost:8765/index.html')
    time.sleep(14)
    print('segments:', js('document.getElementById("s-seg").textContent'),
          '| city avg:', js('document.getElementById("s-avg").textContent'),
          '| self-test:', js('document.getElementById("test-txt").textContent'))

    # exercise several A/B pairs at the opening zoom
    trials = [((900, 300), (1180, 640)), ((820, 620), (1250, 300)), ((1000, 750), (960, 250))]
    for n, (pa, pb) in enumerate(trials):
        print('\n=== trial %d: %s -> %s ===' % (n + 1, pa, pb))
        js('document.getElementById("btn-clear").click()')
        time.sleep(0.6)
        click(*pa); time.sleep(1.0)
        click(*pb); time.sleep(4.5)
        info = js('''(function(){
          var cards = Array.from(document.getElementById("routes").children).map(function(e){
            return e.innerText.replace(/\\n/g," | "); });
          return {cards:cards,
                  sel: document.querySelector("#routes [aria-pressed=true] .nm") ?
                       document.querySelector("#routes [aria-pressed=true] .nm").innerText : null,
                  a: document.getElementById("a-name").textContent,
                  b: document.getElementById("b-name").textContent};
        })()''')
        if not info['cards']:
            print('  NO ROUTES:', js('document.getElementById("route-status").textContent'))
            continue
        print('  A =', info['a'], '| B =', info['b'])
        print('  selected by default:', info['sel'])
        for c in info['cards']:
            print('   ', c)
        # does the drawn line actually reach the pins?
        gap = js('''(function(){
          function ll(el){ return el; }
          var m = document.querySelectorAll(".marker-ab");
          if (m.length < 2) return null;
          function centre(el){ var r = el.getBoundingClientRect();
            return [r.left + r.width/2, r.top + r.height/2]; }
          var A = centre(m[0]), B = centre(m[1]);
          // gather every endpoint of every drawn route polyline
          var pts = [];
          document.querySelectorAll("#map .leaflet-overlay-pane path").forEach(function(p){
            var d = p.getAttribute("d"); if(!d) return;
            var nums = d.match(/-?\\d+(\\.\\d+)?/g); if(!nums || nums.length < 4) return;
            var box = p.ownerSVGElement.getBoundingClientRect();
            pts.push([+nums[0]+box.left, +nums[1]+box.top]);
            pts.push([+nums[nums.length-2]+box.left, +nums[nums.length-1]+box.top]);
          });
          function near(P){ var best=1e9; pts.forEach(function(q){
            best = Math.min(best, Math.hypot(q[0]-P[0], q[1]-P[1])); }); return best; }
          return {aGapPx: Math.round(near(A)), bGapPx: Math.round(near(B)), endpoints: pts.length};
        })()''')
        print('  pin-to-route gap:', gap, '(px on screen; small = the line meets the pin)')
        shot('r4_trial%d.png' % (n + 1))

    print('\n=== switching to an alternative ===')
    js('document.getElementById("routes").children[1].click()')
    time.sleep(2)
    print('  route key:', (js('document.getElementById("routekey").innerText.replace(/\\n/g," | ")') or ''))
    shot('r4_alt.png')

    print('\n=== console errors ===')
    print('  ', errors[:10] if errors else 'none')
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate()
