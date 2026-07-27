"""Capture the score-scale card: on first load, and scrolled to after routing."""
import json, subprocess, sys, time, pathlib, base64
import requests, websocket

OUT = pathlib.Path(sys.argv[1]); CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
proc = subprocess.Popen([CHROME, '--headless=new', '--disable-gpu', '--no-sandbox',
    '--hide-scrollbars', '--remote-debugging-port=9337', '--remote-allow-origins=*',
    '--window-size=1600,1000', '--user-data-dir=' + str(OUT / 'cp5'), 'about:blank'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    ws_url = None
    for _ in range(60):
        try:
            t = [x for x in requests.get('http://127.0.0.1:9337/json', timeout=2).json() if x['type'] == 'page']
            if t: ws_url = t[0]['webSocketDebuggerUrl']; break
        except Exception: pass
        time.sleep(0.5)
    ws = websocket.create_connection(ws_url, timeout=60); mid = [0]
    def send(m, **p):
        mid[0] += 1
        ws.send(json.dumps({'id': mid[0], 'method': m, 'params': p}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get('id') == mid[0]: return msg.get('result', {})
    def js(e): return send('Runtime.evaluate', expression=e, returnByValue=True).get('result', {}).get('value')
    def shot(n):
        (OUT / n).write_bytes(base64.b64decode(send('Page.captureScreenshot', format='png')['data']))
        print('  shot ->', n)
    send('Page.enable'); send('Runtime.enable')
    send('Page.navigate', url='http://localhost:8765/index.html')
    time.sleep(13)
    print('first load, score card position from top of pane:',
          js('document.getElementById("scorecard").getBoundingClientRect().top'))
    shot('r3_card_load.png')
    js('document.getElementById("pane-route").scrollTop = 99999')
    time.sleep(1)
    shot('r3_card_scrolled.png')
finally:
    try: ws.close()
    except Exception: pass
    proc.terminate()
