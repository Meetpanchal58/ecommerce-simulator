"""Settings for one simulated shop: size, dates, seed and where data is written.

Every value can be overridden with an environment variable (ECOMSIM_...) or from the
command line, so tests and CI can run a small shop quickly.
"""
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("data")
    seed: int = 42
    start_date: str = "2025-01-01"   # the shop opens on this day
    today: str = ""                  # last day to simulate; empty = the real today
    n_products: int = 10_000         # product styles taken from the catalogue
    n_sellers: int = 400
    n_agents: int = 100
    launch_customers: int = 9_000    # customers who sign up in the opening weeks
    daily_new_visitors: float = 160  # new (anonymous) visitors per day before marketing

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(self.start_date).normalize()

    @property
    def end(self) -> pd.Timestamp:
        return pd.Timestamp(self.today or date.today().isoformat()).normalize()

    @property
    def scale(self) -> float:
        """How big this shop is compared with the default size (used to scale volumes)."""
        return self.launch_customers / 9_000


def from_environment(**overrides) -> Settings:
    """Settings from ECOMSIM_* environment variables, then explicit overrides."""
    env = {
        "data_dir": os.getenv("ECOMSIM_DATA_DIR"),
        "seed": os.getenv("ECOMSIM_SEED"),
        "start_date": os.getenv("ECOMSIM_START_DATE"),
        "today": os.getenv("ECOMSIM_TODAY"),
        "n_products": os.getenv("ECOMSIM_PRODUCTS"),
        "n_sellers": os.getenv("ECOMSIM_SELLERS"),
        "launch_customers": os.getenv("ECOMSIM_LAUNCH_CUSTOMERS"),
        "daily_new_visitors": os.getenv("ECOMSIM_DAILY_NEW_VISITORS"),
    }
    values = {key: value for key, value in env.items() if value not in (None, "")}
    values.update({key: value for key, value in overrides.items() if value not in (None, "")})
    types = {"seed": int, "n_products": int, "n_sellers": int, "launch_customers": int,
             "daily_new_visitors": float, "data_dir": Path}
    for key, kind in types.items():
        if key in values:
            values[key] = kind(values[key])
    return Settings(**values)
