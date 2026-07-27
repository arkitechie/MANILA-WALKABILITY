"""Drive the app in headless Chrome over the DevTools protocol: real clicks,
real console capture, real screenshots. Usage: python drive.py [outdir]"""
import json, subprocess, sys, time, pathlib, base64
import requests, websocket

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else '.')
OUT.mkdir(parents=True, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
URL = 'http://localhost:8765/index.html'
W, H = 1600, 1000

proc = subprocess.Popen([
    CHROME, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--remote-debugging-port=9333', '--remote-allow-origins=*',
    f'--window-size={W},{H}', '--user-data-dir=' + str(OUT / 'chromeprofile'),
    'about:blank'
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

try:
    ws_url = None
    for _ in range(60):
        try:
            tabs = requests.get('http://127.0.0.1:9333/json', timeout=2).json()
            pages = [t for t in tabs if t['type'] == 'page']
            if pages:
                ws_url = pages[0]['webSocketDebuggerUrl']; break
        except Exception:
            pass
        time.sleep(0.5)
    if not ws_url:
        raise SystemExit('could not reach Chrome DevTools')

    ws = websocket.create_connection(ws_url, timeout=60)
    mid = [0]
    logs, errors = [], []

    def send(method, **params):
        mid[0] += 1
        ws.send(json.dumps({'id': mid[0], 'method': method, 'params': params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('method') == 'Runtime.consoleAPICalled':
                a = msg['params']
                txt = ' '.join(str(x.get('value', x.get('description', ''))) for x in a['args'])
                logs.append((a['type'], txt))
                if a['type'] in ('error', 'warning'):
                    errors.append(f"console.{a['type']}: {txt}")
            elif msg.get('method') == 'Runtime.exceptionThrown':
                d = msg['params']['exceptionDetails']
                errors.append('EXCEPTION: ' + (d.get('exception', {}).get('description') or d.get('text', '')))
            elif msg.get('id') == mid[0]:
                if 'error' in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get('result', {})

    def pump(seconds):
        end = time.time() + seconds
        ws.settimeout(0.4)
        while time.time() < end:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                continue
            if msg.get('method') == 'Runtime.consoleAPICalled':
                a = msg['params']
                txt = ' '.join(str(x.get('value', x.get('description', ''))) for x in a['args'])
                logs.append((a['type'], txt))
                if a['type'] in ('error', 'warning'):
                    errors.append(f"console.{a['type']}: {txt}")
            elif msg.get('method') == 'Runtime.exceptionThrown':
                d = msg['params']['exceptionDetails']
                errors.append('EXCEPTION: ' + (d.get('exception', {}).get('description') or d.get('text', '')))
        ws.settimeout(60)

    def js(expr):
        r = send('Runtime.evaluate', expression=expr, returnByValue=True, awaitPromise=True)
        if 'exceptionDetails' in r:
            return {'__error': r['exceptionDetails'].get('exception', {}).get('description')}
        return r.get('result', {}).get('value')

    def click(x, y, count=1):
        send('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y, buttons=0)
        time.sleep(0.15)
        for c in range(1, count + 1):
            send('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y,
                 button='left', buttons=1, clickCount=c)
            send('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y,
                 button='left', buttons=0, clickCount=c)
            time.sleep(0.05)

    def shot(name):
        r = send('Page.captureScreenshot', format='png')
        (OUT / name).write_bytes(base64.b64decode(r['data']))
        print('  shot ->', name)

    send('Page.enable'); send('Runtime.enable'); send('Log.enable')
    send('Page.navigate', url=URL)
    print('loading ...')
    pump(14)

    ready = js('!!(window.MANILA && window.MODEL_GBM && document.getElementById("s-seg").textContent!=="\\u2014")')
    print('data + model loaded:', ready)
    print('segments chip     :', js('document.getElementById("s-seg").textContent'))
    print('self-test chip    :', js('document.getElementById("test-txt").textContent'))
    print('map zoom          :', js('document.querySelector(".leaflet-container") ? "map ok" : "NO MAP"'))
    print('street canvases   :', js('document.querySelectorAll(".walk-streets canvas").length'))

    # ---- click a street: does the Street panel fill in? ----
    print('\nclick 1 (sets A, selects a street) ...')
    click(960, 430)
    pump(2.5)
    print('  A =', js('document.getElementById("a-name").textContent'))
    print('  A h3 =', js('document.getElementById("a-h3").textContent'))

    print('click 2 (sets B) ...')
    click(1140, 700)
    pump(4.0)
    print('  B =', js('document.getElementById("b-name").textContent'))
    print('  routes rendered:', js('document.getElementById("routes").children.length'))
    print('  route status   :', js('var e=document.getElementById("route-status"); e.hidden?"(hidden)":e.textContent.trim()'))
    print('  route cards    :', js('Array.from(document.getElementById("routes").children).map(function(e){return e.innerText.replace(/\\n/g," | ")})'))
    print('  profile bars   :', js('document.querySelectorAll("#tape rect").length'))
    shot('drive_route.png')

    # ---- the Street tab ----
    print('\nStreet tab ...')
    js('document.getElementById("tab-street").click()')
    pump(1.0)
    print('  panel:', js('var e=document.getElementById("street-body"); e.hidden?"HIDDEN":e.innerText.replace(/\\n+/g," | ").slice(0,300)'))
    shot('drive_street.png')

    # ---- double-click = whole named street ----
    print('\ndouble-click for the whole street ...')
    js('document.getElementById("tab-street").click()')
    click(960, 430, count=2)
    pump(2.5)
    print('  panel:', js('document.getElementById("street-body").innerText.replace(/\\n+/g," | ").slice(0,240)'))

    # ---- Predict tab ----
    print('\nPredict tab ...')
    js('document.getElementById("tab-model").click()')
    pump(1.0)
    print('  prediction:', js('document.getElementById("pred-num").textContent'))
    print('  compare   :', js('document.getElementById("compare").innerText.replace(/\\n+/g," | ")'))

    # ---- switch to the ported GBM ----
    print('\nswitching model to the ported GBM ...')
    js('document.getElementById("tab-about").click()')
    js('var s=document.getElementById("f-model"); s.value="gbm"; s.dispatchEvent(new Event("change"))')
    pump(4.0)
    print('  chip:', js('document.getElementById("model-txt").textContent'))
    print('  legend:', js('document.getElementById("lg-note").innerText'))
    js('document.getElementById("tab-route").click()')
    pump(2.0)
    shot('drive_gbm.png')

    # ---- hexes on ----
    print('\nH3 hex layer ...')
    js('document.getElementById("tab-about").click(); document.getElementById("mb-hex").click()')
    pump(2.5)
    print('  hex polygons drawn:', js('document.querySelectorAll("path").length'))
    js('document.getElementById("f-model").value="rule"; document.getElementById("f-model").dispatchEvent(new Event("change"))')
    pump(2.5)
    shot('drive_hex.png')

    print('\n=== console errors (%d) ===' % len(errors))
    for e in errors[:25]:
        print('  ', e[:300])
    if not errors:
        print('   none')

finally:
    try: ws.close()
    except Exception: pass
    proc.terminate()
