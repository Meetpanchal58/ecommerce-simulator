"""Checks that every table is consistent with every other table.

Each check is a small function returning (passed, detail). Run them all with
`ecommerce-sim validate`; load and increment run them automatically.
"""
import pandas as pd

from .store import Store

CHECKS = []


def check(group: str):
    """Register a check function under a group name."""
    def register(function):
        CHECKS.append((group, function))
        return function
    return register


def unique(frame: pd.DataFrame, column: str):
    duplicates = int(frame[column].duplicated().sum())
    return duplicates == 0, f"{duplicates} duplicate {column}"


def contained(child: pd.Series, parent: pd.Series, label: str):
    missing = int((~child.dropna().isin(set(parent.dropna()))).sum())
    return missing == 0, f"{missing} {label} not found"


# ----------------------------------------------------------------------------- keys
@check("keys")
def keys_are_unique(t):
    for name, column in [("product_master", "product_id"), ("product_skus", "sku_id"), ("sellers", "seller_id"),
                         ("customers", "customer_id"), ("customer_pii", "customer_id"), ("sales", "transaction_id"),
                         ("campaigns", "campaign_id"), ("purchase_orders", "po_id"), ("promotions", "promo_id"),
                         ("sale_events", "event_id"), ("product_reviews", "review_id"),
                         ("support_contacts", "contact_id"), ("clickstream", "event_id"), ("crm_sends", "send_id")]:
        ok, detail = unique(t[name], column)
        if not ok:
            return False, f"{name}: {detail}"
    return True, ""


@check("keys")
def every_reference_exists(t):
    pairs = [
        (t["product_skus"].product_id, t["product_master"].product_id, "SKU products"),
        (t["product_master"].seller_id, t["sellers"].seller_id, "product sellers"),
        (t["sales"].sku_id, t["product_skus"].sku_id, "sold SKUs"),
        (t["sales"].customer_id, t["customers"].customer_id, "order customers"),
        (t["sales"].address_id, t["customer_addresses"].address_id, "order addresses"),
        (t["sales"].campaign_id, t["campaigns"].campaign_id, "order campaigns"),
        (t["sales"].session_id, t["clickstream"].session_id, "order sessions"),
        (t["clickstream"].customer_id, t["customers"].customer_id, "clickstream customers"),
        (t["clickstream"].product_id, t["product_master"].product_id, "clickstream products"),
        (t["purchase_orders"].sku_id, t["product_skus"].sku_id, "PO SKUs"),
        (t["product_reviews"].transaction_id, t["sales"].transaction_id, "reviewed lines"),
        (t["support_contacts"].agent_id, t["agents"].agent_id, "support agents"),
        (t["crm_sends"].campaign_id, t["campaigns"].campaign_id, "CRM campaigns"),
        (t["marketing_spend"].campaign_id, t["campaigns"].campaign_id, "spend campaigns"),
        (t["marketing_attribution"].order_id, t["sales"].order_id, "attributed orders"),
        (t["campaigns"].event_id, t["sale_events"].event_id, "campaign events"),
        (t["price_history"].event_id, t["sale_events"].event_id, "price events"),
    ]
    for child, parent, label in pairs:
        ok, detail = contained(child, parent, label)
        if not ok:
            return False, detail
    return True, ""


# ----------------------------------------------------------------------------- time order
@check("time")
def lifecycle_in_order(t):
    s = t["sales"]
    steps = ["placed_at", "confirmed_at", "shipped_at", "out_for_delivery_at", "delivered_at",
             "return_requested_at", "return_picked_up_at", "return_received_at"]
    for before, after in zip(steps, steps[1:]):
        both = s[before].notna() & s[after].notna()
        bad = int((s.loc[both, after] < s.loc[both, before]).sum())
        if bad:
            return False, f"{bad} lines with {after} before {before}"
    late_return = s.return_requested_at - s.delivered_at > pd.Timedelta(days=8)
    if late_return.any():
        return False, f"{int(late_return.sum())} returns requested after the return window"
    return True, ""


@check("time")
def nothing_happens_before_it_can(t):
    s = t["sales"].merge(t["customers"][["customer_id", "signup_at"]], on="customer_id")
    if (s.placed_at < s.signup_at).any():
        return False, "orders placed before the customer signed up"
    launch = t["product_master"].set_index("product_id").launch_date
    if (s.placed_at.dt.normalize() < s.product_id.map(launch)).any():
        return False, "products sold before launch"
    today = t["_today"]
    for name, column in [("sales", "updated_at"), ("clickstream", "event_at"), ("crm_sends", "sent_at"),
                         ("product_reviews", "reviewed_at"), ("support_contacts", "contact_at")]:
        if (t[name][column] >= today + pd.Timedelta(days=1)).any():
            return False, f"{name}.{column} is in the future"
    return True, ""


# ----------------------------------------------------------------------------- money
@check("money")
def line_amounts_add_up(t):
    s = t["sales"]
    sale = s[s.line_type == "Sale"]
    gross_ok = (sale.gross_amount - sale.unit_price * sale.quantity).abs() < 0.02
    net_ok = (sale.net_amount - (sale.gross_amount - sale.coupon_discount + sale.shipping_fee)).abs() < 0.02
    if not gross_ok.all() or not net_ok.all():
        return False, "gross or net amount does not match price, coupon and shipping"
    if (sale.unit_price > sale.mrp + 0.01).any():
        return False, "selling price above MRP"
    if (s.refund_amount > s.net_amount + 0.01).any():
        return False, "refund larger than the amount paid"
    return True, ""


@check("money")
def sold_price_matches_price_history(t):
    s = t["sales"].loc[t["sales"].line_type == "Sale", ["product_id", "placed_at", "unit_price"]]
    s = s.assign(day=s.placed_at.dt.normalize().astype("datetime64[ns]")).sort_values("day")
    ph = t["price_history"][["product_id", "valid_from", "valid_to", "selling_price"]]
    ph = ph.assign(valid_from=ph.valid_from.astype("datetime64[ns]")).sort_values("valid_from")
    # the price period in force on the day of sale: the latest one that started on or before it
    merged = pd.merge_asof(s, ph, left_on="day", right_on="valid_from", by="product_id")
    covered = merged.valid_from.notna() & (merged.valid_to.isna() | (merged.valid_to >= merged.day))
    if not covered.all():
        return False, f"{int((~covered).sum())} lines without a price period"
    bad = int(((merged.unit_price - merged.selling_price).abs() > 0.01).sum())
    return bad == 0, f"{bad} lines sold at a different price than price_history"


@check("money")
def coupons_were_live(t):
    s = t["sales"].dropna(subset=["coupon_code"])
    promos = t["promotions"]
    merged = s.merge(promos[["code", "start_date", "end_date"]], left_on="coupon_code", right_on="code", how="left")
    day = merged.placed_at.dt.normalize()
    live = (merged.start_date <= day) & (merged.end_date >= day)
    ok = live.groupby(merged.transaction_id).any()
    return bool(ok.all()), f"{int((~ok).sum())} lines used a coupon outside its dates"


# ----------------------------------------------------------------------------- stock
@check("stock")
def stock_never_negative(t):
    if (t["inventory_live"].on_hand_qty < 0).any() or (t["inventory_history"].closing_stock < 0).any():
        return False, "negative stock"
    return True, ""


@check("stock")
def stock_flows_balance(t):
    h = t["inventory_history"]
    balance = h.opening_stock + h.received + h.returned_restocked - h.sold - h.closing_stock
    return bool((balance == 0).all()), f"{int((balance != 0).sum())} SKU-days where stock does not balance"


@check("stock")
def receipts_match_purchase_orders(t):
    po = t["purchase_orders"].dropna(subset=["received_at"])
    received = (po.received_qty - po.rejected_qty).groupby([po.sku_id, po.received_at.dt.normalize()]).sum()
    h = t["inventory_history"]
    booked = h[h.received > 0].set_index(["sku_id", "date"]).received
    joined = pd.concat([received.rename("po"), booked.rename("stock")], axis=1).fillna(0)
    bad = int((joined.po != joined.stock).sum())
    return bad == 0, f"{bad} SKU-days where goods received differ from purchase orders"


@check("stock")
def sold_units_match_sales(t):
    s = t["sales"]
    sold = s.quantity.groupby([s.sku_id, s.placed_at.dt.normalize()]).sum()
    h = t["inventory_history"]
    booked = h[h.sold > 0].set_index(["sku_id", "date"]).sold
    joined = pd.concat([sold.rename("sales"), booked.rename("stock")], axis=1).fillna(0)
    bad = int((joined.sales != joined.stock).sum())
    return bad == 0, f"{bad} SKU-days where units sold differ between sales and inventory"


# ----------------------------------------------------------------------------- behaviour
@check("behaviour")
def every_order_has_its_visit(t):
    c = t["clickstream"]
    purchases = c[c.event_type == "purchase"]
    orders = t["sales"][t["sales"].line_type == "Sale"].order_id.unique()
    missing = set(orders) - set(purchases.order_id)
    return not missing, f"{len(missing)} orders without a purchase event"


@check("behaviour")
def impressions_match_clickstream(t):
    """Impressions are checked one month at a time (they are the biggest table)."""
    c = t["clickstream"]
    month = c.event_at.dt.strftime("%Y-%m")
    for path in t["_impression_months"]:
        imp = pd.read_parquet(path, columns=["page_event_id", "session_id", "product_id", "clicked"])
        this_month = c[month == path.parent.name.removeprefix("month=")]
        ok, detail = contained(imp.page_event_id, this_month.event_id, "impression page views")
        if not ok:
            return False, f"{path.parent.name}: {detail}"
        views = this_month.loc[this_month.event_type == "pdp_view", ["session_id", "product_id"]].drop_duplicates()
        merged = imp[imp.clicked].merge(views, on=["session_id", "product_id"], how="left", indicator=True)
        bad = int((merged._merge == "left_only").sum())
        if bad:
            return False, f"{path.parent.name}: {bad} clicked impressions without a product view"
    return True, ""


@check("behaviour")
def crm_control_group_gets_nothing(t):
    crm = t["crm_sends"]
    control = crm[crm.test_group == "control"]
    if control.sent_at.notna().any() or control.clicked_at.notna().any():
        return False, "control customers received messages"
    share = len(control) / max(len(crm), 1)
    return 0.06 < share < 0.14 or len(crm) < 200, f"control share {share:.1%}"


@check("behaviour")
def attribution_credits_sum_to_one(t):
    a = t["marketing_attribution"]
    totals = a.groupby("order_id")[["credit_last_click", "credit_first_click", "credit_linear", "credit_time_decay"]].sum()
    bad = int(((totals - 1).abs() > 0.01).any(axis=1).sum())
    return bad == 0, f"{bad} orders whose credits do not sum to 1"


@check("behaviour")
def statuses_are_valid(t):
    allowed = {"Placed", "Confirmed", "Shipped", "Out for Delivery", "Delivered", "Return Requested",
               "Return Picked Up", "Returned", "Exchanged", "Refunded", "Cancelled", "Returned to Origin",
               "Undelivered", "Lost"}
    unknown = set(t["sales"].order_status) - allowed
    return not unknown, f"unknown statuses {unknown}"


# ----------------------------------------------------------------------------- run
TABLES = ["product_master", "product_skus", "sellers", "warehouses", "agents", "sale_events", "promotions",
          "campaigns", "marketing_plan", "marketing_spend", "marketing_attribution", "crm_sends",
          "purchase_orders", "inventory_history", "inventory_live", "price_history", "customers", "customer_pii",
          "customer_addresses", "auth_events", "clickstream", "sales", "product_reviews", "support_contacts"]
# The biggest tables are read with only the columns the checks use, to keep memory low.
COLUMNS = {"clickstream": ["event_id", "session_id", "customer_id", "product_id", "event_type", "order_id", "event_at"],
           "crm_sends": ["send_id", "campaign_id", "test_group", "sent_at", "clicked_at"]}


def validate(data_dir, print_results=True) -> bool:
    store = Store(data_dir)
    tables = {name: store.read(name, columns=COLUMNS.get(name)) for name in TABLES}
    tables["_impression_months"] = sorted((store.root / "impressions").glob("month=*/part.parquet"))
    tables["_today"] = pd.Timestamp(tables["inventory_live"].updated_at.max())
    failures = 0
    for group, function in CHECKS:
        try:
            ok, detail = function(tables)
        except Exception as error:          # a crash in a check counts as a failure
            ok, detail = False, f"check crashed: {error!r}"
        failures += 0 if ok else 1
        if print_results:
            print(f"[{'PASS' if ok else 'FAIL'}] {group:9s} {function.__name__}" + ("" if ok else f" -> {detail}"))
    if print_results:
        print("RESULT:", "ALL GREEN" if failures == 0 else f"{failures} FAILED")
    return failures == 0
