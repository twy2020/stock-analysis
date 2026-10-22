import importlib.util
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx

spec = importlib.util.spec_from_file_location('market_relay', Path(__file__).with_name('market-relay.py'))
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.upstream_ok = True
        owner = self

        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200 if owner.upstream_ok else 503)
                self.end_headers()
                self.wfile.write(json.dumps({'ok': owner.upstream_ok, 'db': 'private-path'}).encode())

        self.upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        self.server = relay.create_server(
            f'http://127.0.0.1:{self.upstream.server_port}', 0, 'test-only-token', host='127.0.0.1')
        for server in (self.upstream, self.server):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.client = httpx.Client(base_url=f'http://127.0.0.1:{self.server.server_port}', trust_env=False)

    def tearDown(self):
        self.client.close()
        for server in (self.server, self.upstream):
            server.shutdown()
            server.server_close()

    def test_health_reports_real_upstream_without_exposing_data(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'service': 'stock-market-relay', 'status': 'UP'})
        self.upstream_ok = False
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private-path', response.text)

    def test_market_routes_require_token_and_restrict_paths(self):
        self.assertEqual(self.client.get('/api/db/health').status_code, 401)
        headers = {'Authorization': 'Bearer test-only-token'}
        self.assertEqual(self.client.get('/api/db/health', headers=headers).status_code, 200)
        self.assertEqual(self.client.get('/api/admin', headers=headers).status_code, 404)
        self.assertEqual(self.client.post('/api/db/stocks', headers=headers).status_code, 405)

    def test_service_hub_port_is_reserved(self):
        with self.assertRaisesRegex(ValueError, 'Service Hub'):
            relay.create_server('http://127.0.0.1:12345', 18765, 'test-only-token')


if __name__ == '__main__':
    unittest.main()
