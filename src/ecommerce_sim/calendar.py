"""The sales calendar: festivals and sales, live only on their own days.

Each event has a start and end date, the categories on offer, an extra discount and
a demand uplift. Shoppers start browsing more a few days before ("run-up") and buy a
little less for a few days after ("post-sale dip").
"""
import numpy as np
import pandas as pd

from . import reference as ref

POST_EVENT_DIP_DAYS = 3
POST_EVENT_DIP = 0.88
RUN_UP_LIFT = 0.15            # browsing rises up to +15% just before an event
WEEKDAY_FACTOR = [0.94, 0.95, 0.97, 0.98, 1.04, 1.07, 1.05]   # Monday ... Sunday
MONTH_FACTOR = {1: 0.95, 2: 0.92, 3: 1.00, 4: 1.00, 5: 1.02, 6: 1.02, 7: 0.98, 8: 1.00,
                9: 1.02, 10: 1.10, 11: 1.12, 12: 1.08}


def _dates_for(name: str, year: int) -> tuple[str, str] | None:
    if name in ref.FIXED_FESTIVALS:
        return ref.FIXED_FESTIVALS[name]
    by_year = ref.MOVING_FESTIVALS[name]
    if year in by_year:
        return by_year[year]
    # Years not in the table reuse the latest known dates (good enough for a simulation).
    return by_year[max(by_year)]


def build_events(settings) -> pd.DataFrame:
    """Every sale event from the opening year until two years later."""
    rows = []
    years = range(settings.start.year, max(settings.end.year, settings.start.year) + 2)
    for year in years:
        for name in list(ref.FIXED_FESTIVALS) + list(ref.MOVING_FESTIVALS):
            start, end = _dates_for(name, year)
            rows.append(_event_row(name, pd.Timestamp(f"{year}-{start}"), pd.Timestamp(f"{year}-{end}")))
        for month in range(1, 13):
            rows.append(_event_row("Payday Sale", pd.Timestamp(year, month, 1), pd.Timestamp(year, month, 3)))
    events = pd.DataFrame(rows).sort_values(["start_date", "name"]).reset_index(drop=True)

    # A payday sale is skipped when a bigger sale already runs on those days.
    big = events[events.event_type.isin(["Mega Sale", "Clearance", "Season Sale"])]
    def overlaps_big(row):
        return ((big.start_date <= row.end_date) & (big.end_date >= row.start_date)).any()
    payday = events.event_type == "Payday"
    events = events[~(payday & events.apply(overlaps_big, axis=1))].reset_index(drop=True)

    events.insert(0, "event_id", [f"EV{d:%Y%m%d}{i:02d}" for i, d in enumerate(events.start_date)])
    return events


def _event_row(name: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    event_type, categories, discount, uplift, run_up, early_access = ref.EVENT_RULES[name]
    return {
        "name": name if name == "Payday Sale" else f"{name} {start.year}",
        "event_type": event_type,
        "start_date": start,
        "end_date": end,
        "prime_early_access_date": start - pd.Timedelta(days=early_access) if early_access else pd.NaT,
        "categories_on_offer": categories,
        "avg_extra_discount": discount,
        "demand_uplift": uplift,
        "run_up_days": run_up,
    }


def published_events(events: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    """Events announced by today: already happened, running, or starting within 30 days."""
    return events[events.start_date <= today + pd.Timedelta(days=30)].reset_index(drop=True)


def active_events(events: pd.DataFrame, day: pd.Timestamp, prime: bool = False) -> pd.DataFrame:
    """Events live on `day` (Prime members can shop the early-access day too)."""
    live = (events.start_date <= day) & (events.end_date >= day)
    if prime:
        early = events.prime_early_access_date.notna() & (events.prime_early_access_date <= day) & (events.end_date >= day)
        live = live | early
    return events[live]


def covered_products(event, products: pd.DataFrame) -> np.ndarray:
    """True for the products this event discounts."""
    offer = event.categories_on_offer
    if offer == "All":
        return np.ones(len(products), dtype=bool)
    if offer == "Ethnic":
        return (products.usage == "Ethnic").to_numpy()
    if offer == "Casual":
        return (products.usage == "Casual").to_numpy()
    if offer == "Women":
        return (products.gender == "Women").to_numpy()
    if offer == "Gifting":
        return products.article_type.isin(ref.GIFTING_TYPES).to_numpy()
    if offer == "Winter":
        return (products.article_type.isin(ref.WINTER_TYPES) | (products.season == "Winter")).to_numpy()
    if offer == "Summer":
        return (products.article_type.isin(ref.SUMMER_TYPES) | (products.season == "Summer")).to_numpy()
    return np.zeros(len(products), dtype=bool)


def demand_factor(events: pd.DataFrame, day: pd.Timestamp) -> float:
    """How busy the shop is today compared with an ordinary day."""
    factor = WEEKDAY_FACTOR[day.weekday()] * MONTH_FACTOR[day.month]
    live = active_events(events, day)
    if len(live):
        factor *= float(live.demand_uplift.max())
        return factor
    # Run-up: within an event's run-up days, browsing climbs towards the event.
    upcoming = events[(events.start_date > day) & (events.start_date - pd.to_timedelta(events.run_up_days, unit="D") <= day)]
    if len(upcoming):
        days_left = (upcoming.start_date - day).dt.days
        closeness = 1 - days_left / upcoming.run_up_days.clip(lower=1)
        factor *= 1 + RUN_UP_LIFT * float(closeness.max())
    # Post-sale dip after big events.
    recent = events[(events.end_date < day) & (events.end_date >= day - pd.Timedelta(days=POST_EVENT_DIP_DAYS))
                    & events.event_type.isin(["Mega Sale", "Clearance"])]
    if len(recent):
        factor *= POST_EVENT_DIP
    return factor
