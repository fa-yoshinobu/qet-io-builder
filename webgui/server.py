"""ブラウザで画面を確認するための小さなサーバー(127.0.0.1 のみ)。

pywebview が無い環境や画面の自動確認で使う。ファイル選択の代わりに、画面でパスを入力する。"""
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).resolve().parent / 'static'


def make_server(api, port=0):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, body, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            name = self.path.split('?')[0].lstrip('/') or 'index.html'
            if name == 'mode.js':
                self._send(200, b'window.BROWSER_MODE = true;', 'text/javascript; charset=utf-8')
                return
            target = (STATIC / name).resolve()
            if STATIC not in target.parents or not target.is_file():
                self._send(404, b'not found', 'text/plain')
                return
            content_type = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
            if content_type.startswith('text/') or content_type.endswith('javascript'):
                content_type += '; charset=utf-8'
            self._send(200, target.read_bytes(), content_type)

        def do_POST(self):
            name = self.path.removeprefix('/api/')
            method = getattr(api, name, None)
            if name.startswith('_') or not callable(method):
                self._send(404, b'{}', 'application/json')
                return
            length = int(self.headers.get('Content-Length', 0))
            args = json.loads(self.rfile.read(length) or b'[]')
            with lock:
                result = method(*args)
            self._send(200, json.dumps(result, ensure_ascii=False).encode('utf-8'), 'application/json; charset=utf-8')

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)
