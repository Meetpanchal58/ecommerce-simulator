"""Daily selling prices, recorded as a price history.

Price of a product on a day = list price (MRP)
    x (1 - everyday markdown)                      set per product
    x cost-change factor                           one-off price rise on 1 Feb 2025
    x (1 - event discount)                         only on days an event covering it is live
    x (1 - clearance discount)                     last 30 days before a product is discontinued

`price_history` keeps one row per period with the same price (valid_from .. valid_to),
the usual "slowly changing dimension" layout: a new row only when the price changes.
"""
import numpy as np
import pandas as pd

from .calendar import active_events, covered_products
from .randomness import stream

PRICE_RISE_DATE = pd.Timestamp("2025-02-01")
CLEARANCE_DAYS = 30
CLEARANCE_DISCOUNT = 0.30


class Pricing:
    def __init__(self, settings, products: pd.DataFrame):
        rng = stream(settings.seed, "pricing.base")
        n = len(products)
        self.seed = settings.seed
        self.products = products
        self.mrp = products.mrp.to_numpy(dtype=float)
        self.cost = products.unit_cost.to_numpy(dtype=float)
        self.markdown = np.round(rng.choice([0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30], n,
                                            p=[0.18, 0.14, 0.18, 0.18, 0.14, 0.10, 0.08]), 2)
        self.rises = rng.random(n) < 0.40
        self.rise_size = rng.uniform(0.06, 0.11, n)
        self.event_discounts = {}          # event_id -> per-product discount (made once per event)
        self.current = np.full(n, np.nan)  # today's price (NaN = not launched yet)
        self.current_reason = np.array([""] * n, dtype=object)
        self.current_event = np.array([None] * n, dtype=object)
        self.open_from = np.array([pd.NaT] * n, dtype=object)
        self.closed_rows = []              # finished price periods

    def _event_discount(self, event) -> np.ndarray:
        if event.event_id not in self.event_discounts:
            rng = stream(self.seed, f"pricing.event.{event.event_id}")
            covered = covered_products(event, self.products)
            spread = rng.normal(event.avg_extra_discount, 0.05, len(self.products))
            self.event_discounts[event.event_id] = np.where(covered, np.clip(spread, 0.03, 0.6), 0.0)
        return self.event_discounts[event.event_id]

    def prices_for(self, day: pd.Timestamp, events: pd.DataFrame):
        """Price, reason and event for every product on `day`."""
        launched = (self.products.launch_date <= day).to_numpy()
        stopped = (self.products.discontinue_date.notna() & (self.products.discontinue_date <= day)).to_numpy()
        price = self.mrp * (1 - self.markdown)
        reason = np.where(self.markdown > 0, "Everyday Markdown", "List Price").astype(object)
        if day >= PRICE_RISE_DATE:
            price = np.where(self.rises, np.minimum(self.mrp, price * (1 + self.rise_size)), price)
            reason = np.where(self.rises, "Cost Change", reason)
        event_ids = np.array([None] * len(price), dtype=object)
        best = np.zeros(len(price))
        for event in active_events(events, day).itertuples(index=False):
            discount = self._event_discount(event)
            better = discount > best
            best = np.where(better, discount, best)
            event_ids = np.where(better, event.event_id, event_ids)
        price = np.where(best > 0, price * (1 - best), price)
        reason = np.where(best > 0, "Sale Event", reason)
        days_left = (self.products.discontinue_date - day).dt.days.to_numpy()
        clearing = ~np.isnan(days_left.astype(float)) & (days_left <= CLEARANCE_DAYS) & (days_left > 0)
        price = np.where(clearing, price * (1 - CLEARANCE_DISCOUNT), price)
        reason = np.where(clearing, "Clearance", reason)
        price = np.maximum(price, self.cost * 1.05)            # never sell below cost + 5%
        price = np.floor(price) - 0.0 + np.where(np.floor(price) % 10 == 9, 0, 9 - np.floor(price) % 10)
        price = np.minimum(price, self.mrp)
        price = np.where(launched & ~stopped, price, np.nan)
        return price, reason, event_ids

    def advance(self, day: pd.Timestamp, events: pd.DataFrame) -> np.ndarray:
        """Move to `day`: record price changes and return today's prices."""
        price, reason, event_ids = self.prices_for(day, events)
        was = self.current
        changed = ~((was == price) | (np.isnan(was) & np.isnan(price)))
        for i in np.flatnonzero(changed):
            if not np.isnan(was[i]):
                self._close(i, day - pd.Timedelta(days=1))
            if not np.isnan(price[i]):
                self.open_from[i] = day
        self.current = price
        self.current_reason = np.where(changed, reason, self.current_reason)
        self.current_event = np.where(changed, event_ids, self.current_event)
        return price

    def _close(self, i: int, last_day: pd.Timestamp) -> None:
        self.closed_rows.append(self._row(i, self.open_from[i], last_day))

    def _row(self, i: int, valid_from, valid_to) -> tuple:
        mrp = self.mrp[i]
        price = self.current[i]
        return (self.products.product_id.iat[i], valid_from, valid_to, mrp, price,
                round(1 - price / mrp, 4), self.current_reason[i], self.current_event[i])

    def history(self) -> pd.DataFrame:
        """All closed periods plus the currently open ones (valid_to empty)."""
        open_rows = [self._row(i, self.open_from[i], pd.NaT) for i in np.flatnonzero(~np.isnan(self.current))]
        columns = ["product_id", "valid_from", "valid_to", "mrp", "selling_price", "discount_pct",
                   "price_change_reason", "event_id"]
        frame = pd.DataFrame(self.closed_rows + open_rows, columns=columns)
        return frame.sort_values(["product_id", "valid_from"]).reset_index(drop=True)
