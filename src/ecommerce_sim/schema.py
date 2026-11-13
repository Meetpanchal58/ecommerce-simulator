"""Data dictionary: what each table holds, its grain, keys and how it links to others.

Used to write docs/schema.md and the Text-to-SQL knowledge base, so the documentation
always matches the code.
"""

TABLES = {
    # ------------------------------------------------------------------ catalogue
    "product_master": {
        "group": "Catalogue", "grain": "one row per product style",
        "about": "Products launched so far. Hierarchy: category -> sub_category -> article_type -> product -> SKU.",
        "keys": {"product_id": "primary key", "seller_id": "-> sellers"},
        "columns": {"mrp": "list price (Rs, GST included)", "unit_cost": "what the shop pays the supplier",
                    "gst_rate": "tax rate for this product", "size_type": "Apparel, Footwear or Free Size",
                    "launch_date": "first day on sale", "discontinue_date": "last day on sale (empty if still sold)"},
    },
    "product_skus": {
        "group": "Catalogue", "grain": "one row per size of a product",
        "about": "Sellable units. Stock, purchase orders and sales are kept per SKU.",
        "keys": {"sku_id": "primary key", "product_id": "-> product_master"},
        "columns": {"size": "XS-XXL, 6-11 or Free Size", "barcode": "EAN-13"},
    },
    "sellers": {
        "group": "Catalogue", "grain": "one row per seller",
        "about": "Brands and marketplace sellers. 1P = own stock, 3P-FBA = seller's stock in our warehouse, 3P-MFN = seller ships.",
        "keys": {"seller_id": "primary key", "home_warehouse_id": "-> warehouses"},
        "columns": {"lead_time_days": "days from purchase order to delivery", "commission_rate": "marketplace fee"},
    },
    "warehouses": {"group": "Catalogue", "grain": "one row per warehouse", "about": "Fulfilment centres.",
                   "keys": {"warehouse_id": "primary key"}, "columns": {}},
    "agents": {"group": "Service", "grain": "one row per support agent", "about": "Customer support staff.",
               "keys": {"agent_id": "primary key"}, "columns": {"team": "Orders, Returns, Payments or Product Support"}},
    # ------------------------------------------------------------------ events and marketing
    "sale_events": {
        "group": "Events & offers", "grain": "one row per sale event",
        "about": "Festivals and sales, live only between start_date and end_date (Prime members from prime_early_access_date).",
        "keys": {"event_id": "primary key"},
        "columns": {"categories_on_offer": "All, Ethnic, Gifting, Women, Winter, Summer or Casual",
                    "avg_extra_discount": "average extra discount on covered products",
                    "demand_uplift": "how much busier the shop is during the event",
                    "run_up_days": "days before the start when campaigns and browsing ramp up"},
    },
    "promotions": {
        "group": "Events & offers", "grain": "one row per coupon",
        "about": "Coupon codes: one or two per event plus always-on offers (FIRST100, BANK10, PRIME15).",
        "keys": {"promo_id": "primary key", "event_id": "-> sale_events", "code": "used in sales.coupon_code"},
        "columns": {"offer_type": "% Off, Flat Off or Bank Offer", "usage_limit_per_customer": "times one customer may use it"},
    },
    "campaigns": {
        "group": "Marketing", "grain": "one row per campaign",
        "about": "Paid search, paid social, display, affiliate and CRM campaigns: monthly always-on ones and event ones.",
        "keys": {"campaign_id": "primary key", "event_id": "-> sale_events", "promo_code": "-> promotions.code"},
        "columns": {"channel_group": "Paid Search, Paid Social, Display, Affiliate or CRM",
                    "campaign_type": "Brand, Generic, Performance, Prospecting, Retargeting, Event or Lifecycle",
                    "affiliate_partner": "affiliate site (affiliate campaigns only)",
                    "payout_model": "CPS (% of sale), CPA (per new customer) or CPC (per click)",
                    "utm_campaign": "matches clickstream.utm_campaign"},
    },
    "marketing_plan": {
        "group": "Marketing", "grain": "one row per paid campaign per day",
        "about": "Planned budget and targets, set when the campaign is created (may run past today).",
        "keys": {"campaign_id": "-> campaigns"}, "columns": {"planned_spend": "Rs"},
    },
    "marketing_spend": {
        "group": "Marketing", "grain": "one row per campaign per hour (per region for paid media)",
        "about": "Actual delivery. platform_conversions are what the ad platform reports (more than the shop sees). "
                 "Affiliate spend = commissions and per-click fees; CRM spend = message costs.",
        "keys": {"campaign_id": "-> campaigns"}, "columns": {"date_hour": "start of the hour"},
    },
    "marketing_attribution": {
        "group": "Marketing", "grain": "one row per order per marketing touchpoint",
        "about": "Campaign visits in the 30 days before an order, with credit under four models (each sums to 1 per order). "
                 "Orders with no campaign visit get one 'Direct/Organic' row.",
        "keys": {"order_id": "-> sales", "campaign_id": "-> campaigns"},
        "columns": {"credit_time_decay": "half-life 7 days"},
    },
    "crm_sends": {
        "group": "Marketing", "grain": "one row per message per customer",
        "about": "Email, push, SMS and WhatsApp messages. 10% of each campaign's audience is a control group that gets nothing.",
        "keys": {"send_id": "primary key", "campaign_id": "-> campaigns", "customer_id": "-> customers",
                 "converted_order_id": "-> sales.order_id (order from the visit that followed the click)"},
        "columns": {"test_group": "treatment or control"},
    },
    # ------------------------------------------------------------------ inventory and price
    "purchase_orders": {
        "group": "Inventory & price", "grain": "one row per purchase order (ordered and received in one row)",
        "about": "Initial stock for each SKU before launch, then replenishment when stock reaches the reorder point.",
        "keys": {"po_id": "primary key", "sku_id": "-> product_skus", "warehouse_id": "-> warehouses"},
        "columns": {"po_status": "Open, Received or Short Received", "rejected_qty": "units failing quality check"},
    },
    "inventory_history": {
        "group": "Inventory & price", "grain": "one row per SKU per day on which its stock moved",
        "about": "Daily stock movements; closing = opening + received + returned_restocked - sold. "
                 "Days without a row had no movement.",
        "keys": {"sku_id": "-> product_skus"},
        "columns": {"demand_units": "add-to-cart attempts, including when out of stock",
                    "lost_sales_units": "demand that could not be served"},
    },
    "inventory_live": {"group": "Inventory & price", "grain": "one row per SKU", "about": "Stock at the end of today.",
                       "keys": {"sku_id": "-> product_skus"}, "columns": {"inbound_qty": "on open purchase orders"}},
    "price_history": {
        "group": "Inventory & price", "grain": "one row per product per period with the same price",
        "about": "Selling price over time (valid_from .. valid_to; valid_to empty = current price).",
        "keys": {"product_id": "-> product_master", "event_id": "-> sale_events"},
        "columns": {"price_change_reason": "List Price, Everyday Markdown, Cost Change, Sale Event or Clearance"},
    },
    # ------------------------------------------------------------------ customers and behaviour
    "customers": {
        "group": "Customers", "grain": "one row per customer",
        "about": "Accounts (no personal data). account_status: Active, Dormant (not seen for 180 days) or Deleted.",
        "keys": {"customer_id": "primary key", "anonymous_id": "visitor id before sign-up (-> clickstream)",
                 "signup_campaign_id": "-> campaigns"},
        "columns": {"signup_channel": "traffic source of the sign-up visit"},
    },
    "customer_pii": {"group": "Customers", "grain": "one row per customer",
                     "about": "Personal data, kept separately (all fictional: example.com emails, +91 00000 numbers).",
                     "keys": {"customer_id": "-> customers"}, "columns": {}},
    "customer_addresses": {"group": "Customers", "grain": "one row per address",
                           "about": "Delivery addresses.", "keys": {"address_id": "primary key", "customer_id": "-> customers"},
                           "columns": {"nearest_warehouse_id": "-> warehouses"}},
    "auth_events": {"group": "Customers", "grain": "one row per sign-up / login attempt",
                    "about": "signup, login and otp_failed events.", "keys": {"customer_id": "-> customers",
                                                                             "session_id": "-> clickstream"},
                    "columns": {}},
    "clickstream": {
        "group": "Customers", "grain": "one row per event in a visit",
        "about": "Every page view and action. Anonymous visitors have anonymous_id only; customer_id appears after sign-up.",
        "keys": {"event_id": "primary key", "session_id": "visit", "customer_id": "-> customers",
                 "product_id": "-> product_master", "sku_id": "-> product_skus", "campaign_id": "-> campaigns",
                 "order_id": "-> sales (purchase events)"},
        "columns": {"list_position": "position of the product when it was clicked from a list"},
    },
    "impressions": {
        "group": "Customers", "grain": "one row per product shown in a list",
        "about": "Products shown on home recommendations, listings, search results and 'similar products'.",
        "keys": {"page_event_id": "-> clickstream.event_id (the page that showed it)", "product_id": "-> product_master"},
        "columns": {"position": "1 = top", "clicked": "the visitor opened it", "added_to_cart": "then added it to the cart"},
    },
    # ------------------------------------------------------------------ sales and service
    "sales": {
        "group": "Sales", "grain": "one row per transaction line (item in an order)",
        "about": "Orders, payments, shipping, returns and refunds in one table. Each milestone has its own timestamp; "
                 "order_status is the latest milestone reached today and updated_at the time of the last change. "
                 "Exchange replacements are extra lines (line_type = Exchange) in the same order.",
        "keys": {"transaction_id": "primary key", "order_id": "order", "shipment_id": "parcel", "customer_id": "-> customers",
                 "sku_id": "-> product_skus", "address_id": "-> customer_addresses", "session_id": "-> clickstream",
                 "campaign_id": "-> campaigns", "event_id": "-> sale_events (price was an event price)"},
        "columns": {"net_amount": "gross_amount - coupon_discount + shipping_fee (GST included)",
                    "order_status": "Placed, Confirmed, Shipped, Out for Delivery, Delivered, Return Requested, "
                                    "Return Picked Up, Returned, Exchanged, Refunded, Cancelled, Returned to Origin, "
                                    "Undelivered or Lost",
                    "payment_status": "Paid, Pending (COD not yet collected), Not Collected, Refunded or Not Applicable",
                    "affiliate_commission": "payable to the affiliate for this line"},
    },
    "product_reviews": {"group": "Service", "grain": "one row per review",
                        "about": "Reviews written after delivery.", "keys": {"review_id": "primary key",
                                                                              "transaction_id": "-> sales"},
                        "columns": {"moderation_status": "Published or Rejected"}},
    "support_contacts": {
        "group": "Service", "grain": "one row per contact (a ticket can have several)",
        "about": "Customer contacts triggered by late deliveries, failed deliveries, refunds, exchanges and payment problems.",
        "keys": {"contact_id": "primary key", "ticket_id": "groups contacts", "transaction_id": "-> sales",
                 "agent_id": "-> agents"},
        "columns": {"issue_bucket_true": "true issue (for NLP evaluation)", "issue_category": "agent's tag (noisy)"},
    },
}


def markdown(column_types: dict | None = None) -> str:
    """docs/schema.md content. column_types: {table: {column: dtype}} from real data, if available."""
    lines = ["# Data dictionary", "", "Generated from `src/ecommerce_sim/schema.py`.", ""]
    group = None
    for name, info in TABLES.items():
        if info["group"] != group:
            group = info["group"]
            lines += [f"## {group}", ""]
        lines += [f"### `{name}`", "", f"{info['about']}", "", f"**Grain:** {info['grain']}", ""]
        if info["keys"]:
            lines += ["**Keys and links:** " + "; ".join(f"`{k}` {v}" for k, v in info["keys"].items()), ""]
        types = (column_types or {}).get(name, {})
        if types:
            lines += ["| Column | Type | Notes |", "|---|---|---|"]
            notes = {**{k: v for k, v in info["keys"].items()}, **info["columns"]}
            lines += [f"| `{col}` | {dtype} | {notes.get(col, '')} |" for col, dtype in types.items()]
            lines.append("")
    return "\n".join(lines)
