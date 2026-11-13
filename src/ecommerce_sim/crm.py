"""CRM messages: email, push, SMS and WhatsApp to customers, with a control group.

Programmes (each is a campaign in `campaigns`):
    Weekly newsletter     every Tuesday, email subscribers
    Welcome series        the day after sign-up
    Cart abandonment      the day after a customer left items in the cart (push, else email)
    Win-back              on the 1st and 15th, customers who have not ordered for 60-150 days
    Event messages        when an event campaign starts and on the event's first day

Every message is split: 90% "treatment" (the message is sent) and 10% "control" (held
back on purpose). Comparing the two groups measures the real effect (uplift) of CRM.
A click on a message starts a visit to the shop, which may end in an order.
"""
import zlib

import pandas as pd

from . import reference as ref
from .randomness import stream

CONTROL_SHARE = 10            # percent of customers held out of each campaign
SEND_HOUR = {"Email": 10, "Push": 19, "SMS": 12, "WhatsApp": 18}
OPT_IN = {"Email": "email_opt_in", "Push": "push_opt_in", "SMS": "sms_opt_in", "WhatsApp": "whatsapp_opt_in"}


def in_control_group(customer_id: str, campaign_id: str) -> bool:
    return zlib.crc32(f"{customer_id}|{campaign_id}".encode()) % 100 < CONTROL_SHARE


class CRM:
    def __init__(self, settings):
        self.settings = settings
        self.rows = []                 # today's sends
        self.next_send = 1
        self.open_sends = {}           # (customer, campaign) -> send row, waiting for a possible order

    def _audience(self, w, campaign: dict, day: pd.Timestamp) -> list[str]:
        name = campaign["campaign_name"]
        population = w.population
        yesterday = day - pd.Timedelta(days=1)
        if campaign["campaign_type"] == "Event":
            starts = campaign["start_date"] == day or (
                campaign["event_id"] and w.event_start.get(campaign["event_id"]) == day)
            if not starts:
                return []
            # Event messages go to customers seen in the last 120 days (30 for payday pushes).
            window = 30 if "Payday" in name else 120
            return [c["customer_id"] for c in population.customers
                    if c["account_status"] != "Deleted" and (day - c["last_seen_at"]).days <= window]
        if "WeeklyNewsletter" in name:
            if day.weekday() != 1:
                return []
            # Sunset rule: newsletters go to customers active in the last 90 days.
            return [c["customer_id"] for c in population.customers
                    if c["account_status"] == "Active" and (day - c["last_seen_at"]).days <= 90]
        if "WelcomeSeries" in name:
            return [c["customer_id"] for c in population.customers if c["signup_at"].normalize() == yesterday]
        if "CartAbandonment" in name:
            left = {cid for cid, at in w.traffic.carts_abandoned if at.normalize() == yesterday}
            if name.startswith("CRM_PUSH"):
                return sorted(left)
            return sorted(cid for cid in left if not population.row(cid)["push_opt_in"])
        if "WinBack" in name:
            if day.day not in (1, 15):
                return []
            chosen = []
            for c in population.customers:
                last = w.orders.last_order_at.get(c["customer_id"], c["signup_at"])
                if 60 <= (day - last).days <= 150 and c["account_status"] != "Deleted":
                    chosen.append(c["customer_id"])
            return chosen
        return []

    def send(self, w, day: pd.Timestamp) -> list[tuple]:
        """Send today's messages; returns the clicks that start visits (time, customer, campaign)."""
        rng = stream(self.settings.seed, "crm.send", day)
        clicks = []
        for campaign in w.marketing.live(day, "CRM"):
            channel = campaign["channel"]
            source, open_rate, click_rate, cost = ref.CRM_CHANNELS[channel]
            for customer_id in self._audience(w, campaign, day):
                customer = w.population.row(customer_id)
                if not customer[OPT_IN[channel]]:
                    continue
                send_id = f"MS{self.next_send:010d}"
                self.next_send += 1
                if in_control_group(customer_id, campaign["campaign_id"]):
                    self.rows.append([send_id, campaign["campaign_id"], customer_id, channel, "control",
                                      pd.NaT, False, pd.NaT, pd.NaT, None, False, 0.0])
                    continue
                person = w.population.profile(customer_id)
                sent_at = day + pd.Timedelta(hours=SEND_HOUR[channel], minutes=int(rng.integers(0, 50)))
                delivered = rng.random() < (0.96 if channel == "Email" else 0.985)
                engaged = min(2.0, 0.5 + person["visits_per_week"] / 2)
                opened = delivered and (channel == "SMS" or rng.random() < open_rate * engaged)
                clicked = opened and rng.random() < click_rate * engaged * (1.4 if campaign["event_id"] else 1.0)
                opened_at = sent_at + pd.Timedelta(minutes=int(rng.gamma(1.5, 90))) if opened and channel != "SMS" else pd.NaT
                clicked_at = ((opened_at if pd.notna(opened_at) else sent_at) + pd.Timedelta(minutes=int(rng.integers(1, 30)))
                              if clicked else pd.NaT)
                if pd.notna(clicked_at) and clicked_at.normalize() != day:
                    clicked_at = day + pd.Timedelta(hours=23, minutes=50)
                unsubscribed = delivered and channel in ("Email", "WhatsApp") and rng.random() < 0.002
                if unsubscribed:
                    customer[OPT_IN[channel]] = False
                row = [send_id, campaign["campaign_id"], customer_id, channel, "treatment", sent_at, delivered,
                       opened_at, clicked_at, None, unsubscribed, cost if delivered else 0.0]
                self.rows.append(row)
                if clicked:
                    clicks.append((clicked_at, customer_id, campaign["campaign_id"]))
                    self.open_sends[(customer_id, campaign["campaign_id"])] = row
        return clicks

    def record_conversion(self, customer_id: str, campaign_id: str, order_id: str) -> None:
        row = self.open_sends.pop((customer_id, campaign_id), None)
        if row is not None and row[9] is None:
            row[9] = order_id

    COLUMNS = ["send_id", "campaign_id", "customer_id", "channel", "test_group", "sent_at", "delivered",
               "opened_at", "clicked_at", "converted_order_id", "unsubscribed", "cost"]

    def take_rows(self) -> pd.DataFrame:
        frame = pd.DataFrame(self.rows, columns=self.COLUMNS)
        self.rows = []
        self.open_sends = {}
        return frame
