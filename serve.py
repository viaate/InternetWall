#!/usr/bin/env python3
"""Serve the wall on this machine so the iPad can open it over wifi.

    python3 serve.py

Prints the address to type into the iPad. Threaded, because a single-threaded server
blocks on a video byte-range request and starves every other file, which looks exactly
like the app failing to load.

Note this is plain http, so iOS will not register the service worker and the app will
not work with this machine switched off. That is fine for trying it out. For the real
install put it on GitHub Pages, which is https; see the README.
"""
import http.server
import socket
import socketserver
import pathlib

PORT = 8000
ROOT = pathlib.Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, *a):
        pass            # the console is more useful quiet


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))     # nothing is sent; this just picks the route
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


with socketserver.ThreadingTCPServer(("", PORT), Handler) as httpd:
    httpd.daemon_threads = True
    print(f"\n  On this machine:  http://localhost:{PORT}/")
    print(f"  On the iPad:      http://{lan_ip()}:{PORT}/")
    print("\n  Ctrl-C to stop.\n")
    httpd.serve_forever()
