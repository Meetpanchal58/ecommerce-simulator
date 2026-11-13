"""Reading and writing the generated tables.

Layout of the data folder:

    data/
      <table>.parquet            small and medium tables, rewritten on every run
      <table>/month=YYYY-MM/     big event tables (clickstream, impressions, ...),
          part.parquet           one file per month; new days are appended
      _state/                    the simulator's memory between runs (not for analysis)
      _ground_truth/             hidden truths for evaluation only (e.g. customer taste)
      derived/                   tables built by `ecommerce-sim derive`
"""
import json
import pickle
from pathlib import Path

import pandas as pd

STATE_VERSION = 1


class Store:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir)
        self.state_dir = self.root / "_state"
        self.truth_dir = self.root / "_ground_truth"

    def prepare(self, fresh: bool) -> None:
        """Create folders; with fresh=True, delete everything generated before."""
        if fresh and self.root.exists():
            for path in sorted(self.root.rglob("*"), reverse=True):
                if path.is_file() and (path.suffix in {".parquet", ".pkl", ".json"}):
                    path.unlink()
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
        for folder in (self.root, self.state_dir, self.truth_dir):
            folder.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ whole tables
    def write(self, name: str, frame: pd.DataFrame) -> None:
        frame.reset_index(drop=True).to_parquet(self.root / f"{name}.parquet", index=False)

    def write_truth(self, name: str, frame: pd.DataFrame) -> None:
        frame.reset_index(drop=True).to_parquet(self.truth_dir / f"{name}.parquet", index=False)

    def read(self, name: str, columns=None) -> pd.DataFrame:
        single = self.root / f"{name}.parquet"
        if single.exists():
            return pd.read_parquet(single, columns=columns)
        folder = self.root / name
        if folder.is_dir():
            parts = sorted(folder.glob("month=*/part.parquet"))
            if parts:
                return pd.concat([pd.read_parquet(p, columns=columns) for p in parts], ignore_index=True)
        return pd.DataFrame(columns=columns)

    # ------------------------------------------------------------------ monthly event tables
    def append_month(self, name: str, month: str, frame: pd.DataFrame) -> None:
        """Add rows to one month's file of a big event table (e.g. month='2025-03')."""
        if frame.empty:
            return
        folder = self.root / name / f"month={month}"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "part.parquet"
        if path.exists():
            frame = pd.concat([pd.read_parquet(path), frame], ignore_index=True)
        frame.reset_index(drop=True).to_parquet(path, index=False)

    def write_manifest(self, settings, first_day, last_day) -> None:
        """manifest.json: which shop this is and which days it covers."""
        from . import __version__
        from .settings import SIZES
        mine = {"n_products": settings.n_products, "n_sellers": settings.n_sellers,
                "traffic_scale": settings.traffic_scale, "daily_new_visitors": settings.daily_new_visitors}
        size = next((name for name, preset in SIZES.items() if preset == mine), "custom")
        manifest = {"size": size, "seed": settings.seed, "first_day": f"{first_day:%Y-%m-%d}",
                    "last_day": f"{last_day:%Y-%m-%d}", "package_version": __version__, **mine}
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # ------------------------------------------------------------------ simulator memory
    def save_state(self, state: dict) -> None:
        state = dict(state, state_version=STATE_VERSION)
        with open(self.state_dir / "state.pkl", "wb") as handle:
            pickle.dump(state, handle, protocol=pickle.HIGHEST_PROTOCOL)

    def load_state(self) -> dict | None:
        path = self.state_dir / "state.pkl"
        if not path.exists():
            return None
        with open(path, "rb") as handle:
            state = pickle.load(handle)
        if state.get("state_version") != STATE_VERSION:
            raise RuntimeError("Saved state is from another simulator version; run `ecommerce-sim load`.")
        return state
