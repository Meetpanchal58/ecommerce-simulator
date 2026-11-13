"""Download the ready-made data published on GitHub (refreshed every day).

A scheduled GitHub Action runs `ecommerce-sim increment` each night and publishes the
data as assets of the release tagged `data-latest`. Downloading it gives data up to
yesterday in about a minute; `ecommerce-sim increment` then adds any missing days.
"""
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from . import __version__

REPO = os.getenv("ECOMSIM_DATA_REPO", "Meetpanchal58/ecommerce-simulator")
TAG = "data-latest"


def asset_name(size: str) -> str:
    return f"ecommerce-sim-data-{size}.tar.gz"


def download(data_dir, size: str = "full") -> Path:
    data_dir = Path(data_dir)
    url = f"https://github.com/{REPO}/releases/download/{TAG}/{asset_name(size)}"
    print(f"Downloading {size} data from {url} ...")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset_name(size)
        with urllib.request.urlopen(url) as response, open(archive, "wb") as out:
            shutil.copyfileobj(response, out)
        if data_dir.exists() and any(data_dir.iterdir()):
            print(f"Replacing existing data in {data_dir}")
            shutil.rmtree(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tar:
            tar.extractall(data_dir, filter="data")
    manifest = json.loads((data_dir / "manifest.json").read_text())
    print(f"Data ready in {data_dir}: {manifest['size']} shop, {manifest['first_day']} -> {manifest['last_day']}")
    if manifest.get("package_version") != __version__:
        print(f"Note: data was made with ecommerce-simulator {manifest.get('package_version')}, you have {__version__}. "
              "Upgrade the package before running `increment`.")
    return data_dir


def package(data_dir, size: str, out_dir) -> Path:
    """Pack a data folder (with its manifest) for publishing (used by the daily workflow)."""
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / asset_name(size)
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(data_dir.iterdir()):
            tar.add(path, arcname=path.name)
    return archive
