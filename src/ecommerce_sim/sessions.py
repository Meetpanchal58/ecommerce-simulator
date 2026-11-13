"""Visits to the shop: who comes, what they see, what they click and what they buy.

Every visit (session) follows the same path a real shopper takes:

    land (home page, a listing, search results or a product page, depending on the source)
    -> maybe sign in
    -> browse listings / search results      (products shown are logged as impressions)
    -> open products they like                (more likely near the top: position bias)
    -> pick a size and add to cart            (only if that size is in stock)
    -> checkout (anonymous visitors sign up here)
    -> pay (prepaid payments sometimes fail and are retried)
    -> order placed

Visitors today come from:
    existing customers returning on their own, ad clicks and affiliate clicks
    (from marketing), CRM message clicks, and new visitors finding the shop.
"""
import numpy as np
import pandas as pd

from . import reference as ref
from .marketing import HOUR_SHAPE
from .randomness import stream

LISTING_SLOTS = 8            # products logged per listing / search page
SIMILAR_SLOTS = 4            # "similar products" on a product page
HOME_SLOTS = 6               # "recommended for you" on the home page
POSITION_BIAS = 1 / (1 + 0.35 * np.arange(max(LISTING_SLOTS, HOME_SLOTS)))
ANONYMOUS_POOL_SIZE = 12_000
LAUNCH_DAYS = 21

# Landing page for each traffic source.
LANDING_PAGE = {"paid_search": "search_results", "shopping": "pdp", "paid_social": "plp", "display": "plp",
                "affiliate": "plp", "crm": "plp", "organic_search": "home", "direct": "home", "referral": "home",
                "video": "home"}


class Traffic:
    def __init__(self, settings, products: pd.DataFrame, skus: pd.DataFrame, taste):
        self.settings = settings
        self.taste = taste
        self.n_products = len(products)
        self.article = products.article_type.to_numpy()
        self.category = products.category.to_numpy()
        self.gender = products.gender.to_numpy()
        self.colour = products.colour.to_numpy()
        self.product_ids = products.product_id.to_numpy()
        self.size_type = products.size_type.to_numpy()
        self.mrp = products.mrp.to_numpy(dtype=float)
        # SKUs of each product sit next to each other: product p owns skus first[p] .. first[p]+count[p]-1.
        sku_product = pd.Categorical(skus.product_id, categories=products.product_id).codes
        self.sku_first = np.searchsorted(sku_product, np.arange(self.n_products))
        self.sku_count = np.bincount(sku_product, minlength=self.n_products)
        self.sku_size = skus["size"].to_numpy()
        # Which products each kind of shopper browses (their own gender plus unisex).
        self.audience = {
            "F": np.isin(self.gender, ["Women", "Girls", "Unisex"]),
            "M": np.isin(self.gender, ["Men", "Boys", "Unisex"]),
            "Other": np.isin(self.gender, ["Women", "Men", "Unisex"]),
        }
        self.popularity = np.ones(self.n_products)          # recent views and sales (drives listing order)
        self.anonymous = []                                 # visitors who have not signed up (yet)
        self.next_session = 1
        self.next_event = 1
        self.click_rows, self.impression_rows, self.auth_rows = [], [], []
        self.carts_abandoned = []                           # (customer, day) for CRM cart reminders
        self.touches = {}                                   # customer -> [(time, campaign, channel group)] for attribution

    # ------------------------------------------------------------------ helpers
    def _event(self, s: dict, event_type: str, page: str | None, product=None, sku=None, position=None,
               query=None, order_id=None, dwell=None) -> str:
        event_id = f"E{self.next_event:011d}"
        self.next_event += 1
        s["time"] = min(s["time"], s["day_end"])          # a visit never runs into the next day
        self.click_rows.append((event_id, s["session_id"], s["anonymous_id"], s["person"]["customer_id"],
                                s["time"], event_type, page,
                                None if product is None else self.product_ids[product],
                                sku, position, query, s["device"], s["traffic_source"], s["utm_source"],
                                s["utm_medium"], s["utm_campaign"], s["campaign_id"], order_id, dwell))
        s["time"] += pd.Timedelta(seconds=int(dwell if dwell else s["rng"].integers(3, 25)))
        return event_id

    def _shown(self, s: dict, event_id: str, surface: str, positions: np.ndarray) -> None:
        for slot, p in enumerate(positions, 1):
            row = [event_id, s["session_id"], s["anonymous_id"], s["person"]["customer_id"], s["time"],
                   surface, slot, self.product_ids[p], False, False]
            s["shown"][(event_id, p)] = row
            self.impression_rows.append(row)

    def _audience_mask(self, gender: str) -> np.ndarray:
        return self.audience[gender]

    def prepare_day(self, day: pd.Timestamp, prices: np.ndarray, on_hand: np.ndarray) -> None:
        """Daily listing order: products live today with some stock, most popular first."""
        sellable = ~np.isnan(prices)
        stock_by_product = np.add.reduceat(np.maximum(on_hand, 0), self.sku_first) if len(on_hand) else np.zeros(1)
        stock_by_product = np.where(self.sku_count > 0, stock_by_product, 0)
        self.visible = sellable & (stock_by_product > 0)
        self.visible_any = sellable                  # out-of-stock products can still be opened from links
        rng = stream(self.settings.seed, "traffic.ranking", day)
        noise = rng.lognormal(0, 0.35, self.n_products)
        self.rank_score = np.where(self.visible, self.popularity * noise, -1.0)
        self.by_article = {}
        order = np.argsort(-self.rank_score, kind="stable")
        for p in order[self.rank_score[order] > 0]:
            self.by_article.setdefault(self.article[p], []).append(p)
        self.by_article = {k: np.array(v) for k, v in self.by_article.items()}
        # Article types a shopper can browse today, per gender (and per favourite category).
        self.articles_for = {}
        for shopper, mask in self.audience.items():
            live = mask & self.visible
            self.articles_for[(shopper, None)] = self.article[live]
            for category in ("Apparel", "Footwear", "Accessories"):
                self.articles_for[(shopper, category)] = self.article[live & (self.category == category)]
        self.month = day.month
        self.prices = prices
        self.popularity *= 0.97                      # popularity fades unless refreshed

    def _pick_article(self, rng, person: dict) -> str | None:
        """An article type to browse: usually from their favourite category."""
        category = person["category_focus"] if rng.random() < 0.75 else None
        candidates = self.articles_for[(person["gender"], category)]
        if len(candidates) == 0:
            candidates = self.articles_for[(person["gender"], None)]
        if len(candidates) == 0:
            return None
        return str(candidates[int(rng.integers(0, len(candidates)))])

    def _listing(self, rng, person: dict, article: str, query_colour: str | None = None) -> np.ndarray:
        items = self.by_article.get(article, np.array([], dtype=int))
        if len(items) == 0:
            return items
        keep = self.audience[person["gender"]][items]
        if query_colour:
            coloured = keep & (self.colour[items] == query_colour)
            if coloured.sum() >= 3:
                keep = coloured
        items = items[keep]
        page = int(rng.integers(0, 2)) if len(items) > 2 * LISTING_SLOTS else 0
        return items[page * LISTING_SLOTS:(page + 1) * LISTING_SLOTS]

    def _clicks(self, rng, person: dict, shown: np.ndarray, base: float) -> list[int]:
        """Which of the shown products the visitor opens (taste x position bias)."""
        if len(shown) == 0:
            return []
        score = self.taste.score(person, shown, self.month, self.prices[shown])
        relative = score / max(score.mean(), 1e-9)
        chance = np.clip(base * relative * POSITION_BIAS[:len(shown)], 0, 0.85)
        return [int(p) for p, c in zip(shown, chance) if rng.random() < c]

    def _choose_sku(self, rng, person: dict, p: int) -> int:
        first, count = self.sku_first[p], self.sku_count[p]
        sizes = list(self.sku_size[first:first + count])
        if self.size_type[p] == "Free Size" or count == 1:
            return int(first)
        wanted = person["apparel_size"] if self.size_type[p] == "Apparel" else person["footwear_size"]
        if wanted in sizes and rng.random() < person["size_certainty"]:
            return int(first + sizes.index(wanted))
        if wanted in sizes:
            k = sizes.index(wanted) + int(rng.choice([-1, 1]))
            return int(first + min(max(k, 0), count - 1))
        return int(first + int(rng.integers(0, count)))

    # ------------------------------------------------------------------ one visit
    def visit(self, w, rng, person: dict, start: pd.Timestamp, source: dict) -> None:
        """Simulate one session. `w` is the World (population, orders, inventory, ...)."""
        session = {
            "rng": rng, "person": person, "time": start, "session_id": f"SE{self.next_session:010d}",
            "anonymous_id": person["anonymous_id"], "device": person["device"] if rng.random() < 0.85
            else str(rng.choice(ref.DEVICES, p=ref.DEVICE_SHARE)),
            "traffic_source": source["traffic_source"], "utm_source": source["utm_source"],
            "utm_medium": source["utm_medium"], "utm_campaign": source.get("utm_campaign"),
            "campaign_id": source.get("campaign_id"), "shown": {},
            "day_end": start.normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1),
        }
        self.next_session += 1
        s = session
        customer_id = person["customer_id"]
        if customer_id:
            w.population.row(customer_id)["last_seen_at"] = start
            if s["campaign_id"]:
                self.touches.setdefault(customer_id, []).append((start, s["campaign_id"], source["group"]))
        elif s["campaign_id"]:
            person.setdefault("pending_touches", []).append((start, s["campaign_id"], source["group"]))

        page = LANDING_PAGE.get(source["landing"], "home")
        self._event(s, "session_start", page)
        if customer_id and s["device"] in ("Mobile Web", "Desktop Web") and rng.random() < 0.35:
            self._login(s, rng)

        prime = bool(customer_id and w.population.row(customer_id)["is_prime"])
        sale_on = w.sale_today_prime if prime else w.sale_today
        deal_mood = 1.0 + (person["deal_seeking"] * 0.8 if sale_on else 0.0)
        cart = []
        viewed = []

        if page == "home":
            event_id = self._event(s, "home_view", "home", dwell=int(rng.integers(5, 30)))
            article = self._pick_article(rng, person)
            if article is not None:
                shown = self._listing(rng, person, article)[:HOME_SLOTS]
                self._shown(s, event_id, "home_recs", shown)
                viewed += [(event_id, p, slot) for slot, p in enumerate(shown, 1)
                           if p in self._clicks(rng, person, shown, 0.22)]
        if page == "pdp":
            article = self._pick_article(rng, person)
            items = self.by_article.get(article, np.array([], dtype=int)) if article else []
            if len(items):
                viewed.append((None, int(items[int(rng.integers(0, min(len(items), 30)))]), None))

        pages = 1 + int(rng.geometric(0.55)) - 1 if page != "pdp" else int(rng.random() < 0.4)
        for k in range(pages):
            article = self._pick_article(rng, person)
            if article is None:
                break
            searching = (page == "search_results" and k == 0) or rng.random() < 0.45
            if searching:
                colour = person["colour_focus"] if rng.random() < 0.5 else None
                query = f"{colour.lower() + ' ' if colour else ''}{article.lower()}"
                event_id = self._event(s, "search", "search_results", query=query, dwell=int(rng.integers(4, 20)))
                shown = self._listing(rng, person, article, colour)
                surface = "search_results"
            else:
                event_id = self._event(s, "plp_view", "plp", dwell=int(rng.integers(5, 40)))
                shown = self._listing(rng, person, article)
                surface = "plp"
                if rng.random() < 0.15:
                    self._event(s, "filter_apply", "plp")
                if rng.random() < 0.08:
                    self._event(s, "sort_apply", "plp")
            self._shown(s, event_id, surface, shown)
            for p in self._clicks(rng, person, shown, 0.20):
                viewed.append((event_id, p, int(np.flatnonzero(shown == p)[0]) + 1))

        # Product pages: look, maybe follow a "similar products" suggestion, maybe add to cart.
        for source_event, p, slot in viewed[:5]:
            if source_event is not None:
                s["shown"][(source_event, p)][8] = True          # clicked
            event_id = self._event(s, "pdp_view", "pdp", product=p, position=slot, dwell=int(rng.gamma(2.0, 22)))
            self.popularity[p] += 0.15
            similar = self.by_article.get(self.article[p], np.array([], dtype=int))
            similar = similar[similar != p][:SIMILAR_SLOTS]
            self._shown(s, event_id, "pdp_similar", similar)
            if len(cart) < 4 and self._wants(rng, person, p, deal_mood):
                sku = self._choose_sku(rng, person, p)
                w.demand[sku] += 1
                if w.inventory.available(sku) <= 0:
                    self._event(s, "out_of_stock_view", "pdp", product=p, sku=w.inventory.sku_ids[sku])
                    if customer_id and rng.random() < 0.02:
                        w.orders.add_ticket(rng, "Product Question", s["time"] + pd.Timedelta(minutes=10),
                                            w.population.row(customer_id), w.agents,
                                            product_name=w.catalog["product_name"][p])
                    continue
                self._event(s, "add_to_cart", "pdp", product=p, sku=w.inventory.sku_ids[sku])
                if source_event is not None:
                    s["shown"][(source_event, p)][9] = True      # added to cart
                cart.append((p, sku, int(rng.choice([1, 2], p=[0.92, 0.08]))))
            elif rng.random() < 0.06:
                self._event(s, "wishlist_add", "pdp", product=p)
            clicked_similar = self._clicks(rng, person, similar, 0.10)
            if clicked_similar and len(viewed) < 6:
                viewed.append((event_id, clicked_similar[0], int(np.flatnonzero(similar == clicked_similar[0])[0]) + 1))

        # Anonymous visitors sometimes create an account mid-visit (welcome coupon prompt),
        # much more often in the launch weeks and when they have something in the cart.
        if not person["customer_id"]:
            launch = (start.normalize() - self.settings.start).days < LAUNCH_DAYS
            chance = (0.30 if launch else 0.06) + (0.10 if cart else 0.0)
            if rng.random() < chance:
                self._sign_up_now(w, s, rng, person)

        if cart and rng.random() < 0.10:
            removed = cart.pop()
            self._event(s, "remove_from_cart", "cart", product=removed[0], sku=w.inventory.sku_ids[removed[1]])
        if cart:
            self._checkout(w, s, rng, person, cart, deal_mood)
        self._event(s, "session_end", None, dwell=1)

    def _wants(self, rng, person: dict, p: int, deal_mood: float) -> bool:
        score = self.taste.score(person, np.array([p]), self.month, self.prices[[p]])[0]
        discount = 1 - self.prices[p] / self.mrp[p]
        price_pull = 1 + discount * person["deal_seeking"] * 1.5
        chance = 0.035 * person["buy_propensity"] * min(score, 4.0) * price_pull * deal_mood
        return rng.random() < min(chance, 0.6)

    def _login(self, s: dict, rng) -> None:
        method = str(rng.choice(ref.SIGNUP_METHODS, p=ref.SIGNUP_METHOD_SHARE))
        if rng.random() < 0.06:
            self.auth_rows.append((s["time"], s["person"]["customer_id"], "otp_failed", method, s["device"], False,
                                   s["session_id"]))
            s["time"] = min(s["time"] + pd.Timedelta(seconds=40), s["day_end"])
        self.auth_rows.append((s["time"], s["person"]["customer_id"], "login", method, s["device"], True, s["session_id"]))
        self._event(s, "login", "login")

    def _sign_up_now(self, w, s: dict, rng, person: dict) -> None:
        customer_id = w.sign_up(rng, person, s["time"], s)
        self.auth_rows.append((s["time"], customer_id, "signup", w.population.row(customer_id)["signup_method"],
                               s["device"], True, s["session_id"]))
        self._event(s, "signup", "login")

    def _checkout(self, w, s: dict, rng, person: dict, cart: list, deal_mood: float) -> None:
        self._event(s, "view_cart", "cart")
        if rng.random() > min(0.72, 0.40 * person["buy_propensity"] * deal_mood):
            if person["customer_id"]:
                self.carts_abandoned.append((person["customer_id"], s["time"]))
            return
        if not person["customer_id"]:
            if rng.random() > 0.55:            # many visitors leave when asked to create an account
                return
            self._sign_up_now(w, s, rng, person)
        self._event(s, "checkout_start", "checkout")
        customer = w.population.row(person["customer_id"])
        for attempt in range(3):
            method = w.orders._payment_method(rng, customer, person)
            self._event(s, "payment_attempt", "payment")
            if rng.random() < ref.PAYMENT_FAILURE_RATE[method]:
                self._event(s, "payment_failed", "payment")
                if rng.random() < 0.35 * (attempt + 1):
                    if rng.random() < 0.04:
                        w.payment_issue(rng, customer, s["time"])
                    return
                continue
            break
        address = w.population.addresses_of(person["customer_id"])[-1]
        order = w.place_order(rng, s["time"], customer, person, address, cart, s)
        self._event(s, "purchase", "confirmation", order_id=order["order_id"])
        for p, _sku, units in cart:
            self.popularity[p] += 1.0 * units

    # ------------------------------------------------------------------ a whole day
    def run_day(self, w, day: pd.Timestamp, demand: float, landings: list, crm_clicks: list) -> None:
        rng = stream(self.settings.seed, "traffic.day", day)
        scale = self.settings.scale
        visits = []         # (start time, person, source)

        # 1. Existing customers coming back on their own (interest fades after their last order).
        for person in w.population.profiles:
            customer_id = person["customer_id"]
            if w.population.row(customer_id)["account_status"] == "Deleted":
                continue
            last = w.orders.last_order_at.get(customer_id, person["signed_up_at"])
            idle = (day - last).days
            fade = max(0.04, np.exp(-max(0, idle - 7) / person["lapse_after_days"]))
            rate = person["visits_per_week"] / 7 * demand * fade
            for _ in range(int(rng.poisson(rate))):
                visits.append((self._start(rng, day), person, self._organic_source(rng)))

        # 2. Ad, affiliate and CRM clicks that landed on the site.
        recent = [p for p in w.population.profiles
                  if (day - w.population.row(p["customer_id"])["last_seen_at"]).days <= 21]
        lapsed = [p for p in w.population.profiles
                  if (day - w.orders.last_order_at.get(p["customer_id"], p["signed_up_at"])).days > 60]
        for hour, minute, campaign_id, audience in landings:
            campaign = w.marketing.by_id[campaign_id]
            person = self._who_clicked(rng, w, audience, campaign, recent, lapsed)
            start = day + pd.Timedelta(hours=hour, minutes=minute)
            visits.append((start, person, self._campaign_source(campaign)))
        for start, customer_id, campaign_id in crm_clicks:
            campaign = w.marketing.by_id[campaign_id]
            visits.append((start, w.population.profile(customer_id), self._campaign_source(campaign)))

        # 3. New visitors finding the shop (many more during the launch weeks), and
        #    earlier anonymous visitors returning.
        new_visitors = rng.poisson(self.settings.daily_new_visitors * scale * demand)
        if (day - self.settings.start).days < LAUNCH_DAYS:
            new_visitors += rng.poisson(self.settings.launch_customers / LAUNCH_DAYS * 2.4)
        for _ in range(int(new_visitors)):
            source = self._organic_source(rng)
            person = w.population.new_person(rng, source["traffic_source"])
            self._remember_anonymous(person)
            visits.append((self._start(rng, day), person, source))
        returning = [p for p in self.anonymous if p["customer_id"] is None and rng.random() < p["visits_per_week"] / 7 * 0.3]
        for person in returning:
            visits.append((self._start(rng, day), person, self._organic_source(rng)))

        visits.sort(key=lambda v: (v[0], v[1]["anonymous_id"]))
        for start, person, source in visits:
            self.visit(w, rng, person, start, source)

    def _start(self, rng, day) -> pd.Timestamp:
        hour = int(rng.choice(24, p=HOUR_SHAPE))
        return day + pd.Timedelta(hours=hour, minutes=int(rng.integers(0, 60)), seconds=int(rng.integers(0, 60)))

    def _organic_source(self, rng) -> dict:
        name = str(rng.choice(["direct", "organic_search", "referral"], p=[0.47, 0.43, 0.10]))
        utm_source, utm_medium = ref.ORGANIC_SOURCES[name]
        return {"traffic_source": name, "utm_source": utm_source, "utm_medium": utm_medium, "landing": name,
                "group": "Organic"}

    def _campaign_source(self, campaign: dict) -> dict:
        group = campaign["channel_group"]
        traffic = {"Paid Search": "paid_search", "Paid Social": "paid_social", "Display": "display",
                   "Affiliate": "affiliate", "CRM": "crm"}[group]
        landing = traffic
        if campaign["channel"] == "Google Shopping":
            landing = "shopping"
        elif campaign["channel"] == "YouTube":
            landing = "video"
        return {"traffic_source": traffic, "utm_source": campaign["utm_source"], "utm_medium": campaign["utm_medium"],
                "utm_campaign": campaign["utm_campaign"], "campaign_id": campaign["campaign_id"], "landing": landing,
                "group": group}

    def _who_clicked(self, rng, w, audience: str, campaign: dict, recent: list, lapsed: list) -> dict:
        new_share = {"New": 0.85, "All": 0.45, "Active": 0.05, "Lapsed": 0.05}.get(audience, 0.45)
        if campaign["channel_group"] == "Affiliate":
            new_share = 0.55
        pool = recent if audience in ("Active", "All", "New") else lapsed
        if rng.random() < new_share or not pool:
            person = w.population.new_person(rng, campaign["channel_group"].lower().replace(" ", "_"))
            self._remember_anonymous(person)
            return person
        return pool[int(rng.integers(0, len(pool)))]

    def _remember_anonymous(self, person: dict) -> None:
        self.anonymous.append(person)
        if len(self.anonymous) > ANONYMOUS_POOL_SIZE:
            self.anonymous = [p for p in self.anonymous[-ANONYMOUS_POOL_SIZE:] if p["customer_id"] is None]

    # ------------------------------------------------------------------ rows
    CLICK_COLUMNS = ["event_id", "session_id", "anonymous_id", "customer_id", "event_at", "event_type", "page_type",
                     "product_id", "sku_id", "list_position", "search_query", "device", "traffic_source",
                     "utm_source", "utm_medium", "utm_campaign", "campaign_id", "order_id", "dwell_seconds"]
    IMPRESSION_COLUMNS = ["page_event_id", "session_id", "anonymous_id", "customer_id", "shown_at", "surface",
                          "position", "product_id", "clicked", "added_to_cart"]
    AUTH_COLUMNS = ["event_at", "customer_id", "event_type", "method", "device", "success", "session_id"]

    def take_rows(self) -> dict[str, pd.DataFrame]:
        """Hand over today's event rows (and clear them)."""
        rows = {
            "clickstream": pd.DataFrame(self.click_rows, columns=self.CLICK_COLUMNS),
            "impressions": pd.DataFrame(self.impression_rows, columns=self.IMPRESSION_COLUMNS),
            "auth_events": pd.DataFrame(self.auth_rows, columns=self.AUTH_COLUMNS),
        }
        self.click_rows, self.impression_rows, self.auth_rows = [], [], []
        return rows
