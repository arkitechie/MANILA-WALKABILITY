"""Drop A in the MIDDLE of a long street, then zoom right in on the pin to see
whether the drawn route actually begins there rather than at a junction."""
import json, subprocess, sys, time, pathlib, base64
import requests, websocket

OUT = pathlib.Path(sys.argv[1]); CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
    '--hide-scrollbars', '--remote-debugging-port=9339', '--remote-allow-origins=*',
    '--window-size=1500,950', '--user-data-dir=' + str(OUT / 'cp7'), 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ws_url = None
    for _ in range(60):
        try:
            t = [x for x in requests.get('http://127.0.0.1:9339/json', timeout=2).json() if x['type'] == 'page']
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
                errors.append(msg['params']['exceptionDetails'].get('text', ''))
            elif msg.get('id') == mid[0]: return msg.get('result', {})
    def js(e):
        r = send('Runtime.evaluate', expression=e, returnByValue=True)
        return r.get('result', {}).get('value')
    def click(x, y):
        send('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y, buttons=0); time.sleep(0.3)
        send('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y, button='left', buttons=1, clickCount=1)
        send('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y, button='left', buttons=0, clickCount=1)
        time.sleep(0.1)
    def wheel(x, y, dy, n=1):
        for _ in range(n):
            send('Input.dispatchMouseEvent', type='mouseWheel', x=x, y=y, deltaX=0, deltaY=dy, buttons=0)
            time.sleep(0.6)
    def shot(n):
        (OUT / n).write_bytes(base64.b64decode(send('Page.captureScreenshot', format='png')['data']))
        print('  shot ->', n)

    send('Page.enable'); send('Runtime.enable')
    send('Page.navigate', url='http://localhost:8765/index.html')
    time.sleep(13)

    # A on Roxas Boulevard-ish long stretch, B far away
    AX, AY = 900, 700
    click(AX, AY); time.sleep(1.0)
    print('A =', js('document.getElementById("a-name").textContent'))
    click(1150, 300); time.sleep(4.5)
    print('B =', js('document.getElementById("b-name").textContent'))
    print('cards:', js('document.getElementById("routes").children.length'))
    shot('pin_wide.png')

    # find the A marker on screen and zoom onto it
    pos = js('''(function(){ var m=document.querySelector(".marker-ab.a");
        if(!m) return null; var r=m.getBoundingClientRect();
        return [Math.round(r.left+r.width/2), Math.round(r.top+r.height/2)]; })()''')
    print('A marker at', pos)
    if pos:
        wheel(pos[0], pos[1], -300, 3)
        time.sleep(3)
        shot('pin_zoom.png')
    print('errors:', errors[:5] or 'none')
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate()
