"""Optional authenticated host relay when Docker routes overlap the market LAN."""
import argparse
import hmac
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import httpx


def create_server(upstream, port, token, host='0.0.0.0'):
    if port == 18765:
        raise ValueError('Port 18765 is reserved for Service Hub')
    if not token:
        raise ValueError('Configure the stock engine token before starting')
    upstream = upstream.rstrip('/')
    parsed = urlsplit(upstream)
    if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.path or parsed.query
            or parsed.fragment or parsed.username or parsed.password):
        raise ValueError('Upstream must be a fixed HTTP origin')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def dispatch(self):
            if self.command == 'GET' and self.path == '/health':
                ready = False
                try:
                    with httpx.stream('GET', upstream+'/api/db/health', timeout=2,
                                      trust_env=False, follow_redirects=False) as response:
                        data = bytearray()
                        for chunk in response.iter_bytes():
                            data.extend(chunk)
                            if len(data) > 16*1024:
                                raise ValueError('Health response too large')
                        ready = response.status_code == 200 and json.loads(data).get('ok') is True
                except (ValueError, AttributeError, httpx.HTTPError):
                    pass
                body = json.dumps({'service':'stock-market-relay', 'status':'UP' if ready else 'DOWN'}).encode()
                self.send_response(200 if ready else 503)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if not hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token):
                self.send_error(401); return
            path = urlsplit(self.path)
            if not re.fullmatch(r'/api/db/(?:health|stocks|snapshot|rank|dates|sql|bars/\d{6})', path.path):
                self.send_error(404); return
            if self.command == 'POST' and path.path != '/api/db/sql':
                self.send_error(405); return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 <= length <= 128*1024:
                    self.send_error(413); return
                body = self.rfile.read(length) if length else None
                with httpx.stream(self.command, upstream+path.path, params=path.query,
                    content=body, headers={'Content-Type':'application/json'}, timeout=25,
                    trust_env=False, follow_redirects=False) as response:
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        data.extend(chunk)
                        if len(data) > 16*1024*1024: raise ValueError('Response too large')
                    self.send_response(response.status_code)
                    self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(data)))
                    self.end_headers(); self.wfile.write(data)
            except (ValueError, httpx.HTTPError):
                self.send_error(502, 'Market unavailable')

        do_GET = dispatch
        do_POST = dispatch

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upstream', default='http://192.168.3.5:8765')
    parser.add_argument('--port', type=int, default=18766)
    args = parser.parse_args()
    token = (Path(__file__).resolve().parents[1]/'.stock-private/engine.token').read_text('utf-8-sig').strip()
    with create_server(args.upstream, args.port, token) as server:
        print(f'Stock market relay listening on port {args.port}; upstream {args.upstream}', flush=True)
        print(f'Readiness: http://127.0.0.1:{args.port}/health; market routes require authentication', flush=True)
        server.serve_forever()


if __name__ == '__main__':
    main()
