"""The catalogue: product styles, their sizes (SKUs), sellers, warehouses and support agents.

Hierarchy:  category -> sub-category -> article type -> product (style) -> SKU (size)

The whole catalogue, including styles that launch later, is created once when the
shop is loaded. Each run publishes only what exists by "today" (launched products,
onboarded sellers), so later runs reveal new launches as time moves on.
"""
from importlib import resources

import numpy as np
import pandas as pd

from . import reference as ref
from .randomness import stream

# Products launch in seasonal "drops" (spring/summer in Feb-Mar, autumn/winter in Aug-Sep).
DROP_MONTHS = ["2025-02", "2025-03", "2025-08", "2025-09", "2026-02", "2026-03", "2026-08", "2026-09",
               "2027-02", "2027-03", "2027-08", "2027-09"]
SHARE_LIVE_AT_OPENING = 0.62
SHARE_DISCONTINUED = 0.22


def load_catalogue_file() -> pd.DataFrame:
    """The cleaned Kaggle fashion catalogue that ships with the package."""
    path = resources.files("ecommerce_sim").joinpath("resources/product_catalog.csv")
    with resources.as_file(path) as file:
        catalogue = pd.read_csv(file)
    catalogue = catalogue[catalogue.masterCategory.isin(["Apparel", "Footwear", "Accessories"])]
    return catalogue.dropna(subset=["productDisplayName", "articleType", "baseColour"]).reset_index(drop=True)


def sizes_for(category: str, sub_category: str, article_type: str) -> list[str]:
    """Which sizes a style of this kind is sold in."""
    free_size_types = {"Sarees", "Stoles", "Scarves", "Dupatta", "Socks", "Ties", "Mufflers"}
    if category == "Apparel" and article_type not in free_size_types:
        return ref.APPAREL_SIZES
    if category == "Footwear" and article_type != "Socks":
        return ref.FOOTWEAR_SIZES
    return ref.FREE_SIZE


def build_products(settings) -> pd.DataFrame:
    """Product styles (one row per style), with launch/discontinue dates and hidden quality."""
    rng = stream(settings.seed, "catalog.products")
    source = load_catalogue_file()

    # Keep the mix of categories and article types when taking a sample of the catalogue.
    share = min(1.0, settings.n_products / len(source))
    picked = []
    for _, group in source.groupby(["masterCategory", "articleType"], sort=True):
        take = max(1, int(round(len(group) * share)))
        picked.append(group.sample(min(take, len(group)), random_state=int(rng.integers(1, 2**31))))
    styles = pd.concat(picked).sort_values("id")
    styles = styles.sample(frac=1, random_state=int(rng.integers(1, 2**31))).head(settings.n_products)
    styles = styles.reset_index(drop=True)
    n = len(styles)

    category = styles.masterCategory.astype(str).to_numpy()
    article = styles.articleType.astype(str).to_numpy()
    sub_category = styles.subCategory.astype(str).to_numpy()

    base = np.array([ref.BASE_PRICE[c] for c in category], dtype=float)
    premium = np.array([ref.PREMIUM_TYPES.get(a, 1.0) for a in article])
    mrp = np.clip(np.round(base * premium * rng.uniform(0.6, 1.9, n) / 10) * 10 - 1, 199, 24_999)
    unit_cost = np.round(mrp * rng.uniform(0.38, 0.62, n), 2)

    # Launch dates: most styles are live when the shop opens, the rest arrive in drops.
    opening = settings.start
    live_at_opening = rng.random(n) < SHARE_LIVE_AT_OPENING
    early = opening - pd.to_timedelta(rng.integers(15, 500, n), unit="D")
    drop_month = rng.choice(DROP_MONTHS, n)
    later = pd.to_datetime([f"{m}-01" for m in drop_month]) + pd.to_timedelta(rng.integers(0, 28, n), unit="D")
    launch = np.where(live_at_opening, early, later)
    launch = pd.to_datetime(launch)
    discontinued = rng.random(n) < SHARE_DISCONTINUED
    discontinue = launch + pd.to_timedelta(rng.integers(240, 700, n), unit="D")
    discontinue = pd.to_datetime(np.where(discontinued, discontinue, pd.NaT))

    materials = [rng.choice(ref.MATERIALS.get(s, ref.DEFAULT_MATERIALS)) for s in sub_category]
    fit = np.where(category == "Apparel", rng.choice(ref.FITS, n, p=[0.5, 0.25, 0.15, 0.10]), None)
    brand = styles.productDisplayName.str.split().str[0].fillna("Generic").to_numpy()

    products = pd.DataFrame({
        "product_id": [f"P{i:06d}" for i in range(1, n + 1)],
        "source_product_id": styles.id.astype(int).to_numpy(),
        "product_name": styles.productDisplayName.astype(str).to_numpy(),
        "brand_name": brand,
        "gender": styles.gender.astype(str).to_numpy(),
        "category": category,
        "sub_category": sub_category,
        "article_type": article,
        "colour": styles.baseColour.astype(str).to_numpy(),
        "season": styles.season.astype(str).to_numpy(),
        "usage": styles.usage.astype(str).to_numpy(),
        "material": materials,
        "fit": fit,
        "size_type": [("Apparel" if s == ref.APPAREL_SIZES else "Footwear" if s == ref.FOOTWEAR_SIZES else "Free Size")
                      for s in (sizes_for(c, sc, a) for c, sc, a in zip(category, sub_category, article))],
        "mrp": mrp,
        "unit_cost": unit_cost,
        "gst_rate": [ref.gst_rate(c, p) for c, p in zip(category, mrp)],
        "seller_id": "",                    # filled by build_sellers
        "launch_date": launch.normalize(),
        "discontinue_date": discontinue.normalize(),
        "image_url": styles.link.fillna("").astype(str).to_numpy(),
        "description": [f"{name}. {col} {art.lower()} in {mat.lower()} for {gen.lower()}; {use.lower()} wear."
                        for name, col, art, mat, gen, use in zip(styles.productDisplayName, styles.baseColour,
                                                                 article, materials, styles.gender, styles.usage)],
        # Hidden: true quality drives ratings and quality returns; not published in the master.
        "quality": np.clip(rng.normal(0.0, 1.0, n), -2.5, 2.5),
    })
    return products


def build_skus(settings, products: pd.DataFrame) -> pd.DataFrame:
    """One row per size of each style. Most styles skip the smallest or largest sizes."""
    rng = stream(settings.seed, "catalog.skus")
    rows = []
    for product in products.itertuples(index=False):
        sizes = sizes_for(product.category, product.sub_category, product.article_type)
        if len(sizes) > 1:
            first = int(rng.integers(0, 2))                 # sometimes no XS / size 6
            last = len(sizes) - int(rng.integers(0, 2))     # sometimes no XXL / size 11
            sizes = sizes[first:last]
        for size in sizes:
            rows.append((product.product_id, size))
    skus = pd.DataFrame(rows, columns=["product_id", "size"])
    skus.insert(0, "sku_id", skus.product_id + "-" + skus["size"].str.replace(" ", "", regex=False).str.upper())
    digits = rng.integers(0, 10, size=(len(skus), 9))
    skus["barcode"] = [ean13("890" + "".join(map(str, row))) for row in digits]
    return skus


def ean13(first_twelve: str) -> str:
    """Add the check digit to a 12-digit barcode number."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first_twelve))
    return first_twelve + str((10 - total % 10) % 10)


def build_sellers(settings, products: pd.DataFrame) -> pd.DataFrame:
    """Sellers, and which seller sells each product (onboarded before their first launch)."""
    rng = stream(settings.seed, "catalog.sellers")
    n = settings.n_sellers
    cities = list(ref.CITIES)
    weights = np.array([ref.TIER_WEIGHT[ref.CITIES[c][2]] for c in cities])
    city = rng.choice(cities, n, p=weights / weights.sum())
    seller_ids = [f"S{i:04d}" for i in range(1, n + 1)]

    # Bigger sellers carry more styles.
    size = rng.pareto(1.6, n) + 1
    products["seller_id"] = rng.choice(seller_ids, len(products), p=size / size.sum())
    first_launch = products.groupby("seller_id").launch_date.min()

    onboarding = settings.start - pd.to_timedelta(rng.integers(30, 1500, n), unit="D")
    onboarding = pd.Series(onboarding, index=seller_ids)
    onboarding = onboarding.where(onboarding <= first_launch.reindex(seller_ids) - pd.Timedelta(days=30),
                                  first_launch.reindex(seller_ids) - pd.Timedelta(days=30)).fillna(onboarding)

    return pd.DataFrame({
        "seller_id": seller_ids,
        "seller_name": [f"{rng.choice(ref.SELLER_WORDS_1)} {rng.choice(ref.SELLER_WORDS_2)} {i}" for i in range(1, n + 1)],
        "seller_type": rng.choice(ref.SELLER_TYPES, n, p=ref.SELLER_TYPE_SHARE),
        "city": city,
        "state": [ref.CITIES[c][0] for c in city],
        "region": [ref.CITIES[c][1] for c in city],
        "home_warehouse_id": [ref.CITIES[c][4] for c in city],
        "onboarding_date": onboarding.dt.normalize().to_numpy(),
        "rating": np.round(np.clip(rng.normal(4.1, 0.35, n), 2.5, 5.0), 1),
        "fulfillment_score": np.round(np.clip(rng.normal(0.93, 0.05, n), 0.70, 0.995), 3),
        "cancellation_rate": np.round(np.clip(rng.normal(0.02, 0.01, n), 0.002, 0.08), 3),
        "lead_time_days": rng.integers(3, 15, n),
        "commission_rate": np.round(rng.choice([0.08, 0.12, 0.15, 0.18], n), 2),
        "is_active": True,
    })


def build_warehouses() -> pd.DataFrame:
    return pd.DataFrame([
        {"warehouse_id": wid, "city": city, "region": region, "capacity_units": capacity}
        for wid, (city, region, capacity) in ref.WAREHOUSES.items()
    ])


def build_agents(settings) -> pd.DataFrame:
    rng = stream(settings.seed, "catalog.agents")
    n = settings.n_agents
    return pd.DataFrame({
        "agent_id": [f"AG{i:03d}" for i in range(1, n + 1)],
        "agent_name": [f"{rng.choice(ref.FIRST_NAMES)} {rng.choice(ref.LAST_NAMES)}" for _ in range(n)],
        "team": rng.choice(ref.SUPPORT_TEAMS, n, p=[0.35, 0.25, 0.20, 0.20]),
        "location": rng.choice(ref.AGENT_LOCATIONS, n),
        "language": rng.choice(ref.AGENT_LANGUAGES, n, p=[0.40, 0.30, 0.10, 0.10, 0.10]),
        "hire_date": (settings.start - pd.to_timedelta(rng.integers(30, 1400, n), unit="D")).normalize(),
    })
