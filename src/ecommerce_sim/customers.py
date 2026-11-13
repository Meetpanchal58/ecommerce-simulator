"""Customers: sign-up, personal data (kept separate), addresses, Prime and hidden taste.

A customer is created when a visitor signs up during a visit. Their hidden profile
(taste, sizes, how often they shop, how likely they are to return things) drives
everything they do later.
"""
import numpy as np
import pandas as pd

from . import reference as ref

CITY_NAMES = list(ref.CITIES)
CITY_WEIGHTS = np.array([ref.TIER_WEIGHT[ref.CITIES[c][2]] for c in CITY_NAMES])
CITY_WEIGHTS = CITY_WEIGHTS / CITY_WEIGHTS.sum()
CATEGORY_FOCUS = ["Apparel", "Footwear", "Accessories"]
COLOURS = ["Black", "Blue", "White", "Navy Blue", "Grey", "Red", "Pink", "Green", "Brown", "Beige"]
USAGES = ["Casual", "Formal", "Sports", "Ethnic", "Party", "Smart Casual"]

# How good customers from each channel tend to be (referrals are loyal, social ads less so).
CHANNEL_QUALITY = {"referral": 1.35, "organic_search": 1.2, "direct": 1.15, "crm": 1.05, "paid_search": 0.95,
                   "affiliate": 0.85, "display": 0.7, "paid_social": 0.7}


class Population:
    """All customers so far, plus their hidden profiles, kept in simple Python lists."""

    def __init__(self):
        self.customers = []      # published customer rows (dicts)
        self.pii = []
        self.addresses = []
        self.profiles = []       # hidden taste and behaviour (dicts)
        self.index = {}          # customer_id -> position
        self.next_number = 1
        self.next_address = 1
        self.next_anonymous = 1
        self.address_ids = {}    # customer_id -> positions in self.addresses
        # Per-customer numbers kept as plain lists (same order as self.customers) so a whole
        # day's decisions can be made at once with numpy.
        self.visit_rate = []     # visits per week
        self.lapse_days = []     # how quickly interest fades after the last order
        self.signup_day = []     # day number of sign-up
        self.last_order_day = [] # day number of the latest order (sign-up day if none)
        self.last_seen_day = []  # day number of the latest visit
        self.deleted = []

    def __len__(self):
        return len(self.customers)

    def profile(self, customer_id: str) -> dict:
        return self.profiles[self.index[customer_id]]

    def row(self, customer_id: str) -> dict:
        return self.customers[self.index[customer_id]]

    def new_person(self, rng, channel: str, device: str | None = None) -> dict:
        """A new visitor: hidden taste and habits, but no account yet (anonymous)."""
        quality = CHANNEL_QUALITY.get(channel, 1.0)
        apparel_size = int(rng.choice(len(ref.APPAREL_SIZES), p=ref.APPAREL_SIZE_SHARE))
        footwear_size = int(rng.choice(len(ref.FOOTWEAR_SIZES), p=ref.FOOTWEAR_SIZE_SHARE))
        self.next_anonymous = getattr(self, "next_anonymous", 1)
        anonymous_id = f"ANON{self.next_anonymous:09d}"
        self.next_anonymous += 1
        return {
            "customer_id": None,
            "anonymous_id": anonymous_id,
            "gender": str(rng.choice(ref.GENDERS, p=ref.GENDER_SHARE)),
            "category_focus": str(rng.choice(CATEGORY_FOCUS, p=[0.56, 0.25, 0.19])),
            "colour_focus": str(rng.choice(COLOURS)),
            "preferred_usage": str(rng.choice(USAGES, p=[0.45, 0.12, 0.12, 0.17, 0.06, 0.08])),
            "price_sensitivity": float(np.clip(rng.beta(2.2, 2.0), 0.03, 0.98)),
            "deal_seeking": float(np.clip(rng.beta(2.0, 2.5), 0.02, 0.98)),        # reacts to sales
            "visits_per_week": float(np.clip(rng.gamma(2.0, 0.26) * quality, 0.03, 4.0)),
            "buy_propensity": float(np.clip(rng.gamma(2.5, 0.35) * quality, 0.05, 3.0)),
            "return_tendency": float(np.clip(rng.beta(1.6, 9.0), 0.01, 0.45)),
            "apparel_size": ref.APPAREL_SIZES[apparel_size],
            "footwear_size": ref.FOOTWEAR_SIZES[footwear_size],
            "size_certainty": float(np.clip(rng.beta(6, 1.6), 0.4, 0.99)),      # how often they pick the right size
            "prime_propensity": float(rng.beta(1.4, 4.0)),
            "cod_preference": float(rng.beta(1.5, 4.0)),
            "device": device or str(rng.choice(ref.DEVICES, p=ref.DEVICE_SHARE)),
            "lapse_after_days": float(rng.gamma(2.5, 32.0)),                   # interest fades after this long without buying
            "acquired_via": channel,
            "city": str(rng.choice(CITY_NAMES, p=CITY_WEIGHTS)),
        }

    def sign_up(self, rng, person: dict, signup_at: pd.Timestamp, channel: str, campaign_id, device: str) -> str:
        """Turn an anonymous visitor into a customer (account, personal data, address)."""
        number = self.next_number
        self.next_number += 1
        customer_id = f"C{number:07d}"
        city = person["city"]
        state, region, tier, _pincode, _warehouse = ref.CITIES[city]
        gender = person["gender"]
        first = str(rng.choice(ref.FIRST_NAMES))
        last = str(rng.choice(ref.LAST_NAMES))
        age = str(rng.choice(ref.AGE_BRACKETS, p=ref.AGE_SHARE))
        birth_year = {"18-24": 2003, "25-34": 1994, "35-44": 1984, "45-54": 1974, "55+": 1963}[age]

        self.index[customer_id] = len(self.customers)
        self.customers.append({
            "customer_id": customer_id,
            "signup_at": signup_at,
            "signup_channel": channel,
            "signup_campaign_id": campaign_id,
            "signup_method": str(rng.choice(ref.SIGNUP_METHODS, p=ref.SIGNUP_METHOD_SHARE)),
            "signup_device": device,
            "anonymous_id": person["anonymous_id"],
            "city": city, "state": state, "region": region, "city_tier": tier,
            "age_bracket": age, "gender": gender,
            "is_prime": False, "prime_start_date": pd.NaT,
            "email_opt_in": bool(rng.random() < 0.74), "sms_opt_in": bool(rng.random() < 0.52),
            "push_opt_in": bool(device in ("Android App", "iOS App") and rng.random() < 0.65),
            "whatsapp_opt_in": bool(rng.random() < 0.40),
            "account_status": "Active",
            "last_seen_at": signup_at,
        })
        self.pii.append({
            "customer_id": customer_id,
            "full_name": f"{first} {last}",
            "email": f"{first.lower()}.{last.lower()}.{number}@example.com",
            "phone": f"+91 00000 {number % 100000:05d}",
            "date_of_birth": pd.Timestamp(birth_year + int(rng.integers(0, 10)), int(rng.integers(1, 13)),
                                          int(rng.integers(1, 29))),
        })
        self.address_ids[customer_id] = []
        self.add_address(rng, customer_id, city, label="Home", default=True, created_at=signup_at)
        person["customer_id"] = customer_id
        person["signed_up_at"] = signup_at
        self.profiles.append(person)
        day = signup_at.toordinal()
        self.visit_rate.append(person["visits_per_week"])
        self.lapse_days.append(person["lapse_after_days"])
        self.signup_day.append(day)
        self.last_order_day.append(day)
        self.last_seen_day.append(day)
        self.deleted.append(False)
        return customer_id

    def mark_seen(self, customer_id: str, when: pd.Timestamp) -> None:
        i = self.index[customer_id]
        self.customers[i]["last_seen_at"] = when
        self.last_seen_day[i] = when.toordinal()

    def mark_order(self, customer_id: str, when: pd.Timestamp) -> None:
        self.last_order_day[self.index[customer_id]] = when.toordinal()

    def delete(self, customer_id: str) -> None:
        i = self.index[customer_id]
        self.customers[i]["account_status"] = "Deleted"
        self.deleted[i] = True

    def add_address(self, rng, customer_id: str, city: str, label: str, default: bool, created_at) -> str:
        state, region, tier, prefix, warehouse = ref.CITIES[city]
        address_id = f"A{self.next_address:08d}"
        self.next_address += 1
        self.address_ids[customer_id].append(len(self.addresses))
        self.addresses.append({
            "address_id": address_id, "customer_id": customer_id, "label": label,
            "address_line": f"{int(rng.integers(1, 400))}, {rng.choice(ref.STREETS)}",
            "city": city, "state": state, "region": region, "city_tier": tier,
            "pincode": f"{prefix}{int(rng.integers(1, 99)):03d}", "is_default": default,
            "nearest_warehouse_id": warehouse, "created_at": created_at,
        })
        return address_id

    def addresses_of(self, customer_id: str) -> list[dict]:
        return [self.addresses[i] for i in self.address_ids[customer_id]]

    def join_prime(self, customer_id: str, day) -> None:
        row = self.row(customer_id)
        if not row["is_prime"]:
            row["is_prime"] = True
            row["prime_start_date"] = pd.Timestamp(day)

    # ------------------------------------------------------------------ tables
    def tables(self, today: pd.Timestamp) -> dict[str, pd.DataFrame]:
        customers = pd.DataFrame(self.customers)
        if not customers.empty:
            # Dormant: not seen for 180 days; status is worked out as of today.
            quiet = (today - pd.to_datetime(customers.last_seen_at)).dt.days > 180
            customers.loc[quiet & customers.account_status.eq("Active"), "account_status"] = "Dormant"
            customers = customers.drop(columns=["last_seen_at"])
        return {
            "customers": customers,
            "customer_pii": pd.DataFrame(self.pii),
            "customer_addresses": pd.DataFrame(self.addresses),
        }

    def truth(self) -> pd.DataFrame:
        """Hidden profiles of signed-up customers (for evaluation only)."""
        frame = pd.DataFrame(self.profiles)
        internal = [c for c in frame.columns if c.startswith("_") or c in ("city", "pending_touches")]
        return frame.drop(columns=internal)
