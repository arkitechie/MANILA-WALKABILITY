"""Verify the second round of UI changes with real input events:
  1. overlay off by default, street names unobstructed, button brings it back
  2. coral -> purple gradient painted along the selected route
  3. hover tooltip carries street name + score
  4. opens on the city core, close enough to read labels
"""
import json, subprocess, sys, time, pathlib, base64
import requests, websocket

OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
W, H = 1600, 1000

proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
    '--hide-scrollbars', '--remote-debugging-port=9335', '--remote-allow-origins=*',
    f'--window-size={W},{H}', '--user-data-dir=' + str(OUT / 'cp3'), 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ws_url = None
    for _ in range(60):
        try:
            t = [x for x in requests.get('http://127.0.0.1:9335/json', timeout=2).json()
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

    def move(x, y):
        send('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y, buttons=0)
        time.sleep(0.35)

    def click(x, y, count=1):
        move(x, y)
        for c in range(1, count + 1):
            send('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y,
                 button='left', buttons=1, clickCount=c)
            send('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y,
                 button='left', buttons=0, clickCount=c)
            time.sleep(0.05)

    def shot(n):
        (OUT / n).write_bytes(base64.b64decode(send('Page.captureScreenshot', format='png')['data']))
        print('  shot ->', n)

    send('Page.enable'); send('Runtime.enable')
    send('Page.navigate', url='http://localhost:8765/index.html')
    time.sleep(13)

    print('== 4. opening view ==')
    print('  segments        :', js('document.getElementById("s-seg").textContent'))
    print('  self-test       :', js('document.getElementById("test-txt").textContent'))
    print('  walkability btn :', js('document.getElementById("mb-walk").textContent'))
    print('  overlay canvases:', js('document.querySelectorAll(".walk-streets canvas").length'),
          '(expect 0 while off)')
    print('  basemap labels visible:',
          js('document.querySelectorAll(".basemap-bw img").length > 0'))
    shot('r2_open.png')

    print('\n== 3. hover tooltip ==')
    hits = []
    for (x, y) in ((950, 430), (1050, 560), (860, 640), (1180, 470)):
        move(x, y)
        time.sleep(0.4)
        t = js('var e=document.getElementById("hovertip"); e.hidden?null:e.innerText.replace(/\\n/g," ")')
        if t: hits.append(((x, y), t))
    for p, t in hits:
        print('  at', p, '->', t)
    if not hits:
        print('  !! tooltip never appeared')
    shot('r2_hover.png')

    print('\n== 1 + 2. click anywhere -> A, B -> gradient route ==')
    click(950, 430); time.sleep(1.2)
    print('  A =', js('document.getElementById("a-name").textContent'))
    click(1120, 700); time.sleep(4.5)
    print('  B =', js('document.getElementById("b-name").textContent'))
    print('  route cards:', js('document.getElementById("routes").children.length'))
    seg = js('''(function(){
        var p=document.querySelectorAll("#map .leaflet-overlay-pane path");
        var cols={}, n=0;
        p.forEach(function(el){ var s=el.getAttribute("stroke"); if(!s) return;
          n++; cols[s]=(cols[s]||0)+1; });
        var keys=Object.keys(cols);
        return {paths:n, distinctStrokes:keys.length,
                sample:keys.slice(0,10), ghost:cols["#9A907C"]||0};
      })()''')
    print('  route strokes  :', seg)
    print('  gradient colours on the selected route:', seg['distinctStrokes'], 'distinct')
    shot('r2_route.png')

    print('\n== switching to another alternative ==')
    js('document.getElementById("routes").children[2].click()')
    time.sleep(2)
    print('  swatch classes:', js('Array.from(document.querySelectorAll("#routes .swatch")).map(function(e){return e.className})'))
    shot('r2_route_alt.png')

    print('\n== 1. walkability button turns the overlay back on ==')
    js('document.getElementById("mb-walk").click()')
    time.sleep(4)
    print('  button   :', js('document.getElementById("mb-walk").textContent'))
    print('  canvases :', js('document.querySelectorAll(".walk-streets canvas").length'))
    a = js('''(function(){
        var cs=document.querySelectorAll(".walk-streets canvas"), t={}, painted=0;
        for(var n=0;n<cs.length;n++){ var c=cs[n]; if(!c.width) continue; var d;
          try{ d=c.getContext("2d").getImageData(0,0,c.width,c.height).data; }catch(e){ continue; }
          for(var i=0;i<d.length;i+=4){ if(d[i+3]>40){ painted++;
            t[(d[i]>>5)+"-"+(d[i+1]>>5)+"-"+(d[i+2]>>5)]=1; } } }
        return {painted:painted, buckets:Object.keys(t).length};
      })()''')
    print('  painted px:', a['painted'], ' distinct colour buckets:', a['buckets'])
    shot('r2_overlay_on.png')

    print('\n== console errors ==')
    print('  ', errors[:10] if errors else 'none')
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate()
