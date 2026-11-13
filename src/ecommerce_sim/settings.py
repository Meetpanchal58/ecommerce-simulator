"""Settings for one simulated shop: size, dates, seed and where data is written.

Every value can be overridden with an environment variable (ECOMSIM_...) or from the
command line, so tests and CI can run a small shop quickly.
"""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

# Ready-made shop sizes. Explicit settings (flags or environment variables) override these.
SIZES = {
    "small": {"n_products": 1_500, "n_sellers": 80, "traffic_scale": 0.17, "daily_new_visitors": 30},
    "medium": {"n_products": 5_000, "n_sellers": 200, "traffic_scale": 0.5, "daily_new_visitors": 80},
    "full": {"n_products": 10_000, "n_sellers": 400, "traffic_scale": 1.0, "daily_new_visitors": 160},
}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    seed: int = 42
    start_date: str = "2025-01-01"   # the shop opens on this day
    today: str = ""                  # last day to simulate; empty = the real today
    n_products: int = 10_000         # product styles taken from the catalogue
    n_sellers: int = 400
    n_agents: int = 100
    traffic_scale: float = 1.0       # marketing budgets and clicks relative to the full-size shop
    daily_new_visitors: float = 160  # new (anonymous) visitors per day before marketing

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(self.start_date).normalize()

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(self.today or date.today().isoformat()).normalize()

    @property
    def scale(self) -> float:
        """How big this shop's marketing is compared with the full-size shop."""
        return self.traffic_scale


def from_environment(size: str | None = None, **overrides) -> Settings:
    """Settings from a size preset, then ECOMSIM_* environment variables, then explicit overrides."""
    env = {
        "data_dir": os.getenv("ECOMSIM_DATA_DIR"),
        "seed": os.getenv("ECOMSIM_SEED"),
        "start_date": os.getenv("ECOMSIM_START_DATE"),
        "today": os.getenv("ECOMSIM_TODAY"),
        "n_products": os.getenv("ECOMSIM_PRODUCTS"),
        "n_sellers": os.getenv("ECOMSIM_SELLERS"),
        "traffic_scale": os.getenv("ECOMSIM_TRAFFIC_SCALE"),
        "daily_new_visitors": os.getenv("ECOMSIM_DAILY_NEW_VISITORS"),
    }
    size = size or os.getenv("ECOMSIM_SIZE") or "full"
    size = {"large": "full"}.get(size, size)          # "large" is another name for "full"
    if size not in SIZES:
        raise ValueError(f"size must be one of {', '.join(SIZES)}")
    values = dict(SIZES[size])
    values.update({key: value for key, value in env.items() if value not in (None, "")})
    values.update({key: value for key, value in overrides.items() if value not in (None, "")})
    types = {"seed": int, "n_products": int, "n_sellers": int, "traffic_scale": float,
             "daily_new_visitors": float, "data_dir": Path}
    for key, kind in types.items():
        if key in values:
            values[key] = kind(values[key])
    return Settings(**values)
