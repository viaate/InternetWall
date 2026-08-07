#!/usr/bin/env python3
"""
The bridge. Runs on the Pi and does the things a browser cannot.

None of these devices are reachable from a web page, and not because of anything the page
is doing wrong:

  Apple TV   speaks Apple's Companion/MRP protocol over the network, with a pairing
             handshake. There is no web API for it in any browser.
  Samsung    does expose a WebSocket API, but on wss:// with a self-signed certificate.
             Safari refuses that, and unlike a page there is no way to accept a
             certificate exception for a WebSocket. Its plaintext port is then blocked by
             mixed-content rules.
  the PCs    Wake-on-LAN is a raw UDP broadcast to port 9. Browsers have no UDP at all.

So this process holds the connections and exposes a small JSON API over HTTPS, and the
iPad only ever talks to this.

HTTPS is not optional. The wall is served from GitHub Pages over https, and a secure page
cannot call an insecure one. Use mkcert (see README.md) so the certificate is genuinely
trusted by the iPad rather than clicked past, because fetch() offers no way to click past.

    python3 bridge.py --config config.json
"""

import argparse
import asyncio
import json
import logging
import pathlib
import socket
import ssl
import struct
import sys

from aiohttp import web

log = logging.getLogger("bridge")

HERE = pathlib.Path(__file__).resolve().parent


# --------------------------------------------------------------------------- wake on lan

def wake(mac: str, broadcast: str = "255.255.255.255") -> None:
    """Send a magic packet: six 0xFF bytes then the MAC sixteen times.

    Written out rather than pulled from a library because it is nine lines and the Pi Zero
    is ARMv6, where every extra dependency is another wheel that may have to compile.
    """
    clean = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(clean) != 12:
        raise ValueError(f"not a MAC address: {mac}")
    packet = b"\xff" * 6 + bytes.fromhex(clean) * 16

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        # Port 9 is the usual one, but plenty of NICs listen on 7 instead, and sending both
        # costs nothing next to the cost of a button that silently does nothing.
        for port in (9, 7):
            s.sendto(packet, (broadcast, port))
    finally:
        s.close()


# --------------------------------------------------------------------------- apple tv

class AppleTV:
    """Wraps pyatv, holding one connection open.

    Reconnecting per keypress would be unusable: the scan and pair handshake take seconds
    on an ARMv6 Pi, so a D-pad press would land whenever it felt like it. The connection is
    opened once and re-established only when it drops.
    """

    KEYS = {
        "up": "up", "down": "down", "left": "left", "right": "right",
        "select": "select", "menu": "menu", "home": "home",
        "play_pause": "play_pause", "volume_up": "volume_up", "volume_down": "volume_down",
    }

    def __init__(self, cfg):
        self.address = cfg.get("address")
        self.credentials = cfg.get("credentials", {})
        self.atv = None
        self._lock = asyncio.Lock()

    @property
    def configured(self):
        return bool(self.address and self.credentials)

    async def _connect(self):
        import pyatv                      # imported late: it is slow to load on ARMv6
        loop = asyncio.get_running_loop()
        confs = await pyatv.scan(loop, hosts=[self.address], timeout=5)
        if not confs:
            raise RuntimeError(f"no Apple TV answered at {self.address}")
        conf = confs[0]
        for proto_name, cred in self.credentials.items():
            proto = getattr(pyatv.const.Protocol, proto_name, None)
            if proto is None:
                log.warning("unknown protocol in credentials: %s", proto_name)
                continue
            conf.set_credentials(proto, cred)
        self.atv = await pyatv.connect(conf, loop)
        log.info("Apple TV connected at %s", self.address)

    async def press(self, action):
        key = self.KEYS.get(action)
        if key is None:
            raise ValueError(f"unknown Apple TV key: {action}")
        async with self._lock:
            for attempt in (1, 2):
                try:
                    if self.atv is None:
                        await self._connect()
                    await getattr(self.atv.remote_control, key)()
                    return
                except Exception as exc:
                    # One silent retry. A connection that has gone stale looks exactly like
                    # a real failure on the first press and works fine on the second.
                    log.warning("Apple TV %s failed (attempt %d): %s", action, attempt, exc)
                    if self.atv is not None:
                        try:
                            self.atv.close()
                        except Exception:
                            pass
                        self.atv = None
                    if attempt == 2:
                        raise


# --------------------------------------------------------------------------- samsung

class SamsungTV:
    """Wraps samsungtvws.

    The first connection makes the TV show an allow/deny prompt. Accept it, and the token
    it returns is written back to the config so it never asks again. Without persisting
    that token every restart of this service prompts on the TV, which on a wall display
    means the TV asking permission at three in the morning.
    """

    KEYS = {
        "power": "KEY_POWER", "mute": "KEY_MUTE",
        "volume_up": "KEY_VOLUP", "volume_down": "KEY_VOLDOWN",
        "source": "KEY_SOURCE", "home": "KEY_HOME",
        "hdmi1": "KEY_HDMI1", "hdmi2": "KEY_HDMI2", "hdmi3": "KEY_HDMI3",
        "up": "KEY_UP", "down": "KEY_DOWN", "left": "KEY_LEFT", "right": "KEY_RIGHT",
        "select": "KEY_ENTER", "back": "KEY_RETURN",
    }

    def __init__(self, cfg, on_token):
        self.address = cfg.get("address")
        self.token = cfg.get("token") or None
        self.on_token = on_token
        self._tv = None

    @property
    def configured(self):
        return bool(self.address)

    def _open(self):
        from samsungtvws import SamsungTVWS
        self._tv = SamsungTVWS(host=self.address, port=8002, token=self.token,
                               name="The Wall", timeout=6)
        return self._tv

    async def press(self, action):
        key = self.KEYS.get(action)
        if key is None:
            raise ValueError(f"unknown Samsung key: {action}")

        def blocking():
            tv = self._tv or self._open()
            tv.send_key(key)
            new = getattr(tv, "token", None)
            if new and new != self.token:
                self.token = new
                self.on_token(new)
            return True

        # samsungtvws is synchronous, so it goes to a thread rather than stalling the loop
        # and making every other button feel broken while one is in flight.
        try:
            await asyncio.to_thread(blocking)
        except Exception:
            self._tv = None
            raise


# --------------------------------------------------------------------------- the service

class Bridge:
    def __init__(self, cfg_path):
        self.cfg_path = pathlib.Path(cfg_path)
        self.cfg = json.loads(self.cfg_path.read_text())
        self.appletv = AppleTV(self.cfg.get("appletv", {}))
        self.tv = SamsungTV(self.cfg.get("tv", {}), self._save_token)
        self.pcs = self.cfg.get("pcs", {})

    def _save_token(self, token):
        self.cfg.setdefault("tv", {})["token"] = token
        self.cfg_path.write_text(json.dumps(self.cfg, indent=2) + "\n")
        log.info("saved the Samsung pairing token; the TV will not ask again")

    def devices(self):
        out = []
        if self.appletv.configured:
            out.append("Apple TV")
        if self.tv.configured:
            out.append("Samsung TV")
        if self.pcs:
            out.append(f"{len(self.pcs)} PC" + ("s" if len(self.pcs) != 1 else ""))
        return out

    async def run(self, device, action):
        if device == "appletv":
            await self.appletv.press(action)
        elif device == "tv":
            await self.tv.press(action)
        elif device == "inputs":
            await self.tv.press(action)                 # hdmi1/2/3 are Samsung keys
        elif device == "pcs":
            name = action.replace("wake_", "")
            pc = self.pcs.get(name)
            if not pc:
                raise ValueError(f"no PC called {name}")
            wake(pc["mac"], pc.get("broadcast", "255.255.255.255"))
            # Switching the TV to it as well is the thing you always wanted next anyway.
            if pc.get("hdmi") and self.tv.configured:
                await asyncio.sleep(0.4)
                try:
                    await self.tv.press(pc["hdmi"])
                except Exception as exc:
                    log.warning("woke %s but could not switch the TV: %s", name, exc)
        else:
            raise ValueError(f"unknown device: {device}")


def make_app(bridge, origins):
    routes = web.RouteTableDef()

    def cors(resp, request):
        origin = request.headers.get("Origin")
        # Echoed rather than "*", because the wall is the only thing meant to drive this and
        # "*" would let any page the iPad ever loads press buttons in the room.
        if origin and (origin in origins or "*" in origins):
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return resp

    @routes.get("/health")
    async def health(request):
        return cors(web.json_response({"ok": True, "devices": bridge.devices()}), request)

    @routes.options("/cmd")
    async def preflight(request):
        return cors(web.Response(status=204), request)

    @routes.post("/cmd")
    async def cmd(request):
        try:
            body = await request.json()
            await bridge.run(body["device"], body["action"])
            return cors(web.json_response({"ok": True}), request)
        except Exception as exc:
            log.warning("command failed: %s", exc)
            return cors(web.json_response({"ok": False, "error": str(exc)}, status=502),
                        request)

    app = web.Application()
    app.add_routes(routes)
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(HERE / "config.json"))
    ap.add_argument("--port", type=int, default=8443)
    ap.add_argument("--cert", default=str(HERE / "cert.pem"))
    ap.add_argument("--key", default=str(HERE / "key.pem"))
    ap.add_argument("--http", action="store_true",
                    help="plain http, for testing on the Pi only; the iPad cannot use it")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not pathlib.Path(a.config).exists():
        sys.exit(f"no config at {a.config}. Copy config.example.json and fill it in.")

    bridge = Bridge(a.config)
    origins = set(bridge.cfg.get("allow_origins", []))
    app = make_app(bridge, origins)
    log.info("devices configured: %s", ", ".join(bridge.devices()) or "none")

    ctx = None
    if not a.http:
        if not (pathlib.Path(a.cert).exists() and pathlib.Path(a.key).exists()):
            sys.exit(f"no certificate at {a.cert}. See README.md, or pass --http to test "
                     f"locally.")
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(a.cert, a.key)

    web.run_app(app, port=a.port, ssl_context=ctx, print=None)


if __name__ == "__main__":
    main()
