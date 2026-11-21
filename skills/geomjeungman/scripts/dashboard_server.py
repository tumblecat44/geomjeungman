from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from mimetypes import guess_type
from secrets import token_urlsafe
from subprocess import TimeoutExpired
from threading import Lock
from urllib.parse import quote, unquote
import webbrowser

from preview import destination, generate, screenshot_size


def serve(root, data, render, write_index, open_browser):
    root = root.resolve()
    assets = set()
    shots = {}
    for run in data["runs"]:
        assets.update(url for url in (run["report"], run["findingsPath"]) if url)
        for shot in run["shots"]:
            assets.update(url for url in (shot["src"], shot["marked"]) if url)
            if shot["preview"]:
                assets.add(shot["preview"]["src"])
            if shot["issues"]:
                shots[shot["src"]] = shot
    data["previewEnabled"] = True
    prefix = f"/{token_urlsafe(24)}/"
    job = Lock()

    def asset_path(url):
        path = (root / unquote(url)).resolve()
        if not path.is_relative_to(root):
            raise ValueError("검사 폴더 밖의 파일입니다.")
        return path

    class Handler(BaseHTTPRequestHandler):
        def send(self, status, content, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cache-Control", "no-store")
            policy = "default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'"
            self.send_header("Content-Security-Policy", policy if content_type.startswith("text/html") else "default-src 'none'; sandbox")
            self.end_headers()
            self.wfile.write(content)

        def reply(self, status, payload):
            self.send(status, json.dumps(payload, ensure_ascii=False).encode(), "application/json; charset=utf-8")

        def authorized(self):
            return self.headers.get("Host") == address and self.path.startswith(prefix)

        def do_GET(self):
            path = self.path[len(prefix):]
            if not self.authorized() or (path and path not in assets):
                self.send_error(404)
                return
            try:
                if not path:
                    self.send(200, render(data).encode(), "text/html; charset=utf-8")
                else:
                    self.send(200, asset_path(path).read_bytes(), guess_type(path)[0] or "text/plain")
            except (OSError, ValueError):
                self.send_error(404)

        def do_POST(self):
            if not self.authorized() or self.path != prefix + "preview" or self.headers.get("Origin") != origin:
                self.send_error(403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 4096 or self.headers.get_content_type() != "application/json":
                    raise ValueError
                url = json.loads(self.rfile.read(size))["shot"]
                shot = shots[url]
                screenshot = asset_path(url)
            except (KeyError, TypeError, ValueError):
                self.reply(400, {"error": "수정 제안이 있는 스크린샷을 골라주세요."})
                return
            if not job.acquire(blocking=False):
                self.reply(409, {"error": "다른 미리보기를 생성하고 있습니다."})
                return
            try:
                output = destination(screenshot, shot["context"], shot["issues"])
                if not output.is_file():
                    generate(screenshot, output, shot["context"], shot["issues"])
                url = quote(output.relative_to(root).as_posix())
                preview = {"src": url, "pixels": screenshot_size(asset_path(url))}
                assets.add(url)
                shot["preview"] = preview
                write_index(data)
                self.reply(200, {"preview": preview})
            except TimeoutExpired:
                self.reply(504, {"error": "이미지 생성 시간이 초과되었습니다. 다시 시도하세요."})
            except RuntimeError as error:
                self.reply(502, {"error": str(error)})
            except (OSError, ValueError):
                self.reply(502, {"error": "미리보기 파일을 읽거나 저장할 수 없습니다."})
            finally:
                job.release()

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        address = f"127.0.0.1:{server.server_port}"
        origin = f"http://{address}"
        url = origin + prefix
        print(url, flush=True)
        if open_browser:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
