"""Coupons and offers.

Each sale event gets its own coupon code(s), live only during the event. A few
always-on offers exist too: a welcome coupon for first orders, a bank card offer and
a Prime members' coupon.
"""
import pandas as pd

ALWAYS_ON = [
    # code, offer type, value, minimum order, maximum discount, audience, payment method
    ("FIRST100", "Flat Off", 100, 499, 100, "New", None),
    ("BANK10", "Bank Offer", 0.10, 1499, 300, "All", "Credit Card"),
    ("PRIME15", "% Off", 0.15, 999, 250, "Prime", None),
]


def short_code(event_name: str) -> str:
    """'Diwali 2025' -> 'DIWALI'; "Valentine's Day 2026" -> 'VALENTINES'."""
    first = event_name.split()[0].upper()
    return "".join(ch for ch in first if ch.isalnum())[:10]


def build_promotions(settings, events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    open_ended = pd.Timestamp("2099-12-31")
    for code, kind, value, minimum, cap, audience, method in ALWAYS_ON:
        rows.append({
            "promo_id": f"PR_{code}", "code": code, "event_id": None, "offer_type": kind, "value": value,
            "min_order_value": minimum, "max_discount": cap, "eligible_audience": audience,
            "eligible_payment_method": method, "usage_limit_per_customer": 1 if audience == "New" else 99,
            "start_date": settings.start, "end_date": open_ended,
        })
    for event in events.itertuples(index=False):
        percent = int(round(min(event.avg_extra_discount + 0.05, 0.40) * 100))
        code = f"{short_code(event.name)}{percent}" if event.event_type != "Payday" else "PAYDAY5"
        rows.append({
            "promo_id": f"PR_{event.event_id}", "code": code, "event_id": event.event_id, "offer_type": "% Off",
            "value": 0.05, "min_order_value": 1299 if event.event_type in ("Mega Sale", "Festival") else 999,
            "max_discount": 400, "eligible_audience": "All", "eligible_payment_method": None,
            "usage_limit_per_customer": 2, "start_date": event.start_date, "end_date": event.end_date,
        })
        if event.event_type == "Mega Sale":
            rows.append({
                "promo_id": f"PR_{event.event_id}_BANK", "code": f"{short_code(event.name)}BANK", "event_id": event.event_id,
                "offer_type": "Bank Offer", "value": 0.10, "min_order_value": 2499, "max_discount": 750,
                "eligible_audience": "All", "eligible_payment_method": "Credit Card", "usage_limit_per_customer": 1,
                "start_date": event.start_date, "end_date": event.end_date,
            })
    return pd.DataFrame(rows)


def best_coupon(promotions: pd.DataFrame, day, order_value: float, payment_method: str,
                is_first_order: bool, is_prime: bool, used: dict) -> tuple[str | None, float]:
    """The coupon giving the biggest discount the customer may use today, and its amount."""
    live = promotions[(promotions.start_date <= day) & (promotions.end_date >= day)]
    best_code, best_amount = None, 0.0
    for promo in live.itertuples(index=False):
        if order_value < promo.min_order_value:
            continue
        if promo.eligible_audience == "New" and not is_first_order:
            continue
        if promo.eligible_audience == "Prime" and not is_prime:
            continue
        if promo.eligible_payment_method and promo.eligible_payment_method != payment_method:
            continue
        if used.get(promo.code, 0) >= promo.usage_limit_per_customer:
            continue
        if promo.offer_type == "Flat Off":
            amount = float(promo.value)
        else:
            amount = min(order_value * float(promo.value), float(promo.max_discount))
        if amount > best_amount:
            best_code, best_amount = promo.code, round(amount, 2)
    return best_code, best_amount
