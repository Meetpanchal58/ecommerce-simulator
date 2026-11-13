"""Each customer's hidden taste: how much they like each product.

The simulated shoppers click and buy in proportion to this score. It is saved under
_ground_truth/ so an evaluation can compare a recommender with "perfect knowledge",
but it never appears in the normal tables.

score = quality x season fit x gender fit x category fit x colour fit x style fit x price fit
"""
import numpy as np
import pandas as pd

from . import reference as ref


def season_fit_by_month(products: pd.DataFrame) -> dict[int, np.ndarray]:
    """For each month 1-12, how much in season each product is (1.0 = neutral)."""
    article = products.article_type.to_numpy()
    usage = products.usage.to_numpy()
    season = products.season.to_numpy()
    out = {}
    for month in range(1, 13):
        fit = np.ones(len(products))
        summer = month in (4, 5, 6)
        winter = month in (11, 12, 1, 2)
        festive = month in (10, 11)
        fit = np.where(summer & np.isin(article, list(ref.SUMMER_TYPES)), fit * 1.35, fit)
        fit = np.where(summer & np.isin(article, list(ref.WINTER_TYPES)), fit * 0.6, fit)
        fit = np.where(winter & (np.isin(article, list(ref.WINTER_TYPES)) | (season == "Winter")), fit * 1.4, fit)
        fit = np.where(festive & (usage == "Ethnic"), fit * 1.45, fit)
        fit = np.where((month in (1, 2, 3, 4, 5)) & (usage == "Sports"), fit * 1.1, fit)
        out[month] = fit
    return out


def audience_of(gender: str) -> set[str]:
    """Product genders a shopper normally buys for themselves."""
    if gender == "F":
        return {"Women", "Girls"}
    if gender == "M":
        return {"Men", "Boys"}
    return {"Women", "Men"}


class TasteModel:
    """Scores products for a customer quickly, using pre-computed product arrays."""

    def __init__(self, products: pd.DataFrame):
        self.category = products.category.to_numpy()
        self.gender = products.gender.to_numpy()
        self.colour = products.colour.to_numpy()
        self.usage = products.usage.to_numpy()
        self.quality = np.exp(0.18 * products.quality.to_numpy())
        self.mrp = products.mrp.to_numpy(dtype=float)
        self.median_price = float(np.median(self.mrp))
        self.season_fit = season_fit_by_month(products)
        # Gender fit for each kind of shopper, worked out once for the whole catalogue.
        self.gender_fit = {}
        for shopper in ("F", "M", "Other"):
            audience = list(audience_of(shopper))
            self.gender_fit[shopper] = np.where(np.isin(self.gender, audience), 1.0,
                                                np.where(self.gender == "Unisex", 0.8, 0.07))

        # Small integer codes make the per-shopper lookups fast.
        self.category_values, self.category_code = np.unique(self.category, return_inverse=True)
        self.colour_values, self.colour_code = np.unique(self.colour, return_inverse=True)
        self.usage_values, self.usage_code = np.unique(self.usage, return_inverse=True)

    # ------------------------------------------------------------------ fast scoring for one day
    def prepare_day(self, month: int, prices: np.ndarray) -> None:
        """Parts of the score that are the same for every shopper today (season and price)."""
        price = np.where(np.isnan(prices), self.mrp, prices)
        self.today_base = self.quality * self.season_fit[month]
        self.today_relative_price = np.clip(price / self.median_price - 1, -0.8, 4)

    def _tables(self, profile: dict) -> tuple:
        """Per-shopper lookup tables (made once per shopper and kept in their profile)."""
        tables = profile.get("_taste_tables")
        if tables is None:
            tables = (np.where(self.category_values == profile["category_focus"], 2.4, 0.7),
                      np.where(self.colour_values == profile["colour_focus"], 1.6, 0.9),
                      np.where(self.usage_values == profile["preferred_usage"], 1.5, 0.85),
                      self.gender_fit[profile["gender"]])
            profile["_taste_tables"] = tables
        return tables

    def score_today(self, profile: dict, positions: np.ndarray) -> np.ndarray:
        """Same value as score(...) with today's prices, computed with lookups."""
        p = positions
        category, colour, usage, gender = self._tables(profile)
        return (self.today_base[p] * gender[p] * category[self.category_code[p]] * colour[self.colour_code[p]]
                * usage[self.usage_code[p]] * np.exp(-profile["price_sensitivity"] * self.today_relative_price[p]))

    def score(self, profile: dict, positions: np.ndarray, month: int, prices: np.ndarray | None = None) -> np.ndarray:
        """Taste score of the products at `positions` for one customer."""
        p = positions
        gender_fit = self.gender_fit[profile["gender"]][p]
        category_fit = np.where(self.category[p] == profile["category_focus"], 2.4, 0.7)
        colour_fit = np.where(self.colour[p] == profile["colour_focus"], 1.6, 0.9)
        style_fit = np.where(self.usage[p] == profile["preferred_usage"], 1.5, 0.85)
        price = self.mrp[p] if prices is None else prices
        relative = np.clip(price / self.median_price - 1, -0.8, 4)
        price_fit = np.exp(-profile["price_sensitivity"] * relative)
        return self.quality[p] * self.season_fit[month][p] * gender_fit * category_fit * colour_fit * style_fit * price_fit
