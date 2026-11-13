"""Reproducible random numbers.

Each simulated day, and each part of the simulation, gets its own random stream that
depends only on (seed, day, part name). So:

* the same seed always produces the same data;
* simulating 1 Jan - 30 Jun in one go, or 1 Jan - 31 Mar and then 1 Apr - 30 Jun,
  gives identical results;
* changing one part (say, marketing) does not reshuffle the random numbers of another.
"""
import zlib

import numpy as np
import pandas as pd


def stream(seed: int, part: str, day: pd.Timestamp | None = None) -> np.random.Generator:
    """A random generator for one part of the simulation on one day."""
    part_key = zlib.crc32(part.encode())          # stable number for the part name
    day_key = 0 if day is None else pd.Timestamp(day).toordinal()
    return np.random.default_rng([seed, part_key, day_key])
