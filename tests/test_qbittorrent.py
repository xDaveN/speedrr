"""Exercise Speedrr's client without a live server or production credentials."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs

from clients.qbittorrent import qBittorrentClient
from helpers.config import ClientConfig


class QbitHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def reply(self, status, body="", cookie=None):
        self.send_response(status)
        if cookie:
            self.send_header("Set-Cookie", cookie + "; Path=/; HttpOnly")
        self.end_headers()
        self.wfile.write(body.encode())

    def dispatch(self, params):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/api/v2/auth/login":
            if params.get("password") != ["test-password"]:
                return self.reply(401 if self.server.modern else 200, "" if self.server.modern else "Fails.")
            return self.reply(204 if self.server.modern else 200,
                              "" if self.server.modern else "Ok.", self.server.cookie)
        public = {
            "/api/v2/app/version": "v5.2.4" if self.server.modern else "v5.1.4",
            "/api/v2/app/webapiVersion": "2.15.1" if self.server.modern else "2.11.4",
        }
        if path in public:
            return self.reply(200, public[path])
        if self.headers.get("Cookie") != self.server.cookie:
            return self.reply(403)
        if path == "/api/v2/torrents/info":
            return self.reply(200, json.dumps([
                {"state": "downloading"}, {"state": "uploading"}, {"state": "stoppedUP"},
            ]))
        if path in {"/api/v2/transfer/setUploadLimit", "/api/v2/transfer/setDownloadLimit"}:
            self.server.limits[path] = int(params["limit"][0])
            return self.reply(204 if self.server.modern else 200)
        return self.reply(404)

    def do_GET(self):
        self.dispatch(parse_qs(self.path.partition("?")[2]))

    def do_POST(self):
        self.dispatch(parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()))


class QbitCompatibility(unittest.TestCase):
    def test_legacy_and_modern_login_cookie_and_speed_limits(self):
        for modern in (False, True):
            with self.subTest(modern=modern):
                server = HTTPServer(("127.0.0.1", 0), QbitHandler)
                server.modern = modern
                server.cookie = f"QBT_SID_{server.server_port}=test-session" if modern else "SID=test-session"
                server.limits = {}
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    cfg = SimpleNamespace(units="Mbit")
                    client_cfg = ClientConfig("qbittorrent", f"http://127.0.0.1:{server.server_port}",
                                              "test-user", "test-password", True)
                    client = qBittorrentClient(cfg, client_cfg)
                    self.assertEqual(client.get_active_torrent_count(), 2)
                    client.set_upload_speed(5)
                    client.set_download_speed(10)
                    self.assertEqual(server.limits, {
                        "/api/v2/transfer/setUploadLimit": 625000,
                        "/api/v2/transfer/setDownloadLimit": 1250000,
                    })
                    bad_cfg = ClientConfig("qbittorrent", client_cfg.url, "test-user", "wrong", True)
                    with self.assertRaisesRegex(Exception, "Failed to login"):
                        qBittorrentClient(cfg, bad_cfg)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


if __name__ == "__main__":
    unittest.main()
