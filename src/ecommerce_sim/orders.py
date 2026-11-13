"""Orders and everything that happens to them afterwards.

When a customer pays, each item becomes one row in `sales` (one transaction line).
The line's whole future is decided at that moment (does the seller cancel it, when
does it ship and arrive, is it returned, refunded or exchanged, will the customer
review it or contact support) and stored with future timestamps. The published
table shows each line as of "today": milestones after today are hidden and the
`order_status` is the latest milestone reached. `updated_at` says when the line last
changed, so a daily load can pick up only changed rows.
"""
from collections import defaultdict

import numpy as np
import pandas as pd

from . import reference as ref
from . import texts
from .promotions import best_coupon

BASE_RETURN_RATE = {"Apparel": 0.11, "Footwear": 0.13, "Accessories": 0.05}
STATUS_ORDER = [
    # (status, timestamp column) in the order they can happen
    ("Placed", "placed_at"), ("Confirmed", "confirmed_at"), ("Shipped", "shipped_at"),
    ("Out for Delivery", "out_for_delivery_at"), ("Delivered", "delivered_at"),
    ("Return Requested", "return_requested_at"), ("Return Picked Up", "return_picked_up_at"),
    ("Returned", "return_received_at"), ("Exchanged", "exchanged_at"), ("Refunded", "refunded_at"),
    ("Cancelled", "cancelled_at"), ("Returned to Origin", "rto_at"), ("Undelivered", "undelivered_at"),
    ("Lost", "lost_at"),
]
TIME_COLUMNS = [column for _status, column in STATUS_ORDER] + ["payment_collected_at"]


def hours(n: float) -> pd.Timedelta:
    return pd.Timedelta(hours=float(n))


class OrderBook:
    def __init__(self, settings):
        self.settings = settings
        self.lines = []                         # full truth, one dict per transaction line
        self.reviews = []
        self.contacts = []
        self.orders_of = defaultdict(int)       # customer -> number of orders
        self.last_order_at = {}
        self.coupons_used = {}                  # customer -> {coupon code: times used}
        self.exchanges_due = defaultdict(list)  # day -> lines waiting for a replacement
        self.next_order = 1
        self.next_line = 1
        self.next_shipment = 1
        self.next_review = 1
        self.next_contact = 1
        self.next_ticket = 1
        self.slow_days = set()                  # festival days when couriers deliver slowly

    # ------------------------------------------------------------------ placing an order
    def place(self, rng, at: pd.Timestamp, customer: dict, profile: dict, address: dict, cart: list,
              catalog: dict, prices: np.ndarray, price_events: np.ndarray, session: dict,
              promotions: pd.DataFrame, events: pd.DataFrame, marketing, inventory, moves: dict,
              agents: pd.DataFrame) -> dict:
        """Create one order from the cart [(product position, sku position, units), ...]."""
        customer_id = customer["customer_id"]
        first_order = self.orders_of[customer_id] == 0
        order_id = f"OD{self.next_order:09d}"
        self.next_order += 1

        method = self._payment_method(rng, customer, profile)
        subtotal = sum(prices[p] * units for p, _s, units in cart)
        used = self.coupons_used.setdefault(customer_id, {})
        code, coupon_amount = best_coupon(promotions, at.normalize(), subtotal, method, first_order,
                                          customer["is_prime"], used)
        if code:
            used[code] = used.get(code, 0) + 1
        free_shipping = customer["is_prime"] or subtotal >= ref.FREE_SHIPPING_ABOVE
        shipping_fee = 0.0 if free_shipping else float(ref.SHIPPING_FEE)
        campaign = marketing.by_id.get(session.get("campaign_id"))

        # Items from the same warehouse travel together in one shipment.
        shipments = {}
        order_lines = []
        for k, (p, s, units) in enumerate(cart):
            warehouse = inventory.warehouse[s]
            if warehouse not in shipments:
                shipments[warehouse] = (f"SH{self.next_shipment:09d}", self._shipping_plan(rng, at, address, customer,
                                                                                          warehouse, events))
                self.next_shipment += 1
            shipment_id, plan = shipments[warehouse]
            gross = round(float(prices[p]) * units, 2)
            share = gross / subtotal if subtotal else 0
            coupon_part = round(coupon_amount * share, 2)
            fee_part = round(shipping_fee * share, 2)
            net = round(gross - coupon_part + fee_part, 2)
            gst = float(catalog["gst_rate"][p])
            line = {
                "transaction_id": f"TX{self.next_line:010d}", "order_id": order_id, "shipment_id": shipment_id,
                "line_type": "Sale", "customer_id": customer_id, "session_id": session.get("session_id"),
                "address_id": address["address_id"], "ship_city": address["city"], "ship_pincode": address["pincode"],
                "product_id": catalog["product_id"][p], "sku_id": inventory.sku_ids[s], "seller_id": catalog["seller_id"][p],
                "warehouse_id": warehouse, "quantity": int(units), "mrp": float(catalog["mrp"][p]),
                "unit_price": float(prices[p]), "gross_amount": gross, "coupon_code": code,
                "coupon_discount": coupon_part, "shipping_fee": fee_part, "net_amount": net,
                "tax_amount": round((net - fee_part) * gst / (1 + gst), 2), "gst_rate": gst,
                "unit_cost": float(catalog["unit_cost"][p]), "payment_method": method,
                "event_id": price_events[p], "campaign_id": session.get("campaign_id"),
                "traffic_source": session.get("traffic_source"), "device": session.get("device"),
                "affiliate_partner": campaign["affiliate_partner"] if campaign else None,
                "affiliate_commission": self._commission(campaign, net - fee_part, first_order and k == 0),
                "is_first_order": first_order, "courier": plan["courier"],
                "promised_delivery_date": plan["promised"],
                "placed_at": at, "confirmed_at": at + pd.Timedelta(minutes=int(rng.integers(1, 20))),
            }
            self.next_line += 1
            inventory.take(s, units, moves)
            self._decide_future(rng, line, plan, profile, catalog, p, s, inventory, events)
            self.lines.append(line)
            order_lines.append(line)
            self._maybe_review(rng, line, profile, catalog, p)
        self._maybe_contact(rng, order_lines, customer, catalog, agents)
        self.orders_of[customer_id] += 1
        self.last_order_at[customer_id] = at
        return {"order_id": order_id, "lines": order_lines,
                "revenue": sum(line["net_amount"] for line in order_lines)}

    def _payment_method(self, rng, customer: dict, profile: dict) -> str:
        share = np.array(ref.PAYMENT_SHARE_TIER[customer["city_tier"]], dtype=float)
        share[1] *= 0.4 + 1.6 * profile["cod_preference"]       # COD
        return str(rng.choice(ref.PAYMENT_METHODS, p=share / share.sum()))

    @staticmethod
    def _commission(campaign, value: float, new_customer: bool) -> float:
        if not campaign or campaign["channel_group"] != "Affiliate":
            return 0.0
        if campaign["payout_model"] == "CPS":
            return round(value * float(campaign["payout_rate"]), 2)
        if campaign["payout_model"] == "CPA" and new_customer:
            return float(campaign["payout_rate"])
        return 0.0

    def _shipping_plan(self, rng, at, address, customer, warehouse, events) -> dict:
        """Courier, promised date, and when the parcel really ships and arrives."""
        same_region = ref.WAREHOUSES[warehouse][1] == address["region"]
        promise_days = (3 if same_region else 5) + (1 if address["city_tier"] == "Tier 3" else 0)
        if customer["is_prime"]:
            promise_days -= 1
        courier = str(rng.choice(ref.COURIERS, p=ref.COURIER_SHARE))
        busy = bool((events.event_type == "Mega Sale").any()) if len(events) else False
        ship_after = rng.uniform(6, 30) + (24 if busy else 0) + (20 if at.hour >= 20 else 0)
        transit = rng.gamma(4.0, (0.55 if same_region else 1.0)) + ref.COURIER_SPEED[courier] + 1
        if address["city_tier"] == "Tier 3":
            transit += 1
        shipped = at + hours(ship_after)
        delivered = shipped + pd.Timedelta(days=max(0.6, transit)) + hours(rng.uniform(0, 8))
        if delivered.normalize() in self.slow_days:
            delivered += pd.Timedelta(days=int(rng.integers(1, 3)))
        delivered = delivered.replace(hour=int(np.clip(delivered.hour, 9, 20)))
        return {"courier": courier, "promised": (at + pd.Timedelta(days=promise_days)).normalize(),
                "shipped": shipped, "out_for_delivery": delivered.normalize() + pd.Timedelta(hours=7),
                "delivered": delivered}

    # ------------------------------------------------------------------ the future of a line
    def _decide_future(self, rng, line, plan, profile, catalog, p, s, inventory, events) -> None:
        for column in TIME_COLUMNS:
            line.setdefault(column, pd.NaT)
        line.update({"cancel_reason": None, "cancelled_by": None, "return_reason": None, "return_type": None,
                     "return_qc_result": None, "refund_amount": 0.0, "replacement_transaction_id": None})
        cod = line["payment_method"] == "COD"
        placed = line["placed_at"]
        seller_cancel = float(catalog["seller_cancel"][p])

        # 1. Cancelled before shipping (by the customer or the seller)?
        if rng.random() < (0.06 if cod else 0.035):
            when = placed + hours(rng.uniform(0.5, min(20, (plan["shipped"] - placed).total_seconds() / 3600)))
            self._cancel(line, when, "Customer", str(rng.choice(ref.CANCEL_REASONS)), inventory, s, rng)
            return
        if rng.random() < seller_cancel:
            self._cancel(line, placed + hours(rng.uniform(2, 30)), "Seller", "Out of stock at seller", inventory, s, rng)
            return
        line["shipped_at"] = plan["shipped"]

        # 2. Delivery outcome: refused (cash on delivery), failed, lost, or delivered.
        refused = (0.07 + 0.12 * profile["return_tendency"]) if cod else 0.008
        roll = rng.random()
        if roll < refused:
            line["out_for_delivery_at"] = plan["out_for_delivery"]
            line["rto_at"] = plan["delivered"] + pd.Timedelta(days=int(rng.integers(4, 9)))
            inventory.schedule_back(line["rto_at"], s, line["quantity"], "restock")
            if not cod:
                line["refunded_at"] = line["rto_at"] + pd.Timedelta(days=int(rng.integers(1, 5)))
                line["refund_amount"] = line["net_amount"]
            return
        if roll < refused + 0.006:
            line["out_for_delivery_at"] = plan["out_for_delivery"]
            line["undelivered_at"] = plan["delivered"] + pd.Timedelta(days=2)
            inventory.schedule_back(line["undelivered_at"] + pd.Timedelta(days=3), s, line["quantity"], "restock")
            if not cod:
                line["refunded_at"] = line["undelivered_at"] + pd.Timedelta(days=int(rng.integers(2, 6)))
                line["refund_amount"] = line["net_amount"]
            return
        if roll < refused + 0.009:
            line["lost_at"] = plan["shipped"] + pd.Timedelta(days=int(rng.integers(8, 15)))
            if not cod:
                line["refunded_at"] = line["lost_at"] + pd.Timedelta(days=int(rng.integers(1, 4)))
                line["refund_amount"] = line["net_amount"]
            return
        line["out_for_delivery_at"] = plan["out_for_delivery"]
        line["delivered_at"] = plan["delivered"]
        if cod:
            line["payment_collected_at"] = plan["delivered"]

        # 3. Returned? Wrong size, low quality and serial returners return more.
        size_ok = self._size_fits(rng, line, profile)
        line["size_fit"] = "Fits" if size_ok else str(rng.choice(["Too Small", "Too Large"]))
        rate = BASE_RETURN_RATE[catalog["category"][p]] * (1 + 3 * profile["return_tendency"])
        rate += 0.0 if size_ok else 0.40
        rate += max(0.0, -catalog["quality"][p]) * 0.05
        if rng.random() < min(rate, 0.9):
            if not size_ok:
                reason = str(rng.choice(["Size Issue", "Fit Issue"], p=[0.65, 0.35]))
            else:
                reason = str(rng.choice(["Quality Issue", "Damaged", "Wrong Product", "Colour Mismatch", "Changed Mind"],
                                        p=[0.32, 0.12, 0.08, 0.18, 0.30]))
            requested = line["delivered_at"] + pd.Timedelta(days=float(rng.uniform(0.3, ref.RETURN_WINDOW_DAYS)))
            picked = requested + pd.Timedelta(days=float(rng.uniform(1, 3)))
            received = picked + pd.Timedelta(days=float(rng.uniform(1, 4)))
            damaged = reason == "Damaged" or rng.random() < 0.08
            line.update({"return_reason": reason, "return_requested_at": requested, "return_picked_up_at": picked,
                         "return_received_at": received, "return_qc_result": "Damaged" if damaged else "Restocked"})
            inventory.schedule_back(received, s, line["quantity"], "damaged" if damaged else "restock")
            exchange = reason in ("Size Issue", "Fit Issue") and rng.random() < 0.55
            if exchange:
                line["return_type"] = "Exchange"
                self.exchanges_due[(received + pd.Timedelta(days=1)).normalize()].append(len(self.lines))
            else:
                line["return_type"] = "Store Credit" if rng.random() < 0.12 else "Refund"
                line["refunded_at"] = received + pd.Timedelta(days=float(rng.gamma(2.0, 1.8)))
                line["refund_amount"] = round(line["net_amount"] - line["shipping_fee"], 2)

    def _cancel(self, line, when, by, reason, inventory, s, rng) -> None:
        line.update({"cancelled_at": when, "cancelled_by": by, "cancel_reason": reason})
        inventory.schedule_back(when, s, line["quantity"], "restock")
        if line["payment_method"] != "COD":
            line["refunded_at"] = when + pd.Timedelta(days=float(rng.uniform(1, 6)))
            line["refund_amount"] = line["net_amount"]

    def _size_fits(self, rng, line, profile) -> bool:
        size = line["sku_id"].rsplit("-", 1)[1]
        if size == "FREESIZE":
            return True
        wanted = profile["apparel_size"] if size.isalpha() else profile["footwear_size"]
        return size == wanted.upper() or rng.random() < 0.3

    # ------------------------------------------------------------------ exchanges
    def process_exchanges(self, rng, day: pd.Timestamp, inventory, moves: dict) -> None:
        """Ship a replacement size for exchanges due today; refund if it is out of stock."""
        for index in self.exchanges_due.pop(day, []):
            original = self.lines[index]
            sizes = [i for i, pid in enumerate(inventory.product_ids) if pid == original["product_id"]
                     and inventory.sku_ids[i] != original["sku_id"]]
            # Pick the neighbouring size in the right direction (bigger if it was too small).
            ordered = sorted(sizes)
            current = inventory.position[original["sku_id"]]
            if original.get("size_fit") == "Too Small":
                candidates = [i for i in ordered if i > current]
            else:
                candidates = [i for i in reversed(ordered) if i < current]
            replacement = next((i for i in candidates if inventory.available(i) >= original["quantity"]), None)
            if replacement is None:
                original["return_type"] = "Refund"
                original["refunded_at"] = day + pd.Timedelta(days=2, hours=11)
                original["refund_amount"] = round(original["net_amount"] - original["shipping_fee"], 2)
                continue
            at = day + pd.Timedelta(hours=float(rng.uniform(9, 18)))
            inventory.take(replacement, original["quantity"], moves)
            line = {key: original[key] for key in ("order_id", "customer_id", "session_id", "address_id", "ship_city",
                                                   "ship_pincode", "product_id", "seller_id", "payment_method",
                                                   "campaign_id", "traffic_source", "device", "courier")}
            line.update({
                "transaction_id": f"TX{self.next_line:010d}", "shipment_id": f"SH{self.next_shipment:09d}",
                "line_type": "Exchange", "sku_id": inventory.sku_ids[replacement],
                "warehouse_id": inventory.warehouse[replacement], "quantity": original["quantity"],
                "mrp": original["mrp"], "unit_price": 0.0, "gross_amount": 0.0, "coupon_code": None,
                "coupon_discount": 0.0, "shipping_fee": 0.0, "net_amount": 0.0, "tax_amount": 0.0,
                "gst_rate": original["gst_rate"], "unit_cost": original["unit_cost"], "event_id": None,
                "affiliate_partner": None, "affiliate_commission": 0.0, "is_first_order": False,
                "promised_delivery_date": (at + pd.Timedelta(days=4)).normalize(), "placed_at": at,
                "confirmed_at": at, "cancel_reason": None, "cancelled_by": None, "return_reason": None,
                "return_type": None, "return_qc_result": None, "refund_amount": 0.0,
                "replacement_transaction_id": None, "size_fit": "Fits",
            })
            for column in TIME_COLUMNS:
                line.setdefault(column, pd.NaT)
            line["placed_at"], line["confirmed_at"] = at, at
            line["shipped_at"] = at + hours(rng.uniform(8, 30))
            delivered = line["shipped_at"] + pd.Timedelta(days=float(rng.uniform(1.5, 4)))
            line["delivered_at"] = delivered.replace(hour=int(np.clip(delivered.hour, 9, 20)))
            line["out_for_delivery_at"] = line["delivered_at"].normalize() + pd.Timedelta(hours=7)
            self.next_line += 1
            self.next_shipment += 1
            original["exchanged_at"] = line["delivered_at"]
            original["replacement_transaction_id"] = line["transaction_id"]
            self.lines.append(line)

    # ------------------------------------------------------------------ reviews and support
    def _maybe_review(self, rng, line, profile, catalog, p) -> None:
        if pd.isna(line["delivered_at"]) or rng.random() > 0.22:
            return
        late = line["delivered_at"].normalize() > line["promised_delivery_date"]
        fits = line.get("size_fit", "Fits") == "Fits"
        score = 3.9 + 0.55 * catalog["quality"][p] - (0.9 if not fits else 0) - (0.6 if late else 0) + rng.normal(0, 0.6)
        rating = int(np.clip(round(score), 1, 5))
        if not fits:
            aspect = "Size"
        elif late and rng.random() < 0.6:
            aspect = "Delivery"
        else:
            aspect = str(rng.choice(["Quality", "Look", "Price", "Delivery"], p=[0.45, 0.25, 0.2, 0.1]))
        sentiment = "Positive" if rating >= 4 else ("Neutral" if rating == 3 else "Negative")
        options = texts.REVIEW_TEXT.get((aspect, sentiment)) or texts.REVIEW_TEXT.get((aspect, "Positive" if rating >= 3 else "Negative")) \
            or texts.REVIEW_TEXT[("Quality", "Neutral")]
        self.reviews.append({
            "review_id": f"RV{self.next_review:08d}", "transaction_id": line["transaction_id"],
            "order_id": line["order_id"], "customer_id": line["customer_id"], "product_id": line["product_id"],
            "rating": rating, "title": {5: "Loved it", 4: "Good buy", 3: "Average", 2: "Disappointed", 1: "Terrible"}[rating],
            "review_text": str(rng.choice(options)), "aspect": aspect, "sentiment": sentiment,
            "verified_purchase": True, "moderation_status": "Rejected" if rng.random() < 0.03 else "Published",
            "helpful_votes": int(rng.poisson(2.5 if rating in (1, 5) else 1.0)),
            "reviewed_at": line["delivered_at"] + pd.Timedelta(days=float(rng.uniform(1, 15))),
        })
        self.next_review += 1

    def _maybe_contact(self, rng, order_lines, customer, catalog, agents) -> None:
        """Support tickets triggered by what goes wrong with this order (decided now, revealed later)."""
        first = order_lines[0]
        issue, when, chance = None, None, 0.0
        if pd.notna(first["lost_at"]) or pd.notna(first["undelivered_at"]):
            issue, chance = "Not Delivered", 0.7
            when = first["lost_at"] if pd.notna(first["lost_at"]) else first["undelivered_at"]
        elif pd.notna(first["delivered_at"]) and first["delivered_at"].normalize() > first["promised_delivery_date"] + pd.Timedelta(days=1):
            issue, chance, when = "Delivery Delay", 0.35, first["promised_delivery_date"] + pd.Timedelta(days=1, hours=11)
        elif first["return_reason"] in ("Damaged", "Wrong Product"):
            issue, chance, when = "Damaged or Wrong Item", 0.45, first["return_requested_at"] - pd.Timedelta(hours=2)
        elif first["return_type"] == "Exchange":
            issue, chance, when = "Size Exchange", 0.25, first["return_requested_at"] - pd.Timedelta(hours=3)
        elif pd.notna(first["refunded_at"]) and pd.notna(first["return_received_at"]) and \
                (first["refunded_at"] - first["return_received_at"]).days >= 5:
            issue, chance, when = "Refund Delay", 0.4, first["return_received_at"] + pd.Timedelta(days=5)
        elif pd.notna(first["cancelled_at"]):
            issue, chance, when = "Cancellation Query", 0.12, first["cancelled_at"] + pd.Timedelta(hours=20)
        if issue is None or rng.random() > chance:
            return
        product_name = catalog["product_name"][catalog["position"][first["product_id"]]]
        self.add_ticket(rng, issue, when, customer, agents, first, product_name)

    def add_ticket(self, rng, issue, when, customer, agents, line=None, product_name="the product") -> None:
        ticket_id = f"TK{self.next_ticket:08d}"
        self.next_ticket += 1
        team = texts.TEAM_FOR_ISSUE[issue]
        pool = agents[agents.team == team].agent_id.to_numpy()
        n_contacts = int(rng.choice([1, 2, 3], p=[0.62, 0.28, 0.10]))
        resolved = rng.random() < 0.86
        channel = str(rng.choice(["chat", "phone", "email"], p=[0.55, 0.25, 0.20]))
        for k in range(n_contacts):
            at = when + pd.Timedelta(hours=float(rng.uniform(0, 30)) + 24 * k)
            message = str(rng.choice(texts.TRANSCRIPTS[issue])).format(
                order=line["order_id"] if line else "my order", product=product_name,
                promised=line["promised_delivery_date"].date() if line is not None else "", city=customer["city"],
                amount=round(line["net_amount"]) if line else 0)
            last = k == n_contacts - 1
            self.contacts.append({
                "contact_id": f"CT{self.next_contact:08d}", "ticket_id": ticket_id,
                "customer_id": customer["customer_id"], "order_id": line["order_id"] if line else None,
                "transaction_id": line["transaction_id"] if line else None,
                "product_id": line["product_id"] if line else None, "contact_at": at, "channel": channel,
                "transcript_text": message, "issue_bucket_true": issue,
                "issue_category": str(rng.choice(texts.AGENT_TAGS[issue])), "agent_id": str(rng.choice(pool)),
                "first_response_minutes": int(rng.gamma(2.0, 6.0 if channel == "chat" else 40.0)) + 1,
                "resolved_at": at + pd.Timedelta(hours=float(rng.gamma(2.0, 6.0))) if (last and resolved) else pd.NaT,
                "escalated": bool(not resolved and last and rng.random() < 0.5),
                "csat": int(np.clip(round(rng.normal(4.2 if resolved else 2.3, 0.8)), 1, 5)) if last else None,
            })
            self.next_contact += 1

    # ------------------------------------------------------------------ tables as of today
    def tables(self, today: pd.Timestamp) -> dict[str, pd.DataFrame]:
        cutoff = today + pd.Timedelta(days=1)            # everything up to the end of today
        sales = pd.DataFrame(self.lines)
        if not sales.empty:
            sales = sales[sales.placed_at < cutoff].copy()
            for column in TIME_COLUMNS:
                times = pd.to_datetime(sales[column]).astype("datetime64[ns]").dt.floor("s")
                sales[column] = times.where(times < cutoff)
            hidden_until = {"return_reason": "return_requested_at", "return_type": "return_requested_at",
                            "return_qc_result": "return_received_at", "replacement_transaction_id": "exchanged_at",
                            "cancel_reason": "cancelled_at", "cancelled_by": "cancelled_at", "size_fit": "delivered_at"}
            for column, gate in hidden_until.items():
                sales[column] = sales[column].where(sales[gate].notna())
            sales["refund_amount"] = sales.refund_amount.where(sales.refunded_at.notna(), 0.0)
            sales["order_status"] = "Placed"
            sales["updated_at"] = sales.placed_at
            for status, column in STATUS_ORDER:
                reached = sales[column].notna() & (sales[column] >= sales.updated_at)
                sales.loc[reached, "order_status"] = status
                sales.loc[reached, "updated_at"] = sales.loc[reached, column]
            sales["payment_status"] = np.select(
                [sales.refunded_at.notna(),
                 (sales.payment_method == "COD") & sales.payment_collected_at.notna(),
                 (sales.payment_method == "COD") & (sales.cancelled_at.notna() | sales.rto_at.notna()
                                                     | sales.undelivered_at.notna() | sales.lost_at.notna()),
                 sales.payment_method == "COD"],
                ["Refunded", "Paid", "Not Collected", "Pending"], default="Paid")
            sales.loc[sales.line_type == "Exchange", "payment_status"] = "Not Applicable"
        reviews = pd.DataFrame(self.reviews)
        if not reviews.empty:
            reviews = reviews[reviews.reviewed_at < cutoff]
        contacts = pd.DataFrame(self.contacts)
        if not contacts.empty:
            contacts = contacts[contacts.contact_at < cutoff].copy()
            done = contacts.resolved_at < cutoff
            contacts["resolution_status"] = np.where(done, "Resolved", np.where(contacts.escalated, "Escalated", "Pending"))
            contacts["resolved_at"] = contacts.resolved_at.where(done)
            contacts["csat"] = contacts.csat.where(done)
            contacts = contacts.drop(columns=["escalated"])
        return {"sales": sales, "product_reviews": reviews, "support_contacts": contacts}
