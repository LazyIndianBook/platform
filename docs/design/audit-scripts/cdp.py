"""Tiny Chrome DevTools Protocol client (websocket-client): one headless Chrome, one fresh tab per capture."""
import base64, json, os, subprocess, time, urllib.request
import websocket

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class Chrome:
    def __init__(self, profile, port=9333):
        self.port = port
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
             "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check", "--disable-gpu",
             "--hide-scrollbars", "--force-color-profile=srgb", "--disable-background-networking",
             "--disable-component-update", "--mute-audio", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1).read()
                break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Chrome did not start")

    def version(self):
        return json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version"))["Browser"]

    def new_tab(self):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/new?about:blank", method="PUT")
        info = json.load(urllib.request.urlopen(req))
        return Tab(self, info)

    def quit(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except Exception:
            self.proc.kill()


class Tab:
    def __init__(self, chrome, info):
        self.chrome, self.id = chrome, info["id"]
        self.ws = websocket.create_connection(info["webSocketDebuggerUrl"], suppress_origin=True, timeout=60)
        self.n = 0
        self.events = []

    def call(self, method, **params):
        self.n += 1
        mid = self.n
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            if "method" in msg:
                self.events.append(msg)

    def pump(self, seconds):
        """Read events for `seconds`."""
        end = time.time() + seconds
        self.ws.settimeout(0.2)
        while time.time() < end:
            try:
                msg = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            if "method" in msg:
                self.events.append(msg)
        self.ws.settimeout(60)

    def wait_for(self, name, timeout=30):
        end = time.time() + timeout
        self.ws.settimeout(0.5)
        try:
            while time.time() < end:
                if any(e["method"] == name for e in self.events):
                    return True
                try:
                    msg = json.loads(self.ws.recv())
                except websocket.WebSocketTimeoutException:
                    continue
                if "method" in msg:
                    self.events.append(msg)
            return False
        finally:
            self.ws.settimeout(60)

    def js(self, expression, await_promise=True):
        r = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=await_promise)
        if "exceptionDetails" in r:
            raise RuntimeError(json.dumps(r["exceptionDetails"])[:300])
        return r["result"].get("value")

    def close(self):
        try:
            self.ws.close()
        finally:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.chrome.port}/json/close/{self.id}", timeout=5).read()
            except Exception:
                pass


def viewport(tab, width, height, dpr=1, mobile=False):
    tab.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=dpr, mobile=mobile,
             screenWidth=width, screenHeight=height)
    if mobile:
        tab.call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
        tab.call("Emulation.setEmitTouchEventsForMouse", enabled=True, configuration="mobile")


def load(tab, url, settle=1.5):
    """Navigate, wait for the load event and the fonts, then let entry animations finish."""
    tab.events.clear()
    tab.call("Page.enable"); tab.call("Network.enable"); tab.call("Runtime.enable"); tab.call("Log.enable")
    tab.call("Network.setCacheDisabled", cacheDisabled=True)
    tab.call("Network.setBypassServiceWorker", bypass=True)  # the site's worker serves cached static files first: a stale stylesheet
    tab.call("Page.navigate", url=url)
    ok = tab.wait_for("Page.loadEventFired", 40)
    try:
        tab.js("document.fonts.ready.then(() => true)")
    except Exception:
        pass
    tab.pump(settle)
    return ok


def screenshot(tab, path, quality=80, full=False):
    params = dict(format="jpeg", quality=quality, captureBeyondViewport=full)
    if full:
        h = tab.js("Math.max(document.documentElement.scrollHeight, document.body.scrollHeight)")
        w = tab.js("document.documentElement.clientWidth")
        params["clip"] = {"x": 0, "y": 0, "width": w, "height": min(h, 16000), "scale": 1}
    data = tab.call("Page.captureScreenshot", **params)["data"]
    with open(path, "wb") as f:
        f.write(base64.b64decode(data))
    return os.path.getsize(path)


def network_summary(tab):
    """Requests of the page as the browser made them: url, type, status, body bytes (decoded), wire bytes."""
    reqs = {}
    for e in tab.events:
        m, p = e["method"], e["params"]
        if m == "Network.requestWillBeSent":
            reqs.setdefault(p["requestId"], {"url": p["request"]["url"], "type": p.get("type"), "body": 0, "wire": 0,
                                              "status": None, "mime": None})
        elif m == "Network.responseReceived" and p["requestId"] in reqs:
            r = reqs[p["requestId"]]
            r["status"], r["mime"] = p["response"]["status"], p["response"].get("mimeType")
            r["type"] = p.get("type", r["type"])
        elif m == "Network.dataReceived" and p["requestId"] in reqs:
            reqs[p["requestId"]]["body"] += p["dataLength"]
        elif m == "Network.loadingFinished" and p["requestId"] in reqs:
            reqs[p["requestId"]]["wire"] = p["encodedDataLength"]
    return list(reqs.values())


def console_issues(tab):
    out = []
    for e in tab.events:
        m, p = e["method"], e["params"]
        if m == "Log.entryAdded" and p["entry"]["level"] in ("warning", "error"):
            out.append(f"{p['entry']['source']}/{p['entry']['level']}: {p['entry']['text'][:300]}")
        elif m == "Runtime.consoleAPICalled" and p["type"] in ("error", "warning"):
            out.append("console." + p["type"] + ": " + " ".join(str(a.get("value", a.get("description", ""))) for a in p["args"])[:300])
        elif m == "Runtime.exceptionThrown":
            out.append("exception: " + p["exceptionDetails"].get("text", "") + " " + str(p["exceptionDetails"].get("exception", {}).get("description", ""))[:300])
    return out
