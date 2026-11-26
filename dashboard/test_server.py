"""대시보드 정적 서버 테스트.  실행 (dashboard/ 폴더에서): python -m unittest -v test_server.py

화면·데이터 로직은 node 테스트 (tests/*.test.mjs). 여기서는 서버가
  - 데이터 소스·키를 올바르게 고르고, secret 키를 거부하는지
  - 화면·스크립트만 내주고 다른 파일은 막는지
를 확인한다.
"""
import base64
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

import server

ANON = "sb_publishable_testkey"
URL = "https://example.supabase.co"


def jwt(role):
    part = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{part({'alg': 'HS256'})}.{part({'role': role})}.sig"


class ConfigTest(unittest.TestCase):
    def test_mock_when_no_keys(self):
        self.assertEqual(server.load_config({}), {"dataSource": "mock"})

    def test_supabase_when_keys(self):
        cfg = server.load_config({"SUPABASE_URL": URL + "/", "SUPABASE_ANON_KEY": ANON})
        self.assertEqual(cfg, {"dataSource": "supabase", "supabaseUrl": URL, "supabaseAnonKey": ANON})

    def test_explicit_mock_ignores_keys(self):
        cfg = server.load_config({"SUPABASE_URL": URL, "SUPABASE_ANON_KEY": ANON, "DASHBOARD_DATA_SOURCE": "mock"})
        self.assertEqual(cfg, {"dataSource": "mock"})

    def test_rejects_secret_keys(self):
        for key in ("sb_secret_abc", jwt("service_role")):
            with self.assertRaises(server.ConfigError):
                server.load_config({"SUPABASE_URL": URL, "SUPABASE_ANON_KEY": key})
        server.load_config({"SUPABASE_URL": URL, "SUPABASE_ANON_KEY": jwt("anon")})   # 옛 anon JWT는 허용

    def test_never_reads_service_role_key(self):
        cfg = server.load_config({"SUPABASE_URL": URL, "SUPABASE_ANON_KEY": ANON, "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_x"})
        self.assertNotIn("sb_secret_x", json.dumps(cfg))

    def test_invalid_values(self):
        with self.assertRaises(server.ConfigError):
            server.load_config({"DASHBOARD_DATA_SOURCE": "sqlite"})
        with self.assertRaises(server.ConfigError):
            server.load_config({"DASHBOARD_DATA_SOURCE": "supabase"})
        with self.assertRaises(server.ConfigError):
            server.load_config({"SUPABASE_URL": "http://evil.example", "SUPABASE_ANON_KEY": ANON})
        server.load_config({"SUPABASE_URL": "http://127.0.0.1:54321", "SUPABASE_ANON_KEY": ANON})   # 로컬 Supabase

    def test_env_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("# 주석\nSUPABASE_URL=\"https://x.supabase.co\"\n\nSUPABASE_ANON_KEY='k'\nBROKEN\n", encoding="utf-8")
            self.assertEqual(server.read_env_file(p), {"SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "k"})
        self.assertEqual(server.read_env_file(Path(d) / "없음"), {})

    def test_csp_allows_only_supabase_and_pinned_cdn(self):
        c = server.csp({"dataSource": "supabase", "supabaseUrl": URL})
        self.assertIn(f"connect-src 'self' {URL} wss://example.supabase.co", c)
        self.assertIn("frame-ancestors 'none'", c)
        self.assertIn("connect-src 'self';", server.csp({"dataSource": "mock"}))


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = server.make_server("127.0.0.1", 0, {"dataSource": "supabase", "supabaseUrl": URL, "supabaseAnonKey": ANON})
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def get(self, path, method="GET"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        c.request(method, path)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r, body

    def test_pages(self):
        for path in ("/", "/settings", "/report", "/login"):
            r, body = self.get(path)
            self.assertEqual(r.status, 200, path)
            self.assertIn("text/html", r.getheader("Content-Type"))
            self.assertIn(b'<script src="/config.js"></script>', body)
            self.assertEqual(r.getheader("Cache-Control"), "no-store")
            self.assertEqual(r.getheader("X-Content-Type-Options"), "nosniff")

    def test_config_js(self):
        r, body = self.get("/config.js")
        self.assertEqual(r.status, 200)
        text = body.decode()
        self.assertTrue(text.startswith("window.PD_CONFIG = "))
        cfg = json.loads(text[len("window.PD_CONFIG = "):].rstrip(";\n"))
        self.assertEqual(cfg["supabaseAnonKey"], ANON)

    def test_scripts(self):
        for path in ("/js/model.js", "/js/store.js", "/js/store-supabase.js", "/js/store-mock.js", "/demo-data.js"):
            r, _ = self.get(path)
            self.assertEqual(r.status, 200, path)
            self.assertIn("javascript", r.getheader("Content-Type"))

    def test_blocks_other_files(self):
        for path in ("/server.py", "/../server.py", "/%2e%2e/server.py", "/js/../../test_server.py",
                     "/index.html", "/nope.js", "/..%5cserver.py"):
            r, _ = self.get(path)
            self.assertEqual(r.status, 404, path)

    def test_read_only(self):
        for m in ("POST", "PUT", "DELETE"):
            r, _ = self.get("/", m)
            self.assertEqual(r.status, 405)

    def test_head(self):
        r, body = self.get("/", "HEAD")
        self.assertEqual(r.status, 200)
        self.assertEqual(body, b"")


class NoSecretsInStaticTest(unittest.TestCase):
    def test_no_service_role_usage_in_frontend(self):
        for f in (server.STATIC).rglob("*"):
            if f.suffix in (".js", ".html"):
                text = f.read_text(encoding="utf-8")
                self.assertNotIn("SERVICE_ROLE", text, f)
                self.assertNotIn("sb_secret_", text, f)


if __name__ == "__main__":
    unittest.main()
