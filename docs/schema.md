# Data dictionary

Generated from `src/ecommerce_sim/schema.py`.

## Catalogue

### `product_master`

Products launched so far. Hierarchy: category -> sub_category -> article_type -> product -> SKU.

**Grain:** one row per product style

**Keys and links:** `product_id` primary key; `seller_id` -> sellers

| Column | Type | Notes |
|---|---|---|
| `product_id` | str | primary key |
| `source_product_id` | int64 |  |
| `product_name` | str |  |
| `brand_name` | str |  |
| `gender` | str |  |
| `category` | str |  |
| `sub_category` | str |  |
| `article_type` | str |  |
| `colour` | str |  |
| `season` | str |  |
| `usage` | str |  |
| `material` | str |  |
| `fit` | str |  |
| `size_type` | str | Apparel, Footwear or Free Size |
| `mrp` | float64 | list price (Rs, GST included) |
| `unit_cost` | float64 | what the shop pays the supplier |
| `gst_rate` | float64 | tax rate for this product |
| `seller_id` | str | -> sellers |
| `launch_date` | datetime64[us] | first day on sale |
| `discontinue_date` | datetime64[us] | last day on sale (empty if still sold) |
| `image_url` | str |  |
| `description` | str |  |
| `is_active` | bool |  |

### `product_skus`

Sellable units. Stock, purchase orders and sales are kept per SKU.

**Grain:** one row per size of a product

**Keys and links:** `sku_id` primary key; `product_id` -> product_master

| Column | Type | Notes |
|---|---|---|
| `sku_id` | str | primary key |
| `product_id` | str | -> product_master |
| `size` | str | XS-XXL, 6-11 or Free Size |
| `barcode` | str | EAN-13 |

### `sellers`

Brands and marketplace sellers. 1P = own stock, 3P-FBA = seller's stock in our warehouse, 3P-MFN = seller ships.

**Grain:** one row per seller

**Keys and links:** `seller_id` primary key; `home_warehouse_id` -> warehouses

| Column | Type | Notes |
|---|---|---|
| `seller_id` | str | primary key |
| `seller_name` | str |  |
| `seller_type` | str |  |
| `city` | str |  |
| `state` | str |  |
| `region` | str |  |
| `home_warehouse_id` | str | -> warehouses |
| `onboarding_date` | datetime64[us] |  |
| `rating` | float64 |  |
| `fulfillment_score` | float64 |  |
| `cancellation_rate` | float64 |  |
| `lead_time_days` | int64 | days from purchase order to delivery |
| `commission_rate` | float64 | marketplace fee |
| `is_active` | bool |  |

### `warehouses`

Fulfilment centres.

**Grain:** one row per warehouse

**Keys and links:** `warehouse_id` primary key

| Column | Type | Notes |
|---|---|---|
| `warehouse_id` | str | primary key |
| `city` | str |  |
| `region` | str |  |
| `capacity_units` | int64 |  |

## Service

### `agents`

Customer support staff.

**Grain:** one row per support agent

**Keys and links:** `agent_id` primary key

| Column | Type | Notes |
|---|---|---|
| `agent_id` | str | primary key |
| `agent_name` | str |  |
| `team` | str | Orders, Returns, Payments or Product Support |
| `location` | str |  |
| `language` | str |  |
| `hire_date` | datetime64[us] |  |

## Events & offers

### `sale_events`

Festivals and sales, live only between start_date and end_date (Prime members from prime_early_access_date).

**Grain:** one row per sale event

**Keys and links:** `event_id` primary key

| Column | Type | Notes |
|---|---|---|
| `event_id` | str | primary key |
| `name` | str |  |
| `event_type` | str |  |
| `start_date` | datetime64[us] |  |
| `end_date` | datetime64[us] |  |
| `prime_early_access_date` | datetime64[us] |  |
| `categories_on_offer` | str | All, Ethnic, Gifting, Women, Winter, Summer or Casual |
| `avg_extra_discount` | float64 | average extra discount on covered products |
| `demand_uplift` | float64 | how much busier the shop is during the event |
| `run_up_days` | int64 | days before the start when campaigns and browsing ramp up |

### `promotions`

Coupon codes: one or two per event plus always-on offers (FIRST100, BANK10, PRIME15).

**Grain:** one row per coupon

**Keys and links:** `promo_id` primary key; `event_id` -> sale_events; `code` used in sales.coupon_code

| Column | Type | Notes |
|---|---|---|
| `promo_id` | str | primary key |
| `code` | str | used in sales.coupon_code |
| `event_id` | str | -> sale_events |
| `offer_type` | str | % Off, Flat Off or Bank Offer |
| `value` | float64 |  |
| `min_order_value` | int64 |  |
| `max_discount` | int64 |  |
| `eligible_audience` | str |  |
| `eligible_payment_method` | str |  |
| `usage_limit_per_customer` | int64 | times one customer may use it |
| `start_date` | datetime64[us] |  |
| `end_date` | datetime64[us] |  |

## Marketing

### `campaigns`

Paid search, paid social, display, affiliate and CRM campaigns: monthly always-on ones and event ones.

**Grain:** one row per campaign

**Keys and links:** `campaign_id` primary key; `event_id` -> sale_events; `promo_code` -> promotions.code

| Column | Type | Notes |
|---|---|---|
| `campaign_id` | str | primary key |
| `event_id` | str | -> sale_events |
| `promo_code` | str | -> promotions.code |
| `affiliate_partner` | str | affiliate site (affiliate campaigns only) |
| `affiliate_type` | str |  |
| `payout_model` | str | CPS (% of sale), CPA (per new customer) or CPC (per click) |
| `payout_rate` | float64 |  |
| `utm_source` | str |  |
| `utm_medium` | str |  |
| `campaign_name` | str |  |
| `channel_group` | str | Paid Search, Paid Social, Display, Affiliate or CRM |
| `channel` | str |  |
| `campaign_type` | str | Brand, Generic, Performance, Prospecting, Retargeting, Event or Lifecycle |
| `objective` | str |  |
| `audience` | str |  |
| `offer_type` | str |  |
| `start_date` | datetime64[us] |  |
| `end_date` | datetime64[us] |  |
| `total_budget` | float64 |  |
| `utm_campaign` | str | matches clickstream.utm_campaign |
| `status` | str |  |

### `marketing_plan`

Planned budget and targets, set when the campaign is created (may run past today).

**Grain:** one row per paid campaign per day

**Keys and links:** `campaign_id` -> campaigns

| Column | Type | Notes |
|---|---|---|
| `date` | datetime64[us] |  |
| `campaign_id` | str | -> campaigns |
| `planned_spend` | float64 | Rs |
| `target_impressions` | int64 |  |
| `target_clicks` | int64 |  |
| `target_orders` | float64 |  |
| `target_revenue` | float64 |  |

### `marketing_spend`

Actual delivery. platform_conversions are what the ad platform reports (more than the shop sees). Affiliate spend = commissions and per-click fees; CRM spend = message costs.

**Grain:** one row per campaign per hour (per region for paid media)

**Keys and links:** `campaign_id` -> campaigns

| Column | Type | Notes |
|---|---|---|
| `date_hour` | datetime64[us] | start of the hour |
| `campaign_id` | str | -> campaigns |
| `region` | str |  |
| `spend` | float64 |  |
| `impressions` | int64 |  |
| `clicks` | int64 |  |
| `platform_conversions` | int64 |  |
| `platform_revenue` | float64 |  |

### `marketing_attribution`

Campaign visits in the 30 days before an order, with credit under four models (each sums to 1 per order). Orders with no campaign visit get one 'Direct/Organic' row.

**Grain:** one row per order per marketing touchpoint

**Keys and links:** `order_id` -> sales; `campaign_id` -> campaigns

| Column | Type | Notes |
|---|---|---|
| `order_id` | str | -> sales |
| `customer_id` | str |  |
| `order_at` | datetime64[us] |  |
| `touch_number` | int64 |  |
| `touch_at` | datetime64[us] |  |
| `campaign_id` | str | -> campaigns |
| `channel_group` | str |  |
| `credit_last_click` | float64 |  |
| `credit_first_click` | float64 |  |
| `credit_linear` | float64 |  |
| `credit_time_decay` | float64 | half-life 7 days |
| `order_revenue` | float64 |  |

### `crm_sends`

Email, push, SMS and WhatsApp messages. 10% of each campaign's audience is a control group that gets nothing.

**Grain:** one row per message per customer

**Keys and links:** `send_id` primary key; `campaign_id` -> campaigns; `customer_id` -> customers; `converted_order_id` -> sales.order_id (order from the visit that followed the click)

| Column | Type | Notes |
|---|---|---|
| `send_id` | str | primary key |
| `campaign_id` | str | -> campaigns |
| `customer_id` | str | -> customers |
| `channel` | str |  |
| `test_group` | str | treatment or control |
| `sent_at` | datetime64[us] |  |
| `delivered` | bool |  |
| `opened_at` | datetime64[us] |  |
| `clicked_at` | datetime64[us] |  |
| `converted_order_id` | str | -> sales.order_id (order from the visit that followed the click) |
| `unsubscribed` | bool |  |
| `cost` | float64 |  |

## Inventory & price

### `purchase_orders`

Initial stock for each SKU before launch, then replenishment when stock reaches the reorder point.

**Grain:** one row per purchase order (ordered and received in one row)

**Keys and links:** `po_id` primary key; `sku_id` -> product_skus; `warehouse_id` -> warehouses

| Column | Type | Notes |
|---|---|---|
| `po_id` | str | primary key |
| `sku_id` | str | -> product_skus |
| `product_id` | str |  |
| `seller_id` | str |  |
| `warehouse_id` | str | -> warehouses |
| `po_type` | str |  |
| `created_at` | datetime64[us] |  |
| `ordered_qty` | int64 |  |
| `unit_cost` | float64 |  |
| `expected_at` | datetime64[us] |  |
| `received_at` | datetime64[us] |  |
| `received_qty` | float64 |  |
| `rejected_qty` | float64 | units failing quality check |
| `po_status` | str | Open, Received or Short Received |

### `inventory_history`

Daily stock movements; closing = opening + received + returned_restocked - sold. Days without a row had no movement.

**Grain:** one row per SKU per day on which its stock moved

**Keys and links:** `sku_id` -> product_skus

| Column | Type | Notes |
|---|---|---|
| `date` | datetime64[us] |  |
| `sku_id` | str | -> product_skus |
| `product_id` | str |  |
| `warehouse_id` | str |  |
| `opening_stock` | int64 |  |
| `received` | int64 |  |
| `sold` | int64 |  |
| `returned_restocked` | int64 |  |
| `damaged` | int64 |  |
| `closing_stock` | int64 |  |
| `demand_units` | int64 | add-to-cart attempts, including when out of stock |
| `lost_sales_units` | int64 | demand that could not be served |
| `stock_status` | str |  |

### `inventory_live`

Stock at the end of today.

**Grain:** one row per SKU

**Keys and links:** `sku_id` -> product_skus

| Column | Type | Notes |
|---|---|---|
| `sku_id` | str | -> product_skus |
| `product_id` | str |  |
| `warehouse_id` | str |  |
| `on_hand_qty` | int64 |  |
| `inbound_qty` | int64 | on open purchase orders |
| `reorder_point` | int64 |  |
| `updated_at` | datetime64[us] |  |

### `price_history`

Selling price over time (valid_from .. valid_to; valid_to empty = current price).

**Grain:** one row per product per period with the same price

**Keys and links:** `product_id` -> product_master; `event_id` -> sale_events

| Column | Type | Notes |
|---|---|---|
| `product_id` | str | -> product_master |
| `valid_from` | datetime64[us] |  |
| `valid_to` | datetime64[us] |  |
| `mrp` | float64 |  |
| `selling_price` | float64 |  |
| `discount_pct` | float64 |  |
| `price_change_reason` | str | List Price, Everyday Markdown, Cost Change, Sale Event or Clearance |
| `event_id` | str | -> sale_events |

## Customers

### `customers`

Accounts (no personal data). account_status: Active, Dormant (not seen for 180 days) or Deleted.

**Grain:** one row per customer

**Keys and links:** `customer_id` primary key; `anonymous_id` visitor id before sign-up (-> clickstream); `signup_campaign_id` -> campaigns

| Column | Type | Notes |
|---|---|---|
| `customer_id` | str | primary key |
| `signup_at` | datetime64[us] |  |
| `signup_channel` | str | traffic source of the sign-up visit |
| `signup_campaign_id` | str | -> campaigns |
| `signup_method` | str |  |
| `signup_device` | str |  |
| `anonymous_id` | str | visitor id before sign-up (-> clickstream) |
| `city` | str |  |
| `state` | str |  |
| `region` | str |  |
| `city_tier` | str |  |
| `age_bracket` | str |  |
| `gender` | str |  |
| `is_prime` | bool |  |
| `prime_start_date` | datetime64[us] |  |
| `email_opt_in` | bool |  |
| `sms_opt_in` | bool |  |
| `push_opt_in` | bool |  |
| `whatsapp_opt_in` | bool |  |
| `account_status` | str |  |

### `customer_pii`

Personal data, kept separately (all fictional: example.com emails, +91 00000 numbers).

**Grain:** one row per customer

**Keys and links:** `customer_id` -> customers

| Column | Type | Notes |
|---|---|---|
| `customer_id` | str | -> customers |
| `full_name` | str |  |
| `email` | str |  |
| `phone` | str |  |
| `date_of_birth` | datetime64[us] |  |

### `customer_addresses`

Delivery addresses.

**Grain:** one row per address

**Keys and links:** `address_id` primary key; `customer_id` -> customers

| Column | Type | Notes |
|---|---|---|
| `address_id` | str | primary key |
| `customer_id` | str | -> customers |
| `label` | str |  |
| `address_line` | str |  |
| `city` | str |  |
| `state` | str |  |
| `region` | str |  |
| `city_tier` | str |  |
| `pincode` | str |  |
| `is_default` | bool |  |
| `nearest_warehouse_id` | str | -> warehouses |
| `created_at` | datetime64[us] |  |

### `auth_events`

signup, login and otp_failed events.

**Grain:** one row per sign-up / login attempt

**Keys and links:** `customer_id` -> customers; `session_id` -> clickstream

| Column | Type | Notes |
|---|---|---|
| `event_at` | datetime64[us] |  |
| `customer_id` | str | -> customers |
| `event_type` | str |  |
| `method` | str |  |
| `device` | str |  |
| `success` | bool |  |
| `session_id` | str | -> clickstream |

### `clickstream`

Every page view and action. Anonymous visitors have anonymous_id only; customer_id appears after sign-up.

**Grain:** one row per event in a visit

**Keys and links:** `event_id` primary key; `session_id` visit; `customer_id` -> customers; `product_id` -> product_master; `sku_id` -> product_skus; `campaign_id` -> campaigns; `order_id` -> sales (purchase events)

| Column | Type | Notes |
|---|---|---|
| `event_id` | str | primary key |
| `session_id` | str | visit |
| `anonymous_id` | str |  |
| `customer_id` | str | -> customers |
| `event_at` | datetime64[us] |  |
| `event_type` | str |  |
| `page_type` | str |  |
| `product_id` | str | -> product_master |
| `sku_id` | str | -> product_skus |
| `list_position` | float64 | position of the product when it was clicked from a list |
| `search_query` | str |  |
| `device` | str |  |
| `traffic_source` | str |  |
| `utm_source` | str |  |
| `utm_medium` | str |  |
| `utm_campaign` | str |  |
| `campaign_id` | str | -> campaigns |
| `order_id` | str | -> sales (purchase events) |
| `dwell_seconds` | float64 |  |

### `impressions`

Products shown on home recommendations, listings, search results and 'similar products'.

**Grain:** one row per product shown in a list

**Keys and links:** `page_event_id` -> clickstream.event_id (the page that showed it); `product_id` -> product_master

| Column | Type | Notes |
|---|---|---|
| `page_event_id` | str | -> clickstream.event_id (the page that showed it) |
| `session_id` | str |  |
| `anonymous_id` | str |  |
| `customer_id` | str |  |
| `shown_at` | datetime64[us] |  |
| `surface` | str |  |
| `position` | int64 | 1 = top |
| `product_id` | str | -> product_master |
| `clicked` | bool | the visitor opened it |
| `added_to_cart` | bool | then added it to the cart |

## Sales

### `sales`

Orders, payments, shipping, returns and refunds in one table. Each milestone has its own timestamp; order_status is the latest milestone reached today and updated_at the time of the last change. Exchange replacements are extra lines (line_type = Exchange) in the same order.

**Grain:** one row per transaction line (item in an order)

**Keys and links:** `transaction_id` primary key; `order_id` order; `shipment_id` parcel; `customer_id` -> customers; `sku_id` -> product_skus; `address_id` -> customer_addresses; `session_id` -> clickstream; `campaign_id` -> campaigns; `event_id` -> sale_events (price was an event price)

| Column | Type | Notes |
|---|---|---|
| `transaction_id` | str | primary key |
| `order_id` | str | order |
| `shipment_id` | str | parcel |
| `line_type` | str |  |
| `customer_id` | str | -> customers |
| `session_id` | str | -> clickstream |
| `address_id` | str | -> customer_addresses |
| `ship_city` | str |  |
| `ship_pincode` | str |  |
| `product_id` | str |  |
| `sku_id` | str | -> product_skus |
| `seller_id` | str |  |
| `warehouse_id` | str |  |
| `quantity` | int64 |  |
| `mrp` | float64 |  |
| `unit_price` | float64 |  |
| `gross_amount` | float64 |  |
| `coupon_code` | str |  |
| `coupon_discount` | float64 |  |
| `shipping_fee` | float64 |  |
| `net_amount` | float64 | gross_amount - coupon_discount + shipping_fee (GST included) |
| `tax_amount` | float64 |  |
| `gst_rate` | float64 |  |
| `unit_cost` | float64 |  |
| `payment_method` | str |  |
| `event_id` | str | -> sale_events (price was an event price) |
| `campaign_id` | str | -> campaigns |
| `traffic_source` | str |  |
| `device` | str |  |
| `affiliate_partner` | str |  |
| `affiliate_commission` | float64 | payable to the affiliate for this line |
| `is_first_order` | bool |  |
| `courier` | str |  |
| `promised_delivery_date` | datetime64[ns] |  |
| `placed_at` | datetime64[ns] |  |
| `confirmed_at` | datetime64[ns] |  |
| `shipped_at` | datetime64[ns] |  |
| `out_for_delivery_at` | datetime64[ns] |  |
| `delivered_at` | datetime64[ns] |  |
| `return_requested_at` | datetime64[ns] |  |
| `return_picked_up_at` | datetime64[ns] |  |
| `return_received_at` | datetime64[ns] |  |
| `exchanged_at` | datetime64[ns] |  |
| `refunded_at` | datetime64[ns] |  |
| `cancelled_at` | datetime64[ns] |  |
| `rto_at` | datetime64[ns] |  |
| `undelivered_at` | datetime64[ns] |  |
| `lost_at` | datetime64[ns] |  |
| `payment_collected_at` | datetime64[ns] |  |
| `cancel_reason` | str |  |
| `cancelled_by` | str |  |
| `return_reason` | str |  |
| `return_type` | str |  |
| `return_qc_result` | str |  |
| `refund_amount` | float64 |  |
| `replacement_transaction_id` | str |  |
| `size_fit` | str |  |
| `order_status` | str | Placed, Confirmed, Shipped, Out for Delivery, Delivered, Return Requested, Return Picked Up, Returned, Exchanged, Refunded, Cancelled, Returned to Origin, Undelivered or Lost |
| `updated_at` | datetime64[ns] |  |
| `payment_status` | str | Paid, Pending (COD not yet collected), Not Collected, Refunded or Not Applicable |

## Service

### `product_reviews`

Reviews written after delivery.

**Grain:** one row per review

**Keys and links:** `review_id` primary key; `transaction_id` -> sales

| Column | Type | Notes |
|---|---|---|
| `review_id` | str | primary key |
| `transaction_id` | str | -> sales |
| `order_id` | str |  |
| `customer_id` | str |  |
| `product_id` | str |  |
| `rating` | int64 |  |
| `title` | str |  |
| `review_text` | str |  |
| `aspect` | str |  |
| `sentiment` | str |  |
| `verified_purchase` | bool |  |
| `moderation_status` | str | Published or Rejected |
| `helpful_votes` | int64 |  |
| `reviewed_at` | datetime64[ns] |  |

### `support_contacts`

Customer contacts triggered by late deliveries, failed deliveries, refunds, exchanges and payment problems.

**Grain:** one row per contact (a ticket can have several)

**Keys and links:** `contact_id` primary key; `ticket_id` groups contacts; `transaction_id` -> sales; `agent_id` -> agents

| Column | Type | Notes |
|---|---|---|
| `contact_id` | str | primary key |
| `ticket_id` | str | groups contacts |
| `customer_id` | str |  |
| `order_id` | str |  |
| `transaction_id` | str | -> sales |
| `product_id` | str |  |
| `contact_at` | datetime64[ns] |  |
| `channel` | str |  |
| `transcript_text` | str |  |
| `issue_bucket_true` | str | true issue (for NLP evaluation) |
| `issue_category` | str | agent's tag (noisy) |
| `agent_id` | str | -> agents |
| `first_response_minutes` | int64 |  |
| `resolved_at` | datetime64[ns] |  |
| `csat` | float64 |  |
| `resolution_status` | str |  |
