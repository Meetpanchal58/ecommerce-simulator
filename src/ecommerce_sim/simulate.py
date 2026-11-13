"""Runs the shop one day at a time and writes every table.

Order of events within a simulated day:
    1. new campaigns start; today's prices are set (sale events, clearance)
    2. new products arrive (initial stock); purchase orders and returns come in
    3. exchanges due today are shipped
    4. ads, affiliates and CRM messages bring visitors
    5. visitors browse, sign up, add to cart and order
    6. Prime sign-ups; a few accounts are deleted
    7. platform-reported results are filled in for marketing; stock is counted and
       purchase orders are raised for SKUs running low

`load` starts a fresh shop on the start date. `increment` continues from the last
simulated day up to today and does nothing if the data is already up to date.
Both give exactly the same data for the same days.
"""
import time
from collections import defaultdict

import numpy as np
import pandas as pd

from . import catalog as cat
from . import reference as ref
from .calendar import active_events, build_events, demand_factor, published_events
from .crm import CRM
from .customers import Population
from .inventory import Inventory
from .marketing import PLATFORM_OVER_REPORTING, Marketing
from .orders import OrderBook
from .pricing import Pricing
from .promotions import build_promotions
from .randomness import stream
from .sessions import Traffic
from .store import Store
from .taste import TasteModel

MONTHLY_TABLES = ["clickstream", "impressions", "auth_events", "crm_sends", "marketing_spend",
                  "inventory_history", "marketing_attribution"]
ATTRIBUTION_WINDOW = pd.Timedelta(days=30)
DECAY_HALF_LIFE_DAYS = 7.0


def new_moves() -> dict:
    return {"received": 0, "sold": 0, "restocked": 0, "damaged": 0}


class World:
    """Everything the simulator remembers between days (and between runs)."""

    def __init__(self, settings):
        self.settings = settings
        self.products = cat.build_products(settings)
        self.sellers = cat.build_sellers(settings, self.products)
        self.skus = cat.build_skus(settings, self.products)
        self.warehouses = cat.build_warehouses()
        self.agents = cat.build_agents(settings)
        self.events = build_events(settings)
        self.event_start = dict(zip(self.events.event_id, self.events.start_date))
        self.promotions = build_promotions(settings, self.events)
        seller_cancel = self.sellers.set_index("seller_id").cancellation_rate
        self.catalog = {
            "product_id": self.products.product_id.to_numpy(), "seller_id": self.products.seller_id.to_numpy(),
            "mrp": self.products.mrp.to_numpy(), "unit_cost": self.products.unit_cost.to_numpy(),
            "gst_rate": self.products.gst_rate.to_numpy(), "category": self.products.category.to_numpy(),
            "quality": self.products.quality.to_numpy(), "product_name": self.products.product_name.to_numpy(),
            "seller_cancel": seller_cancel.reindex(self.products.seller_id).to_numpy(),
            "position": {pid: i for i, pid in enumerate(self.products.product_id)},
        }
        self.taste = TasteModel(self.products)
        self.pricing = Pricing(settings, self.products)
        self.inventory = Inventory(settings, self.products, self.skus, self.sellers)
        self.population = Population()
        self.orders = OrderBook(settings)
        for event in self.events.itertuples(index=False):
            if any(event.name.startswith(name) for name in ref.COURIER_SLOWDOWN_EVENTS):
                self.orders.slow_days.update(pd.date_range(event.end_date - pd.Timedelta(days=1), event.end_date))
        self.marketing = Marketing(settings)
        self.crm = CRM(settings)
        self.traffic = Traffic(settings, self.products, self.skus, self.taste)
        self.last_day = None
        self.buffers = defaultdict(list)       # monthly table -> list of DataFrames not yet written
        self.today_orders = []
        self.attribution_rows = []

    # ------------------------------------------------------------------ actions used by visits
    def sign_up(self, rng, person: dict, at: pd.Timestamp, session: dict) -> str:
        customer_id = self.population.sign_up(rng, person, at, session["traffic_source"], session["campaign_id"],
                                              session["device"])
        touches = person.pop("pending_touches", [])
        if touches:
            self.traffic.touches[customer_id] = touches
        return customer_id

    def place_order(self, rng, at, customer, person, address, cart, session) -> dict:
        order = self.orders.place(rng, at, customer, person, address, cart, self.catalog, self.prices,
                                  self.pricing.current_event, session, self.promotions, self.events_live, self.marketing,
                                  self.inventory, self.moves, self.agents)
        order.update({"at": at, "campaign_id": session["campaign_id"], "region": address["region"]})
        self.today_orders.append(order)
        self._attribute(order, customer["customer_id"])
        if session["campaign_id"] and self.marketing.by_id[session["campaign_id"]]["channel_group"] == "CRM":
            self.crm.record_conversion(customer["customer_id"], session["campaign_id"], order["order_id"])
        return order

    def payment_issue(self, rng, customer: dict, at: pd.Timestamp) -> None:
        self.orders.add_ticket(rng, "Payment Issue", at + pd.Timedelta(hours=1), customer, self.agents)

    def _attribute(self, order: dict, customer_id: str) -> None:
        """Marketing touchpoints in the 30 days before the order, credited four ways."""
        at = order["at"]
        touches = [t for t in self.traffic.touches.get(customer_id, []) if at - ATTRIBUTION_WINDOW <= t[0] <= at]
        self.traffic.touches[customer_id] = touches
        revenue = round(order["revenue"], 2)
        if not touches:
            self.attribution_rows.append((order["order_id"], customer_id, at, 1, pd.NaT, None, "Direct/Organic",
                                          1.0, 1.0, 1.0, 1.0, revenue))
            return
        ages = np.array([(at - t[0]).total_seconds() / 86400 for t in touches])
        decay = 0.5 ** (ages / DECAY_HALF_LIFE_DAYS)
        decay = decay / decay.sum()
        n = len(touches)
        for k, (touch_at, campaign_id, group) in enumerate(touches):
            self.attribution_rows.append((order["order_id"], customer_id, at, k + 1, touch_at, campaign_id, group,
                                          1.0 if k == n - 1 else 0.0, 1.0 if k == 0 else 0.0, round(1 / n, 4),
                                          round(float(decay[k]), 4), revenue))

    # ------------------------------------------------------------------ one day
    def simulate_day(self, day: pd.Timestamp) -> None:
        rng = stream(self.settings.seed, "world.day", day)
        self.today_orders = []
        demand = demand_factor(self.events, day)
        self.sale_today = len(active_events(self.events, day)) > 0
        self.sale_today_prime = len(active_events(self.events, day, prime=True)) > 0
        self.events_live = active_events(self.events, day)
        self.marketing.create_campaigns(day, self.events, self.promotions)
        self.prices = self.pricing.advance(day, self.events)

        self.moves = defaultdict(new_moves)
        self.demand = np.zeros(len(self.inventory.sku_ids))
        self.inventory.stock_new_launches(day)
        self.inventory.receive(day, self.moves)
        self.orders.process_exchanges(rng, day, self.inventory, self.moves)

        self.traffic.prepare_day(day, self.prices, self.inventory.on_hand)
        spend_rows, landings = self.marketing.deliver(day, self.events, demand)
        crm_clicks = self.crm.send(self, day)
        self.traffic.carts_abandoned = [c for c in self.traffic.carts_abandoned
                                        if c[1] >= day - pd.Timedelta(days=1)]
        self.traffic.run_day(self, day, demand, landings, crm_clicks)

        self._prime_and_deletions(rng, day)
        spend = self._fill_platform_results(rng, day, spend_rows)
        self.inventory.close_day(day, self.moves, self.demand)

        rows = self.traffic.take_rows()
        rows["crm_sends"] = self.crm.take_rows()
        rows["marketing_spend"] = spend
        history = self.inventory.history_rows
        self.inventory.history_rows = []
        rows["inventory_history"] = pd.DataFrame(history, columns=[
            "date", "sku_id", "product_id", "warehouse_id", "opening_stock", "received", "sold",
            "returned_restocked", "damaged", "closing_stock", "demand_units", "lost_sales_units", "stock_status"])
        rows["marketing_attribution"] = pd.DataFrame(self.attribution_rows, columns=[
            "order_id", "customer_id", "order_at", "touch_number", "touch_at", "campaign_id", "channel_group",
            "credit_last_click", "credit_first_click", "credit_linear", "credit_time_decay", "order_revenue"])
        self.attribution_rows = []
        for name, frame in rows.items():
            if not frame.empty:
                self.buffers[name].append(frame)
        self.last_day = day

    def _prime_and_deletions(self, rng, day: pd.Timestamp) -> None:
        member_days = len(active_events(self.events, day + pd.Timedelta(days=3)).query("name.str.startswith('Mid-Year')")) > 0
        for person in self.population.profiles:
            customer_id = person["customer_id"]
            row = self.population.row(customer_id)
            if row["account_status"] == "Deleted":
                continue
            if not row["is_prime"] and self.orders.orders_of[customer_id] > 0:
                if rng.random() < person["prime_propensity"] * 0.003 * (6 if member_days else 1):
                    self.population.join_prime(customer_id, day)
            if rng.random() < 0.00003:
                row["account_status"] = "Deleted"

    def _fill_platform_results(self, rng, day: pd.Timestamp, spend_rows: list) -> pd.DataFrame:
        """Platform-reported conversions, affiliate commissions and CRM costs, by hour."""
        index = {(row[0], row[1], row[2]): row for row in spend_rows}
        for order in self.today_orders:
            campaign = self.marketing.by_id.get(order["campaign_id"])
            if campaign is None or campaign["channel_group"] == "CRM":
                continue
            hour = order["at"].floor("h")
            region = "All" if campaign["channel_group"] == "Affiliate" else order["region"]
            key = (hour, campaign["campaign_id"], region)
            if key not in index:
                index[key] = [hour, campaign["campaign_id"], region, 0.0, 0, 0, 0, 0.0]
            row = index[key]
            factor = PLATFORM_OVER_REPORTING[campaign["channel_group"]] * float(rng.lognormal(0, 0.08))
            row[6] += factor
            row[7] += order["revenue"] * factor
            if campaign["channel_group"] == "Affiliate":
                row[3] += sum(line["affiliate_commission"] for line in order["lines"])
        for row in index.values():
            campaign = self.marketing.by_id[row[1]]
            if campaign["channel_group"] == "Affiliate" and campaign["payout_model"] == "CPC":
                row[3] = row[5] * float(campaign["payout_rate"])
        crm = self.buffers_today_crm(day)
        for (hour, campaign_id), (cost, delivered, clicked) in crm.items():
            index[(hour, campaign_id, "All")] = [hour, campaign_id, "All", round(cost, 2), delivered, clicked, 0, 0.0]
        frame = pd.DataFrame(list(index.values()), columns=["date_hour", "campaign_id", "region", "spend",
                                                             "impressions", "clicks", "platform_conversions",
                                                             "platform_revenue"])
        frame["platform_conversions"] = frame.platform_conversions.round().astype(int)
        frame["platform_revenue"] = frame.platform_revenue.round(2)
        frame["spend"] = frame.spend.round(2)
        return frame.sort_values(["date_hour", "campaign_id", "region"]).reset_index(drop=True)

    def buffers_today_crm(self, day) -> dict:
        totals = {}
        for row in self.crm.rows:
            if row[4] != "treatment":
                continue
            key = (row[5].floor("h"), row[1])
            cost, delivered, clicked = totals.get(key, (0.0, 0, 0))
            totals[key] = (cost + row[11], delivered + int(row[6]), clicked + int(pd.notna(row[8])))
        return totals

    # ------------------------------------------------------------------ writing
    def flush(self, store: Store) -> None:
        """Write buffered event rows into their monthly files."""
        for name, frames in self.buffers.items():
            if not frames:
                continue
            frame = pd.concat(frames, ignore_index=True)
            time_column = {"clickstream": "event_at", "impressions": "shown_at", "auth_events": "event_at",
                           "crm_sends": "sent_at", "marketing_spend": "date_hour", "inventory_history": "date",
                           "marketing_attribution": "order_at"}[name]
            months = pd.to_datetime(frame[time_column])
            if name == "crm_sends":       # control-group rows have no send time; use their day
                months = months.fillna(pd.Timestamp(self.last_day))
            month_key = months.dt.strftime("%Y-%m")
            for month, part in frame.groupby(month_key, sort=True):
                store.append_month(name, month, part)
        self.buffers = defaultdict(list)

    def publish(self, store: Store) -> None:
        """Write every whole table as it looks at the end of the last simulated day."""
        today = self.last_day
        launched = self.products.launch_date <= today
        products = self.products[launched].drop(columns=["quality"])
        products["is_active"] = products.discontinue_date.isna() | (products.discontinue_date > today)
        products["discontinue_date"] = products.discontinue_date.where(products.discontinue_date <= today)
        store.write("product_master", products)
        store.write("product_skus", self.skus[self.skus.product_id.isin(products.product_id)])
        sellers = self.sellers[self.sellers.onboarding_date <= today]
        store.write("sellers", sellers)
        store.write("warehouses", self.warehouses)
        store.write("agents", self.agents)
        events = published_events(self.events, today)
        store.write("sale_events", events)
        promos = self.promotions[self.promotions.event_id.isna() | self.promotions.event_id.isin(events.event_id)]
        store.write("promotions", promos)
        for name, frame in {**self.marketing.tables(today), **self.population.tables(today),
                            **self.orders.tables(today), **self.inventory.tables(today)}.items():
            store.write(name, frame)
        history = self.pricing.history()
        history = history[history.valid_from <= today]
        store.write("price_history", history)
        store.write_truth("customer_taste", self.population.truth())
        store.write_truth("product_quality", self.products[["product_id", "quality"]])


def run(settings, mode: str, progress=print) -> dict:
    """mode = 'load' (start over) or 'increment' (continue up to today)."""
    store = Store(settings.data_dir)
    end = settings.end
    if mode == "load":
        store.prepare(fresh=True)
        world = World(settings)
        first = settings.start
    elif mode == "increment":
        store.prepare(fresh=False)
        state = store.load_state()
        if state is None:
            raise RuntimeError("No existing data found. Run `ecommerce-sim load` first.")
        world = state["world"]
        if (world.settings.seed, world.settings.start_date) != (settings.seed, settings.start_date):
            raise RuntimeError("Saved data used a different seed or start date; run `ecommerce-sim load`.")
        world.settings = settings
        first = world.last_day + pd.Timedelta(days=1)
        if first > end:
            progress(f"Already up to date (last simulated day {world.last_day:%Y-%m-%d}). Nothing to do.")
            return {"days": 0, "last_day": world.last_day}
    else:
        raise ValueError("mode must be 'load' or 'increment'")
    if first > end:
        raise ValueError(f"Start date {first:%Y-%m-%d} is after today {end:%Y-%m-%d}.")

    days = pd.date_range(first, end, freq="D")
    progress(f"Simulating {len(days):,} days: {days[0]:%Y-%m-%d} -> {days[-1]:%Y-%m-%d}")
    started = time.perf_counter()
    for number, day in enumerate(days, 1):
        world.simulate_day(day)
        month_ends = day == days[-1] or (day + pd.Timedelta(days=1)).day == 1
        if month_ends:
            world.flush(store)
            progress(f"  {day:%Y-%m}: {len(world.population):,} customers, {world.orders.next_order - 1:,} orders "
                     f"({time.perf_counter() - started:.0f}s)")
    world.publish(store)
    store.save_state({"world": world})
    return {"days": len(days), "last_day": world.last_day}
