"""Packing big data into release-sized parts and downloading it back."""
import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from ecommerce_sim import __version__, download


def test_big_archive_is_split_and_downloaded_back(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "clickstream" / "month=2025-01").mkdir(parents=True)
    (data / "clickstream" / "month=2025-01" / "part.parquet").write_bytes(os.urandom(100_000))
    (data / "manifest.json").write_text(json.dumps(
        {"size": "large", "first_day": "2025-01-01", "last_day": "2025-01-31", "package_version": __version__}))
    monkeypatch.setattr(download, "PART_BYTES", 20_000)
    parts = download.package(data, "large", tmp_path / "release")
    assert len(parts) > 1 and all(p.stat().st_size <= 20_000 for p in parts)

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path / "release"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/{download.asset_name('large')}"
        monkeypatch.setattr(download, "_release_url", lambda size: url)
        out = download.download(tmp_path / "copy", "large")
    finally:
        server.shutdown()
    original = data / "clickstream" / "month=2025-01" / "part.parquet"
    assert (out / "clickstream" / "month=2025-01" / "part.parquet").read_bytes() == original.read_bytes()
