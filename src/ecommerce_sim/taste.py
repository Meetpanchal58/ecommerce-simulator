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
