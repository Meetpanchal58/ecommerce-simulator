"""Analysis tables built from the raw tables (`ecommerce-sim derive`).

These are not stored by the "shop": analysts and data scientists build them. Each is
computed point-in-time, using only what was known at its snapshot date, so they are
safe to use for modelling (no leakage from the future).

    derived/customer_monthly_features   one row per customer per month start
    derived/churn_labels                 did the customer order in the 90 days after the snapshot?
    derived/product_affinity             products bought / viewed together (with lift)
    derived/mmm_weekly                   weekly revenue next to weekly spend per channel
"""
import pandas as pd

from .store import Store

CHURN_WINDOW_DAYS = 90


def _sales_known_at(sales: pd.DataFrame, snapshot: pd.Timestamp) -> pd.DataFrame:
    """Sale lines placed before the snapshot and not cancelled before it."""
    placed = sales[(sales.placed_at < snapshot) & (sales.line_type == "Sale")]
    cancelled = placed.cancelled_at.notna() & (placed.cancelled_at < snapshot)
    return placed[~cancelled]


def customer_monthly_features(store: Store) -> pd.DataFrame:
    customers = store.read("customers", columns=["customer_id", "signup_at", "is_prime", "prime_start_date"])
    sales = store.read("sales", columns=["customer_id", "order_id", "line_type", "placed_at", "cancelled_at",
                                         "net_amount", "return_requested_at"])
    clicks = store.read("clickstream", columns=["customer_id", "session_id", "event_at"]).dropna(subset=["customer_id"])
    sessions = clicks.groupby(["customer_id", "session_id"]).event_at.min().reset_index()
    contacts = store.read("support_contacts", columns=["customer_id", "contact_at"])
    end = sales.placed_at.max()
    snapshots = pd.date_range(customers.signup_at.min().normalize() + pd.offsets.MonthBegin(1), end, freq="MS")
    rows = []
    for snapshot in snapshots:
        known = _sales_known_at(sales, snapshot)
        members = customers[customers.signup_at < snapshot]
        recent = known[known.placed_at >= snapshot - pd.Timedelta(days=90)]
        by_customer = known.groupby("customer_id")
        frame = pd.DataFrame({"customer_id": members.customer_id})
        frame["snapshot_date"] = snapshot
        frame["tenure_days"] = (snapshot - members.signup_at).dt.days.to_numpy()
        frame["orders_total"] = frame.customer_id.map(by_customer.order_id.nunique()).fillna(0).astype(int)
        frame["revenue_total"] = frame.customer_id.map(by_customer.net_amount.sum()).fillna(0.0)
        frame["days_since_last_order"] = (snapshot - frame.customer_id.map(by_customer.placed_at.max())).dt.days
        frame["orders_90d"] = frame.customer_id.map(recent.groupby("customer_id").order_id.nunique()).fillna(0).astype(int)
        frame["revenue_90d"] = frame.customer_id.map(recent.groupby("customer_id").net_amount.sum()).fillna(0.0)
        returns = known[known.return_requested_at.notna() & (known.return_requested_at < snapshot)
                        & (known.return_requested_at >= snapshot - pd.Timedelta(days=90))]
        frame["returns_90d"] = frame.customer_id.map(returns.groupby("customer_id").size()).fillna(0).astype(int)
        visits = sessions[(sessions.event_at < snapshot) & (sessions.event_at >= snapshot - pd.Timedelta(days=30))]
        frame["sessions_30d"] = frame.customer_id.map(visits.groupby("customer_id").size()).fillna(0).astype(int)
        tickets = contacts[(contacts.contact_at < snapshot) & (contacts.contact_at >= snapshot - pd.Timedelta(days=90))]
        frame["support_contacts_90d"] = frame.customer_id.map(tickets.groupby("customer_id").size()).fillna(0).astype(int)
        prime_since = members.set_index("customer_id").prime_start_date
        frame["is_prime"] = frame.customer_id.map(prime_since).lt(snapshot).fillna(False).to_numpy()
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def churn_labels(features: pd.DataFrame, sales: pd.DataFrame) -> pd.DataFrame:
    """churned = no order in the 90 days after the snapshot (only for snapshots with a full window)."""
    last_day = sales.placed_at.max().normalize()
    usable = features[features.snapshot_date + pd.Timedelta(days=CHURN_WINDOW_DAYS) <= last_day]
    usable = usable[usable.orders_total > 0][["customer_id", "snapshot_date"]].copy()
    orders = sales[sales.line_type == "Sale"][["customer_id", "placed_at"]]
    merged = usable.merge(orders, on="customer_id", how="left")
    in_window = (merged.placed_at >= merged.snapshot_date) & \
                (merged.placed_at < merged.snapshot_date + pd.Timedelta(days=CHURN_WINDOW_DAYS))
    bought = merged[in_window].groupby(["customer_id", "snapshot_date"]).size()
    usable["label_window_end"] = usable.snapshot_date + pd.Timedelta(days=CHURN_WINDOW_DAYS)
    key = pd.MultiIndex.from_frame(usable[["customer_id", "snapshot_date"]])
    usable["churned_90d"] = ~key.isin(bought.index)
    return usable.reset_index(drop=True)


def product_affinity(store: Store, top_n: int = 20) -> pd.DataFrame:
    sales = store.read("sales", columns=["order_id", "product_id", "line_type"])
    sales = sales[sales.line_type == "Sale"]
    views = store.read("clickstream", columns=["session_id", "product_id", "event_type"])
    views = views[views.event_type == "pdp_view"].dropna(subset=["product_id"])

    def pairs(frame: pd.DataFrame, basket: str, kind: str) -> pd.DataFrame:
        items = frame[[basket, "product_id"]].drop_duplicates()
        size = items.groupby(basket).product_id.transform("size")
        items = items[(size > 1) & (size <= 15)]
        joined = items.merge(items, on=basket, suffixes=("", "_related"))
        joined = joined[joined.product_id != joined.product_id_related]
        counts = joined.groupby(["product_id", "product_id_related"]).size().rename("together").reset_index()
        baskets = items[basket].nunique()
        frequency = items.groupby("product_id")[basket].nunique()
        counts["lift"] = (counts.together * baskets / (counts.product_id.map(frequency)
                                                        * counts.product_id_related.map(frequency))).round(3)
        counts["affinity_type"] = kind
        return counts.rename(columns={"product_id_related": "related_product_id"})

    both = pd.concat([pairs(sales, "order_id", "co_purchase"), pairs(views, "session_id", "co_view")])
    both = both.sort_values(["product_id", "affinity_type", "together", "lift"], ascending=[True, True, False, False])
    return both.groupby(["product_id", "affinity_type"]).head(top_n).reset_index(drop=True)


def mmm_weekly(store: Store) -> pd.DataFrame:
    """Weekly realised revenue next to weekly spend by channel (for marketing-mix models)."""
    sales = store.read("sales", columns=["placed_at", "net_amount", "line_type", "cancelled_at", "rto_at"])
    sales = sales[(sales.line_type == "Sale") & sales.cancelled_at.isna() & sales.rto_at.isna()]
    weekly_revenue = sales.groupby(sales.placed_at.dt.to_period("W-SUN").dt.start_time).net_amount.sum()
    spend = store.read("marketing_spend", columns=["date_hour", "campaign_id", "spend"])
    campaigns = store.read("campaigns", columns=["campaign_id", "channel"])
    spend = spend.merge(campaigns, on="campaign_id")
    spend["week_start"] = spend.date_hour.dt.to_period("W-SUN").dt.start_time
    by_channel = spend.pivot_table(index="week_start", columns="channel", values="spend", aggfunc="sum").fillna(0)
    by_channel.columns = [f"spend_{c.lower().replace(' ', '_')}" for c in by_channel.columns]
    events = store.read("sale_events", columns=["start_date", "end_date", "event_type"])
    events = events[events.event_type != "Payday"]
    sale_dates = set()
    for event in events.itertuples(index=False):
        sale_dates.update(pd.date_range(event.start_date, event.end_date))
    frame = by_channel.join(weekly_revenue.rename("revenue"), how="outer").fillna(0.0)
    frame["sale_days"] = [sum((week + pd.Timedelta(days=d)) in sale_dates for d in range(7)) for week in frame.index]
    frame.index.name = "week_start"
    return frame.reset_index()


def derive_all(data_dir) -> None:
    store = Store(data_dir)
    out = store.root / "derived"
    out.mkdir(exist_ok=True)
    print("Building customer monthly features ...")
    features = customer_monthly_features(store)
    features.to_parquet(out / "customer_monthly_features.parquet", index=False)
    print("Building churn labels ...")
    sales = store.read("sales", columns=["customer_id", "placed_at", "line_type"])
    churn_labels(features, sales).to_parquet(out / "churn_labels.parquet", index=False)
    print("Building product affinity ...")
    product_affinity(store).to_parquet(out / "product_affinity.parquet", index=False)
    print("Building weekly marketing-mix table ...")
    mmm_weekly(store).to_parquet(out / "mmm_weekly.parquet", index=False)
    print(f"Done: tables in {out}")

