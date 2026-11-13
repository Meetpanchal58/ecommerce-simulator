# How it works

## One day at a time

The simulator runs the shop day by day from the opening day (1 Jan 2025). Within a day:

1. **Campaigns** that start today are created: monthly always-on campaigns on the 1st, event
   campaigns a few days before each sale. Each paid campaign gets a daily plan (budget and
   targets).
2. **Prices** are set: list price, everyday markdown, a one-off cost-driven price rise (1 Feb
   2025), event discounts on event days only, and clearance in the last 30 days before a
   product is discontinued. Every change opens a new row in `price_history`.
3. **Stock** arrives: initial purchase orders for products launching today, replenishment
   orders due today (some arrive short, some units fail quality checks), and units coming
   back from cancellations, refused deliveries and returns.
4. **Visitors** arrive from ad clicks (hourly delivery, with UTM tags), affiliate clicks,
   CRM message clicks, returning customers and new visitors. Each visit is a session of
   events: landing page, search or listing (products shown are logged in `impressions`),
   clicks (more likely near the top: position bias), size choice, stock check, cart,
   sign-up (required at checkout), payment attempts (prepaid ones sometimes fail and are
   retried) and the order.
5. **Orders.** When an order is placed, each item's whole future is decided: cancellation
   (by customer or seller), shipping (courier, promised date, festival backlogs), delivery
   or failure (cash-on-delivery refusals, undelivered, lost), return within 7 days (wrong
   size and low quality raise the chance), refund, store credit or exchange (a replacement
   size ships if in stock), review, and support tickets. These events carry future
   timestamps and are revealed only when that date is reached.
6. **End of day.** Prime sign-ups; platform-reported conversions for each campaign hour
   (platforms over-report); stock is counted and SKUs at their reorder point get a new
   purchase order.

## What `sales` looks like on a given day

`sales` has one row per transaction line with a timestamp per milestone (`placed_at`,
`shipped_at`, `delivered_at`, `return_requested_at`, `refunded_at`, ...). Milestones after
"today" are empty, `order_status` is the latest milestone reached, and `updated_at` is when
the row last changed. So a line placed yesterday shows "Shipped" today and "Delivered" a
few days later, as in a real order system. A daily extract can load just the rows whose
`updated_at` is new.

## load and increment

Each day and each part of the simulation (marketing, visits, pricing, ...) has its own
random stream that depends only on the seed, the part and the date. The simulator's
memory (customers, stock, open purchase orders, future order events, ...) is saved after
every run. So:

- `load` deletes old data and simulates from the opening day to today;
- `increment` reloads the memory and simulates only the missing days, appending new days
  to the monthly event files and rewriting the whole tables;
- running `load` to March and `increment` to June gives exactly the same data as running
  `load` to June. A test checks this for every table.

## What is hidden

Each customer has a hidden profile: favourite category, colour and style, price
sensitivity, deal seeking, how often they visit and buy, return tendency, sizes and how
sure they are of them, interest that fades after their last order, Prime and cash-on-
delivery leanings. Products have a hidden quality. Shoppers click and buy in proportion to
a taste score built from these. The profiles and qualities are written to `_ground_truth/`
only; nothing in the normal tables reveals them directly.

## Derived tables

`ecommerce-sim derive` builds analysis tables point-in-time, never using information from
after each snapshot:

- `customer_monthly_features`: orders, revenue, recency, returns, visits and support
  contacts as of the 1st of each month;
- `churn_labels`: whether a customer ordered in the 90 days after each snapshot;
- `product_affinity`: products bought together and viewed together, with lift;
- `mmm_weekly`: weekly revenue next to weekly spend per channel and sale days.

## Checks

`ecommerce-sim validate` (run after every load and increment) checks, among others:
unique keys and every link between tables; lifecycle timestamps in order; nothing before
sign-up or launch and nothing after today; gross/net/refund amounts; sold prices equal to
`price_history`; coupons used only while live; stock never negative and balancing every
day; goods received equal to purchase orders; units sold equal to sales; every order has
its purchase event; clicked impressions have a product view; the CRM control group gets
nothing; attribution credits sum to 1.
