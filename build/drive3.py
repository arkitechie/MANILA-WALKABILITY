"""Round 3: coloured broken lines for the unselected routes, the score-scale
card, the city-wide figures, and the new title."""
import json, subprocess, sys, time, pathlib, base64
import requests, websocket

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
W, H = 1600, 1000

proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
    '--hide-scrollbars', '--remote-debugging-port=9336', '--remote-allow-origins=*',
    f'--window-size={W},{H}', '--user-data-dir=' + str(OUT / 'cp4'), 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ws_url = None
    for _ in range(60):
        try:
            t = [x for x in requests.get('http://127.0.0.1:9336/json', timeout=2).json()
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
    time.sleep(13)

    print('== 4. title ==')
    print('  document.title :', js('document.title'))
    print('  header brand   :', js('document.querySelector(".brand b").innerText'))

    print('\n== 3. city-wide figures ==')
    print('  header stat    :', js('document.getElementById("s-avg").textContent'),
          '/', js('document.querySelector(".stat span").textContent'))
    print('  card text      :')
    for ln in (js('document.getElementById("scorecard").innerText') or '').split('\n'):
        if ln.strip(): print('     ', ln.strip())

    print('\n== 2. band table ==')
    print('  band rows      :', js('document.querySelectorAll("#scorecard table.bands tr").length'))
    print('  chip colours   :', js('Array.from(document.querySelectorAll("#scorecard table.bands td.c i")).map(function(e){return e.style.background})'))

    print('\n== extremes are clickable ==')
    js('document.getElementById("ex-hi").click()')
    time.sleep(2.5)
    print('  active tab     :', js('document.querySelector(".tabs button[aria-selected=true]").innerText'))
    print('  street panel   :', (js('document.getElementById("street-body").innerText.replace(/\\n+/g," | ")') or '')[:170])
    shot('r3_highest.png')

    print('\n== 1. coloured broken lines for the alternatives ==')
    js('document.getElementById("tab-route").click()')
    js('document.getElementById("btn-clear").click()')
    js('document.getElementById("mb-fit").click()')   # back to the whole city
    time.sleep(4)
    click(880, 380); time.sleep(1.2)
    click(1150, 720); time.sleep(5.0)
    print('  A =', js('document.getElementById("a-name").textContent'))
    print('  B =', js('document.getElementById("b-name").textContent'))
    print('  cards:', js('document.getElementById("routes").children.length'))
    print('  route strokes:', js('''(function(){
        var c={}; document.querySelectorAll("#map .leaflet-overlay-pane path").forEach(function(el){
          var s=el.getAttribute("stroke"), d=el.getAttribute("stroke-dasharray");
          if(s && d) c[s+" dash("+d+")"]=(c[s+" dash("+d+")"]||0)+1; });
        return c; })()'''))
    print('  route key    :', (js('document.getElementById("routekey").innerText.replace(/\\n/g," | ")') or ''))
    shot('r3_routes.png')

    print('\n  switching to "Shortest" ...')
    js('document.getElementById("routes").children[2].click()')
    time.sleep(2)
    print('  route key    :', (js('document.getElementById("routekey").innerText.replace(/\\n/g," | ")') or ''))
    print('  dashed now   :', js('''(function(){
        var c={}; document.querySelectorAll("#map .leaflet-overlay-pane path").forEach(function(el){
          var s=el.getAttribute("stroke"), d=el.getAttribute("stroke-dasharray");
          if(s && d) c[s]=(c[s]||0)+1; });
        return c; })()'''))
    shot('r3_routes_alt.png')

    print('\n== model switch keeps the figures in sync ==')
    js('document.getElementById("tab-about").click()')
    js('var s=document.getElementById("f-model"); s.value="gbm"; s.dispatchEvent(new Event("change"))')
    time.sleep(4)
    print('  header avg   :', js('document.getElementById("s-avg").textContent'))
    print('  detail table :', (js('document.getElementById("score-detail").innerText.replace(/\\n+/g," | ")') or '')[:260])
    shot('r3_method.png')
    js('var s=document.getElementById("f-model"); s.value="rule"; s.dispatchEvent(new Event("change"))')
    time.sleep(3)
    print('  back to rule :', js('document.getElementById("s-avg").textContent'))

    print('\n== console errors ==')
    print('  ', errors[:10] if errors else 'none')
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate()
