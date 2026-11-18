"""Serve the local SetupVault interface on loopback."""

import argparse
import base64
import binascii
import json
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Timer

from evaluation import demo_material, evaluate
from silverstone import detail_png
from vault import MAX_JSON_BYTES, MAX_PNG_BYTES, VaultError, backup, digest, read_png, restore

ROOT = Path(__file__).resolve().parent / "web"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/archivo-variable.ttf": ("archivo-variable.ttf", "font/ttf"),
}
MAX_REQUEST_BYTES = 4 * (MAX_JSON_BYTES + 3 * MAX_PNG_BYTES) // 3 + 1024


def to_base64(data):
    return base64.b64encode(data).decode("ascii")


def from_base64(value, limit, label):
    if not isinstance(value, str) or not value:
        raise VaultError(f"{label} belum dipilih.")
    if len(value) > 4 * ((limit + 2) // 3):
        raise VaultError(f"Ukuran {label} melebihi batas.")
    try:
        data = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise VaultError(f"Data {label} tidak dapat dibaca.") from error
    if len(data) > limit:
        raise VaultError(f"Ukuran {label} melebihi batas.")
    return data


def read_list(body, key, count, label):
    items = body.get(key)
    if not isinstance(items, list) or len(items) != count:
        raise VaultError(f"Pilih tepat {count} {label}.")
    return [from_base64(value, MAX_PNG_BYTES, f"{label} {i}") for i, value in enumerate(items, 1)]


def create_backup(body):
    source = from_base64(body.get("data"), MAX_JSON_BYTES, "JSON")
    covers = []
    for i, data in enumerate(read_list(body, "covers", 3, "kartu sampul"), 1):
        try:
            covers.append(read_png(data))
        except VaultError as error:
            raise VaultError(f"Sampul {chr(64 + i)}: {error}") from error
    package_id, cards = backup(source, covers)
    return {"package": package_id.hex(), "digest": digest(source), "cards": [to_base64(card) for card in cards]}


def recover_backup(body):
    package_id, indices, data = restore(read_list(body, "cards", 2, "kartu cadangan"))
    return {"package": package_id.hex(), "indices": indices, "digest": digest(data), "data": to_base64(data)}


class SetupVaultHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, *_):
        pass

    def allowed_host(self):
        port = self.server.server_port
        return self.headers.get("Host") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def send_bytes(self, status, content_type, data):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, result):
        self.send_bytes(status, "application/json; charset=utf-8", json.dumps(result).encode("utf-8"))

    def do_GET(self):
        if not self.allowed_host():
            self.send_json(403, {"error": "Gunakan alamat lokal SetupVault."})
        elif self.path in ASSETS:
            filename, content_type = ASSETS[self.path]
            self.send_bytes(200, content_type, (ROOT / filename).read_bytes())
        elif self.path == "/api/demo":
            data, covers = demo_material()
            self.send_json(200, {"data": to_base64(data), "covers": [to_base64(cover) for cover in covers]})
        elif self.path == "/silverstone-detail.png":
            self.send_bytes(200, "image/png", detail_png())
        else:
            self.send_json(404, {"error": "Halaman tidak ditemukan."})

    def do_POST(self):
        host = self.headers.get("Host")
        if not self.allowed_host() or self.headers.get("Origin") != f"http://{host}":
            self.send_json(403, {"error": "Permintaan harus berasal dari halaman lokal SetupVault."})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Format permintaan harus JSON."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= MAX_REQUEST_BYTES:
                raise VaultError("Ukuran permintaan melebihi batas atau kosong.")
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise VaultError("Format permintaan tidak valid.")
            if self.path == "/api/backup":
                result = create_backup(body)
            elif self.path == "/api/restore":
                result = recover_backup(body)
            elif self.path == "/api/evaluate":
                result = evaluate()
            else:
                self.send_json(404, {"error": "Operasi tidak ditemukan."})
                return
        except VaultError as error:
            self.send_json(400, {"error": str(error)})
            return
        except (ValueError, RecursionError, TimeoutError):
            self.send_json(400, {"error": "Permintaan tidak dapat dibaca."})
            return
        self.send_json(200, result)


def main():
    parser = argparse.ArgumentParser(description="Jalankan SetupVault pada komputer ini.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Buka browser setelah server siap.")
    options = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", options.port), SetupVaultHandler) as server:
        address = f"http://127.0.0.1:{server.server_port}"
        print(f"SetupVault berjalan di {address}. Tekan Ctrl+C untuk berhenti.", flush=True)
        if options.open:
            timer = Timer(0.25, webbrowser.open, args=(address,))
            timer.daemon = True
            timer.start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
