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
import urllib.error
import urllib.request
from pathlib import Path

from . import __version__

REPO = os.getenv("ECOMSIM_DATA_REPO", "Meetpanchal58/ecommerce-simulator")
TAG = "data-latest"
PART_BYTES = 1_900_000_000      # GitHub release assets must be under 2 GB, so big archives are split


def asset_name(size: str) -> str:
    return f"ecommerce-sim-data-{size}.tar.gz"


def _release_url(size: str) -> str:
    return f"https://github.com/{REPO}/releases/download/{TAG}/{asset_name(size)}"


def download(data_dir, size: str = "full") -> Path:
    data_dir = Path(data_dir)
    url = _release_url(size)
    print(f"Downloading {size} data from {url} ...")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset_name(size)
        with open(archive, "wb") as out:
            for part_url in _part_urls(url):
                with urllib.request.urlopen(part_url) as response:
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


def _part_urls(url: str):
    """The archive itself, or (for big shops) its parts .part01, .part02, ... in order."""
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD")).close()
        yield url
        return
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    number = 1
    while True:
        part = f"{url}.part{number:02d}"
        try:
            urllib.request.urlopen(urllib.request.Request(part, method="HEAD")).close()
        except urllib.error.HTTPError as error:
            if error.code == 404 and number > 1:
                return
            raise
        print(f"  part {number}")
        yield part
        number += 1


def package(data_dir, size: str, out_dir) -> list[Path]:
    """Pack a data folder (with its manifest) for publishing (used by the daily workflow).

    Returns the archive, or its parts when it is bigger than one release asset may be."""
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / asset_name(size)
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(data_dir.iterdir()):
            tar.add(path, arcname=path.name)
    if archive.stat().st_size <= PART_BYTES:
        return [archive]
    parts = []
    with open(archive, "rb") as whole:
        while whole.tell() < archive.stat().st_size:
            part = archive.with_name(f"{archive.name}.part{len(parts) + 1:02d}")
            with open(part, "wb") as out:
                left = PART_BYTES
                while left and (chunk := whole.read(min(left, 64 << 20))):
                    out.write(chunk)
                    left -= len(chunk)
            parts.append(part)
    archive.unlink()
    return parts
