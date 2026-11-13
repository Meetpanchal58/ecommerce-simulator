"""Marketing: campaigns, their plan (budget and targets), and hourly delivery.

Story for a paid campaign:
    planned budget per day  ->  actual spend per hour  ->  impressions  ->  clicks
    ->  some clicks land on the site as visits (with UTM tags)  ->  some visits order.

Campaigns are created on the day they start:
* on the 1st of every month: always-on campaigns per channel, one per affiliate partner,
  and lifecycle CRM programmes;
* a few days before each sale event: event campaigns that ramp up into the event.
"""
import numpy as np
import pandas as pd

from . import reference as ref
from .calendar import active_events
from .randomness import stream

# Hour-of-day shape of online activity (00:00 .. 23:00), peaking in the evening.
HOUR_SHAPE = np.array([0.6, 0.35, 0.2, 0.15, 0.15, 0.25, 0.5, 0.9, 1.2, 1.3, 1.35, 1.4,
                       1.45, 1.4, 1.35, 1.35, 1.4, 1.5, 1.7, 1.95, 2.1, 2.0, 1.6, 1.0])
HOUR_SHAPE = HOUR_SHAPE / HOUR_SHAPE.sum()
REGIONS = ["West", "North", "South", "East"]
REGION_SHARE = np.array([0.32, 0.27, 0.28, 0.13])
LANDING_RATE = 0.78          # share of ad clicks that load the site (the rest bounce before tracking)

# Always-on paid campaigns: (channel, campaign type, objective, audience, monthly budget in Rs)
ALWAYS_ON_PAID = [
    ("Google Search", "Brand", "Acquisition", "All", 18_000),
    ("Google Search", "Generic", "Acquisition", "New", 25_000),
    ("Google Shopping", "Performance", "Acquisition", "All", 22_000),
    ("Bing Search", "Generic", "Acquisition", "New", 4_000),
    ("Meta", "Prospecting", "Acquisition", "New", 23_000),
    ("Meta", "Retargeting", "Retargeting", "Active", 7_000),
    ("Instagram", "Prospecting", "Awareness", "New", 8_000),
    ("YouTube", "Brand", "Awareness", "All", 14_000),
    ("DSP Display", "Retargeting", "Retargeting", "Lapsed", 12_000),
]
# Paid channels used for each kind of event, and the event budget (Rs per event day).
EVENT_CHANNELS = {
    "Mega Sale": (["Google Search", "Google Shopping", "Meta", "Instagram", "YouTube", "DSP Display"], 9_000),
    "Festival": (["Google Search", "Meta", "Instagram"], 3_000),
    "Clearance": (["Google Shopping", "Meta", "Instagram"], 4_000),
    "Season Sale": (["Google Search", "Meta"], 2_500),
}
# Platforms report more conversions than the shop sees (view-through, cross-device).
PLATFORM_OVER_REPORTING = {"Paid Search": 1.08, "Paid Social": 1.35, "Display": 1.6, "Affiliate": 1.0, "CRM": 1.0}
CHANNEL_CODES = {"Google Search": "GSEARCH", "Google Shopping": "GSHOP", "Bing Search": "BING", "Meta": "META",
                 "Instagram": "IG", "YouTube": "YT", "DSP Display": "DSP", "Email": "EMAIL", "Push": "PUSH",
                 "SMS": "SMS", "WhatsApp": "WA"}


def campaign_slug(text: str) -> str:
    return "".join(ch for ch in text.title() if ch.isalnum())


class Marketing:
    def __init__(self, settings):
        self.settings = settings
        self.campaigns = []        # campaign rows (dicts)
        self.plan_rows = []        # marketing_plan rows (tuples)
        self.plan_by_day = {}      # day -> {campaign_id: planned spend}
        self.by_id = {}
        self.next_number = 1

    # ------------------------------------------------------------------ campaign creation
    def _add(self, rng, **fields) -> dict:
        campaign_id = f"CMP{self.next_number:05d}"
        self.next_number += 1
        campaign = {"campaign_id": campaign_id, "event_id": None, "promo_code": None,
                    "affiliate_partner": None, "affiliate_type": None, "payout_model": None,
                    "payout_rate": None, "utm_source": None, "utm_medium": None, **fields}
        campaign["utm_campaign"] = campaign["campaign_name"].lower()
        self.campaigns.append(campaign)
        self.by_id[campaign_id] = campaign
        if campaign["channel_group"] not in ("Affiliate", "CRM"):
            self._plan(rng, campaign)
        return campaign

    def _plan(self, rng, campaign: dict) -> None:
        """Planned spend and targets for each day of a paid campaign."""
        days = pd.date_range(campaign["start_date"], campaign["end_date"], freq="D")
        group, cpm, ctr, _source, _medium = ref.PAID_CHANNELS[campaign["channel"]]
        weights = np.ones(len(days))
        if campaign["event_id"]:
            # Event budgets ramp up: run-up days get less than the event days.
            ramp = np.linspace(0.4, 1.0, max(1, len(days)))
            weights = ramp
        weights = weights / weights.sum()
        budget = campaign["total_budget"]
        for day, weight in zip(days, weights):
            spend = round(budget * weight, 2)
            impressions = spend / cpm * 1000
            clicks = impressions * ctr
            orders = clicks * LANDING_RATE * 0.028
            self.plan_rows.append((day, campaign["campaign_id"], spend, int(impressions), int(clicks),
                                   round(orders, 1), round(orders * 1650, 2)))
            self.plan_by_day.setdefault(day, {})[campaign["campaign_id"]] = spend

    def create_campaigns(self, day: pd.Timestamp, events: pd.DataFrame, promotions: pd.DataFrame) -> None:
        """Create the campaigns that start today."""
        rng = stream(self.settings.seed, "marketing.campaigns", day)
        scale = self.settings.scale
        growth = 1 + 0.25 * min(1.0, (day - self.settings.start).days / 540)   # budgets grow as the shop grows
        if day.day == 1 or day == self.settings.start:
            month_end = (day + pd.offsets.MonthEnd(0)).normalize()
            label = f"{day:%y%m}"
            for channel, kind, objective, audience, monthly in ALWAYS_ON_PAID:
                group, _cpm, _ctr, source, medium = ref.PAID_CHANNELS[channel]
                share = ((month_end - day).days + 1) / month_end.day
                self._add(rng, campaign_name=f"{CHANNEL_CODES[channel]}_{kind}_{audience}_AlwaysOn_{label}",
                          channel_group=group, channel=channel, campaign_type=kind, objective=objective,
                          audience=audience, offer_type="None", start_date=day, end_date=month_end,
                          total_budget=round(monthly * share * scale * growth * rng.uniform(0.9, 1.1), 2),
                          utm_source=source, utm_medium=medium)
            for partner, (kind, payout, rate, _clicks) in ref.AFFILIATE_PARTNERS.items():
                self._add(rng, campaign_name=f"AFF_{campaign_slug(partner)}_{payout}_{label}",
                          channel_group="Affiliate", channel="Affiliate Network", campaign_type="Performance",
                          objective="Acquisition", audience="All", offer_type="Cashback" if kind == "Cashback" else "None",
                          start_date=day, end_date=month_end, total_budget=None, affiliate_partner=partner,
                          affiliate_type=kind, payout_model=payout, payout_rate=rate,
                          utm_source=campaign_slug(partner).lower(), utm_medium="affiliate")
            for program, channel, audience, objective in [
                ("WeeklyNewsletter", "Email", "Active", "Retention"),
                ("WelcomeSeries", "Email", "New", "Activation"),
                ("CartAbandonment", "Push", "Active", "Conversion"),
                ("CartAbandonmentEmail", "Email", "Active", "Conversion"),
                ("WinBack", "Email", "Lapsed", "Win-back"),
                ("WinBackWhatsApp", "WhatsApp", "Lapsed", "Win-back"),
            ]:
                source = ref.CRM_CHANNELS[channel][0]
                self._add(rng, campaign_name=f"CRM_{CHANNEL_CODES[channel]}_{program}_{label}", channel_group="CRM",
                          channel=channel, campaign_type="Lifecycle", objective=objective, audience=audience,
                          offer_type="None", start_date=day, end_date=month_end, total_budget=None,
                          utm_source=source, utm_medium="crm")

        # Event campaigns start `run_up_days` before the event and end with it.
        starting = events[(events.start_date - pd.to_timedelta(events.run_up_days, unit="D")) == day]
        for event in starting.itertuples(index=False):
            promo = promotions[promotions.event_id == event.event_id]
            code = promo.code.iloc[0] if len(promo) else None
            slug = campaign_slug(event.name)
            channels, per_day = EVENT_CHANNELS.get(event.event_type, ([], 0))
            n_days = (event.end_date - day).days + 1
            for channel in channels:
                group, _cpm, _ctr, source, medium = ref.PAID_CHANNELS[channel]
                self._add(rng, campaign_name=f"{CHANNEL_CODES[channel]}_Event_All_{slug}", channel_group=group,
                          channel=channel, campaign_type="Event", objective="Conversion", audience="All",
                          offer_type="% Off", start_date=day, end_date=event.end_date,
                          total_budget=round(per_day / len(channels) * n_days * scale * growth * rng.uniform(0.85, 1.15), 2),
                          event_id=event.event_id, promo_code=code, utm_source=source, utm_medium=medium)
            crm_channels = {"Mega Sale": ["Email", "Push", "WhatsApp", "SMS"], "Festival": ["Email", "Push"],
                            "Clearance": ["Email", "Push"], "Season Sale": ["Email"], "Payday": ["Push"]}
            for channel in crm_channels.get(event.event_type, []):
                self._add(rng, campaign_name=f"CRM_{CHANNEL_CODES[channel]}_Event_{slug}", channel_group="CRM",
                          channel=channel, campaign_type="Event", objective="Conversion", audience="All",
                          offer_type="% Off", start_date=day, end_date=event.end_date, total_budget=None,
                          event_id=event.event_id, promo_code=code, utm_source=ref.CRM_CHANNELS[channel][0],
                          utm_medium="crm")
            if event.event_type in ("Mega Sale", "Festival"):
                for partner in ("SaveMore Cashback", "DealDhamaka Coupons"):
                    kind, payout, rate, _clicks = ref.AFFILIATE_PARTNERS[partner]
                    self._add(rng, campaign_name=f"AFF_{campaign_slug(partner)}_Event_{slug}", channel_group="Affiliate",
                              channel="Affiliate Network", campaign_type="Event", objective="Conversion", audience="All",
                              offer_type="Cashback" if kind == "Cashback" else "% Off", start_date=day,
                              end_date=event.end_date, total_budget=None, event_id=event.event_id, promo_code=code,
                              affiliate_partner=partner, affiliate_type=kind, payout_model=payout,
                              payout_rate=rate + 0.02 if payout == "CPS" else rate,
                              utm_source=campaign_slug(partner).lower(), utm_medium="affiliate")

    def live(self, day: pd.Timestamp, group: str | None = None) -> list[dict]:
        return [c for c in self.campaigns if c["start_date"] <= day <= c["end_date"]
                and (group is None or c["channel_group"] == group)]

    # ------------------------------------------------------------------ daily delivery
    def deliver(self, day: pd.Timestamp, events: pd.DataFrame, demand: float):
        """Today's paid and affiliate delivery.

        Returns (spend rows, landings). A landing is one ad click that loaded the site:
        (hour, minute, campaign, audience). The visits are simulated by the session code.
        """
        rng = stream(self.settings.seed, "marketing.delivery", day)
        mega_today = len(active_events(events, day).query("event_type == 'Mega Sale'")) > 0
        plan_today = self.plan_by_day.get(day, {})
        spend_rows, landings = [], []
        for campaign in self.live(day, None):
            group = campaign["channel_group"]
            if group in ("CRM",):
                continue
            if group == "Affiliate":
                _kind, _payout, _rate, typical = ref.AFFILIATE_PARTNERS[campaign["affiliate_partner"]]
                event_boost = 1.8 if campaign["event_id"] else 1.0
                clicks = int(rng.poisson(typical * self.settings.scale * demand * event_boost
                                         * (0.5 if campaign["event_id"] else 1.0)))
                for hour, n in enumerate(rng.multinomial(clicks, HOUR_SHAPE)):
                    for _ in range(int(rng.binomial(n, LANDING_RATE))):
                        landings.append((hour, int(rng.integers(0, 60)), campaign["campaign_id"], "All"))
                    if n:
                        spend_rows.append([day + pd.Timedelta(hours=hour), campaign["campaign_id"], "All",
                                           0.0, 0, n, 0, 0.0])
                continue
            planned = plan_today.get(campaign["campaign_id"], 0.0)
            if planned <= 0:
                continue
            _group, cpm, ctr, _source, _medium = ref.PAID_CHANNELS[campaign["channel"]]
            actual = planned * float(rng.lognormal(0, 0.12))
            cpm_today = cpm * (1.3 if mega_today else 1.0) * float(rng.uniform(0.92, 1.08))
            ctr_today = ctr * (1.15 if campaign["event_id"] else 1.0) * min(1.3, demand)
            hourly = actual * HOUR_SHAPE
            for hour in range(24):
                for region, share in zip(REGIONS, REGION_SHARE):
                    spend = hourly[hour] * share
                    impressions = int(spend / cpm_today * 1000)
                    clicks = int(rng.binomial(impressions, min(ctr_today, 0.5))) if impressions else 0
                    spend_rows.append([day + pd.Timedelta(hours=hour), campaign["campaign_id"], region,
                                       round(spend, 2), impressions, clicks, 0, 0.0])
                    for _ in range(int(rng.binomial(clicks, LANDING_RATE))):
                        landings.append((hour, int(rng.integers(0, 60)), campaign["campaign_id"], campaign["audience"]))
        return spend_rows, landings

    def tables(self, today: pd.Timestamp) -> dict[str, pd.DataFrame]:
        campaigns = pd.DataFrame(self.campaigns)
        if not campaigns.empty:
            campaigns["status"] = np.where(campaigns.end_date < today, "Completed", "Live")
        plan = pd.DataFrame(self.plan_rows, columns=["date", "campaign_id", "planned_spend", "target_impressions",
                                                     "target_clicks", "target_orders", "target_revenue"])
        return {"campaigns": campaigns, "marketing_plan": plan}
