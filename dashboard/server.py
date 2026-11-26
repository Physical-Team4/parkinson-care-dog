"""PD-Dog 대시보드 정적 서버 (담당: D).

데이터는 Supabase에 직접 연결한다 (docs/api.md, docs/db.md). 이 서버는
  - 화면 파일(static/)과
  - /config.js (데이터 소스, SUPABASE_URL, SUPABASE_ANON_KEY)
만 내준다. 저장·로그인·권한은 Supabase(Auth + RLS)가 한다.

키 규칙 (CLAUDE.md): SUPABASE_SERVICE_ROLE_KEY는 읽지 않는다. anon 자리에 secret/service_role 키가
들어 있으면 시작을 거부한다 (프론트엔드로 새어 나가지 않게).

실행 (dashboard/ 폴더에서):  python server.py            → http://127.0.0.1:8000
  데이터 소스: DASHBOARD_DATA_SOURCE=supabase|mock (비우면 URL·anon 키가 있으면 supabase, 없으면 mock)
  값은 환경변수 → 레포 루트 .env 순서로 읽는다.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
DEFAULT_ENV_FILE = HERE.parent / ".env"

PAGES = {"/": "index.html", "/settings": "settings.html", "/report": "report.html", "/login": "login.html"}
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".ico": "image/x-icon", ".json": "application/json; charset=utf-8"}
SUPABASE_JS = "https://cdn.jsdelivr.net"   # store-supabase.js가 supabase-js(고정 버전)를 여기서 받는다


class ConfigError(Exception):
    pass


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE 줄만 읽는다 (주석·빈 줄 무시, 따옴표 제거). 파일이 없으면 빈 dict."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def looks_secret(key: str) -> bool:
    """secret(sb_secret_...) 또는 role=service_role인 옛 JWT 키면 True."""
    if key.startswith("sb_secret_"):
        return True
    parts = key.split(".")
    if len(parts) == 3:
        try:
            payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
            return payload.get("role") == "service_role"
        except (ValueError, json.JSONDecodeError):
            return False
    return False


def load_config(env: Mapping[str, str]) -> dict:
    url = (env.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (env.get("SUPABASE_ANON_KEY") or "").strip()
    source = (env.get("DASHBOARD_DATA_SOURCE") or "").strip().lower() or ("supabase" if url and key else "mock")
    if source == "mock":
        return {"dataSource": "mock"}
    if source != "supabase":
        raise ConfigError(f"DASHBOARD_DATA_SOURCE는 supabase 또는 mock이어야 해요 (지금: {source})")
    if not url or not key:
        raise ConfigError("supabase 모드에는 SUPABASE_URL과 SUPABASE_ANON_KEY가 필요해요 (.env)")
    if looks_secret(key):
        raise ConfigError("SUPABASE_ANON_KEY에 secret(service_role) 키가 들어 있어요. "
                          "대시보드에는 anon(publishable) 키만 넣으세요 (CLAUDE.md)")
    if not (url.startswith("https://") or url.startswith(("http://127.0.0.1", "http://localhost"))):
        raise ConfigError("SUPABASE_URL은 https:// 주소여야 해요 (로컬 테스트만 http://127.0.0.1 허용)")
    return {"dataSource": "supabase", "supabaseUrl": url, "supabaseAnonKey": key}


def csp(config: dict) -> str:
    connect = "'self'"
    if config.get("dataSource") == "supabase":
        url = config["supabaseUrl"]
        ws = "wss://" + url[len("https://"):] if url.startswith("https://") else "ws://" + url[len("http://"):]
        connect += f" {url} {ws}"
    return ("default-src 'self'; "
            f"script-src 'self' 'unsafe-inline' {SUPABASE_JS}; "
            f"connect-src {connect}; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'")


class Handler(BaseHTTPRequestHandler):
    server_version = "PD-Dog-Dashboard"

    def do_GET(self):
        self._serve(send_body=True)

    def do_HEAD(self):
        self._serve(send_body=False)

    def do_POST(self):
        self._send(405, b"Method Not Allowed", "text/plain; charset=utf-8", True)

    do_PUT = do_DELETE = do_PATCH = do_POST

    def _serve(self, send_body: bool):
        path = unquote(urlsplit(self.path).path)
        if path == "/config.js":
            body = ("window.PD_CONFIG = " + json.dumps(self.server.config) + ";\n").encode("utf-8")
            return self._send(200, body, TYPES[".js"], send_body)
        file = STATIC / PAGES[path] if path in PAGES else (STATIC / path.lstrip("/")).resolve()
        if (not file.is_relative_to(STATIC) or file.suffix not in TYPES
                or not file.is_file() or path.endswith(".html")):
            return self._send(404, "찾을 수 없어요".encode("utf-8"), "text/plain; charset=utf-8", send_body)
        self._send(200, file.read_bytes(), TYPES[file.suffix], send_body)

    def _send(self, code: int, body: bytes, ctype: str, send_body: bool):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", self.server.csp)
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def log_message(self, fmt, *args):   # 접속 로그는 남기지 않는다 (오류만 stderr)
        if len(args) > 1 and str(args[1]).startswith("5"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


def make_server(host: str, port: int, config: dict) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), Handler)
    server.config = config
    server.csp = csp(config)
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="PD-Dog 돌봄 대시보드 (정적 서버)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="0.0.0.0 으로 하면 같은 와이파이의 다른 기기에서도 접속 (기본: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="포트 번호 (기본: 8000)")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_FILE), help="설정 파일 (기본: 레포 루트 .env)")
    parser.add_argument("--mock", action="store_true", help="Supabase 없이 Mock 데이터로 실행")
    args = parser.parse_args(argv)

    import os
    env = {**read_env_file(Path(args.env_file)), **os.environ}
    if args.mock:
        env["DASHBOARD_DATA_SOURCE"] = "mock"
    try:
        config = load_config(env)
    except ConfigError as e:
        print("설정 오류:", e)
        return 1
    try:
        server = make_server(args.host, args.port, config)
    except OSError:
        print(f"{args.port}번 포트를 이미 다른 프로그램이 쓰고 있어요. 다른 창에서 server.py가 켜져 있는지 확인하세요.")
        return 1
    port = server.server_address[1]
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    mode = "Supabase 연결" if config["dataSource"] == "supabase" else "Mock (Supabase 없이 예시 데이터)"
    print(f"PD-Dog 대시보드 실행 중: http://{shown}:{port}  · 데이터: {mode}", flush=True)
    print("끄려면 Ctrl+C", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
