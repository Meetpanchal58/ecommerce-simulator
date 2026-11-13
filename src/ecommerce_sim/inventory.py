"""Stock for every SKU: purchase orders in, sales out, returns and cancellations back.

Daily cycle for each SKU:
    1. goods from purchase orders due today arrive (some units fail quality checks);
    2. orders take stock; cancelled / returned-to-sender / returned items come back
       on the day that happens, damaged returns are written off;
    3. at the end of the day, SKUs at or below their reorder point get a new
       purchase order, sized to cover expected demand until the next delivery.

Published tables:
    purchase_orders    one row per PO (ordered and received quantities in one row)
    inventory_history  one row per SKU per day on which its stock moved
    inventory_live     today's stock per SKU
"""
from collections import defaultdict

import numpy as np
import pandas as pd

from .randomness import stream

COVER_DAYS = 21             # a purchase order covers about three weeks of demand
SAFETY_DAYS = 3
MIN_ORDER = 6
DEMAND_SMOOTHING = 0.08     # weight of today's demand in the running average


class Inventory:
    def __init__(self, settings, products: pd.DataFrame, skus: pd.DataFrame, sellers: pd.DataFrame):
        self.settings = settings
        rng = stream(settings.seed, "inventory.setup")
        seller = sellers.set_index("seller_id")
        product_row = products.set_index("product_id")
        self.sku_ids = skus.sku_id.to_numpy()
        self.position = {sku: i for i, sku in enumerate(self.sku_ids)}
        self.product_ids = skus.product_id.to_numpy()
        self.seller_ids = product_row.loc[self.product_ids, "seller_id"].to_numpy()
        self.warehouse = seller.loc[self.seller_ids, "home_warehouse_id"].to_numpy()
        self.lead_time = seller.loc[self.seller_ids, "lead_time_days"].to_numpy()
        self.unit_cost = product_row.loc[self.product_ids, "unit_cost"].to_numpy()
        self.launch = pd.to_datetime(product_row.loc[self.product_ids, "launch_date"]).to_numpy()
        self.discontinue = pd.to_datetime(product_row.loc[self.product_ids, "discontinue_date"]).to_numpy()
        n = len(self.sku_ids)
        # Middle sizes sell more, so they start with more stock.
        size_weight = skus["size"].map({"XS": 0.5, "S": 0.9, "M": 1.3, "L": 1.2, "XL": 0.8, "XXL": 0.45,
                                        "6": 0.6, "7": 0.9, "8": 1.2, "9": 1.2, "10": 0.9, "11": 0.5,
                                        "Free Size": 2.2}).fillna(1.0).to_numpy()
        # The buyer's first forecast is often wrong (popular items get under-stocked).
        self.expected_daily = 0.005 * size_weight * rng.lognormal(0, 0.6, n)
        self.on_hand = np.zeros(n, dtype=np.int64)
        self.on_order = np.zeros(n, dtype=np.int64)
        self.stocked = np.zeros(n, dtype=bool)
        self.purchase_orders = []                    # full truth for every PO (dicts)
        self.arrivals = defaultdict(list)            # day -> PO numbers arriving that day
        self.returns_in = defaultdict(list)          # day -> (sku position, units, kind)
        self.history_rows = []
        self.next_po = 1

    # ------------------------------------------------------------------ purchase orders
    def _raise_po(self, rng, i: int, created: pd.Timestamp, quantity: int, initial: bool, arrive_by=None) -> None:
        lead = int(self.lead_time[i])
        expected = created + pd.Timedelta(days=lead)
        if arrive_by is not None:
            arrival = arrive_by
        else:
            arrival = created + pd.Timedelta(days=max(1, lead + int(rng.integers(-1, 4))))
        short = rng.random() < 0.12                      # some deliveries arrive short
        received = int(round(quantity * (rng.uniform(0.75, 0.95) if short else 1.0)))
        rejected = int(rng.binomial(received, 0.015))    # units failing the quality check
        number = self.next_po
        self.next_po += 1
        self.purchase_orders.append({
            "po_id": f"PO{number:08d}", "sku_id": self.sku_ids[i], "product_id": self.product_ids[i],
            "seller_id": self.seller_ids[i], "warehouse_id": self.warehouse[i], "po_type": "Initial" if initial else "Replenishment",
            "created_at": created, "ordered_qty": int(quantity), "unit_cost": float(self.unit_cost[i]),
            "expected_at": expected, "received_at": arrival, "received_qty": received, "rejected_qty": rejected,
        })
        self.on_order[i] += quantity
        self.arrivals[arrival.normalize()].append(number - 1)

    def stock_new_launches(self, day: pd.Timestamp) -> None:
        """Initial stock for SKUs launching today (or already live when the shop opens)."""
        rng = stream(self.settings.seed, "inventory.launch", day)
        due = ~self.stocked & (self.launch <= np.datetime64(day))
        for i in np.flatnonzero(due):
            quantity = max(MIN_ORDER, int(rng.poisson(self.expected_daily[i] * 30)) + 3)
            created = day - pd.Timedelta(days=int(self.lead_time[i]) + 2)
            self._raise_po(rng, i, created, quantity, initial=True, arrive_by=day)
            self.stocked[i] = True

    # ------------------------------------------------------------------ daily movements
    def receive(self, day: pd.Timestamp, moves: dict) -> None:
        for number in self.arrivals.pop(day, []):
            po = self.purchase_orders[number]
            i = self.position[po["sku_id"]]
            good = po["received_qty"] - po["rejected_qty"]
            self.on_hand[i] += good
            self.on_order[i] -= po["ordered_qty"]
            moves[i]["received"] += good
        for i, units, kind in self.returns_in.pop(day, []):
            if kind == "damaged":
                moves[i]["damaged"] += units
            else:
                self.on_hand[i] += units
                moves[i]["restocked"] += units

    def available(self, i: int) -> int:
        return int(self.on_hand[i])

    def take(self, i: int, units: int, moves: dict) -> None:
        self.on_hand[i] -= units
        moves[i]["sold"] += units

    def schedule_back(self, day: pd.Timestamp, i: int, units: int, kind: str) -> None:
        """Units coming back on a later day: kind 'restock' or 'damaged'."""
        self.returns_in[pd.Timestamp(day).normalize()].append((i, units, kind))

    def close_day(self, day: pd.Timestamp, moves: dict, demand: np.ndarray, lost: np.ndarray) -> None:
        """Record today's movements, update demand estimates and raise purchase orders."""
        rng = stream(self.settings.seed, "inventory.reorder", day)
        self.expected_daily = (1 - DEMAND_SMOOTHING) * self.expected_daily + DEMAND_SMOOTHING * demand
        for i in np.flatnonzero(lost):
            _ = moves[i]                           # creates an empty entry so the SKU still gets a row
        for i, move in moves.items():
            closing = int(self.on_hand[i])
            opening = closing - move["received"] - move["restocked"] + move["sold"]
            missed = int(lost[i])
            status = "Out of Stock" if closing <= 0 else ("Low" if closing <= self.reorder_point(i) else "Healthy")
            self.history_rows.append((day, self.sku_ids[i], self.product_ids[i], self.warehouse[i], opening,
                                      move["received"], move["sold"], move["restocked"], move["damaged"], closing,
                                      int(demand[i]), missed, status))
        selling = self.stocked & (np.isnat(self.discontinue) | (self.discontinue > np.datetime64(day + pd.Timedelta(days=45))))
        reorder_point = self.expected_daily * (self.lead_time + SAFETY_DAYS)
        need = selling & ((self.on_hand + self.on_order) <= reorder_point)
        for i in np.flatnonzero(need):
            quantity = max(MIN_ORDER, int(np.ceil(self.expected_daily[i] * (self.lead_time[i] + COVER_DAYS))))
            self._raise_po(rng, i, day + pd.Timedelta(hours=18), quantity, initial=False)

    def reorder_point(self, i: int) -> int:
        return int(np.ceil(self.expected_daily[i] * (self.lead_time[i] + SAFETY_DAYS)))

    # ------------------------------------------------------------------ tables
    def tables(self, today: pd.Timestamp) -> dict[str, pd.DataFrame]:
        end_of_today = today + pd.Timedelta(days=1)
        pos = pd.DataFrame(self.purchase_orders)
        if not pos.empty:
            pos = pos[pos.created_at < end_of_today].copy()
            arrived = pos.received_at < end_of_today
            pos["po_status"] = np.where(~arrived, "Open",
                                        np.where(pos.received_qty < pos.ordered_qty, "Short Received", "Received"))
            for column in ("received_at", "received_qty", "rejected_qty"):
                pos[column] = pos[column].where(arrived)
        live = pd.DataFrame({
            "sku_id": self.sku_ids, "product_id": self.product_ids, "warehouse_id": self.warehouse,
            "on_hand_qty": self.on_hand, "inbound_qty": self.on_order,
            "reorder_point": [self.reorder_point(i) for i in range(len(self.sku_ids))],
            "updated_at": today,
        })[self.stocked]
        return {"purchase_orders": pos, "inventory_live": live}
