"""Text-to-SQL material: a schema knowledge base and verified question/SQL pairs.

`ecommerce-sim textsql` writes, under data/derived/:
    text_to_sql_kb.json     one entry per table: description, grain, keys and columns
    text_to_sql_eval.json   questions with gold SQL, each executed on the data (needs duckdb)
"""
import json

from .schema import TABLES
from .store import Store

QUESTIONS = [
    ("easy", "How many customers have signed up?", "SELECT COUNT(*) FROM customers"),
    ("easy", "How many products are on sale today?", "SELECT COUNT(*) FROM product_master WHERE is_active"),
    ("easy", "How many orders were placed?", "SELECT COUNT(DISTINCT order_id) FROM sales WHERE line_type = 'Sale'"),
    ("easy", "Which payment methods are used most?",
     "SELECT payment_method, COUNT(DISTINCT order_id) AS orders FROM sales GROUP BY 1 ORDER BY orders DESC"),
    ("easy", "How many customers are Prime members?", "SELECT COUNT(*) FROM customers WHERE is_prime"),
    ("medium", "What is the average order value of delivered orders?",
     "SELECT SUM(net_amount) / COUNT(DISTINCT order_id) FROM sales WHERE delivered_at IS NOT NULL AND line_type = 'Sale'"),
    ("medium", "What share of delivered items were returned?",
     "SELECT AVG(CASE WHEN return_requested_at IS NOT NULL THEN 1.0 ELSE 0 END) FROM sales WHERE delivered_at IS NOT NULL"),
    ("medium", "Which return reasons are most common?",
     "SELECT return_reason, COUNT(*) AS lines FROM sales WHERE return_reason IS NOT NULL GROUP BY 1 ORDER BY lines DESC"),
    ("medium", "What is revenue by product category?",
     "SELECT p.category, SUM(s.net_amount) AS revenue FROM sales s JOIN product_master p USING (product_id) "
     "WHERE s.cancelled_at IS NULL GROUP BY 1 ORDER BY revenue DESC"),
    ("medium", "How many orders came from each traffic source?",
     "SELECT traffic_source, COUNT(DISTINCT order_id) AS orders FROM sales GROUP BY 1 ORDER BY orders DESC"),
    ("medium", "What is the click-through rate of each listing position?",
     "SELECT position, AVG(CASE WHEN clicked THEN 1.0 ELSE 0 END) AS ctr FROM impressions GROUP BY 1 ORDER BY 1"),
    ("medium", "Which SKUs are out of stock right now?",
     "SELECT sku_id, product_id FROM inventory_live WHERE on_hand_qty <= 0"),
    ("medium", "How much was spent on each marketing channel?",
     "SELECT c.channel, SUM(m.spend) AS spend FROM marketing_spend m JOIN campaigns c USING (campaign_id) "
     "GROUP BY 1 ORDER BY spend DESC"),
    ("hard", "What is the conversion rate (orders per visit) by device?",
     "SELECT device, COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN session_id END) * 1.0 / "
     "COUNT(DISTINCT session_id) AS conversion FROM clickstream GROUP BY 1 ORDER BY conversion DESC"),
    ("hard", "How much revenue did each sale event bring?",
     "SELECT e.name, SUM(s.net_amount) AS revenue FROM sales s JOIN sale_events e ON s.event_id = e.event_id "
     "GROUP BY 1 ORDER BY revenue DESC"),
    ("hard", "Did CRM messages raise conversion compared with the control group?",
     "SELECT test_group, AVG(CASE WHEN converted_order_id IS NOT NULL THEN 1.0 ELSE 0 END) AS conversion, COUNT(*) "
     "FROM crm_sends GROUP BY 1"),
    ("hard", "Which campaigns get the most last-click credited revenue?",
     "SELECT campaign_id, channel_group, SUM(credit_last_click * order_revenue) AS revenue FROM marketing_attribution "
     "GROUP BY 1, 2 ORDER BY revenue DESC LIMIT 10"),
    ("hard", "What share of purchase orders arrived late?",
     "SELECT AVG(CASE WHEN received_at > expected_at THEN 1.0 ELSE 0 END) FROM purchase_orders WHERE received_at IS NOT NULL"),
    ("hard", "Which couriers deliver late most often?",
     "SELECT courier, AVG(CASE WHEN CAST(delivered_at AS DATE) > CAST(promised_delivery_date AS DATE) THEN 1.0 ELSE 0 END) "
     "AS late_share FROM sales WHERE delivered_at IS NOT NULL GROUP BY 1 ORDER BY late_share DESC"),
    ("hard", "What is the platform-reported versus shop-recorded orders for Meta campaigns?",
     "SELECT SUM(m.platform_conversions) AS platform, (SELECT COUNT(DISTINCT order_id) FROM sales s JOIN campaigns c2 "
     "USING (campaign_id) WHERE c2.channel = 'Meta') AS shop FROM marketing_spend m JOIN campaigns c USING (campaign_id) "
     "WHERE c.channel = 'Meta'"),
]


def build(data_dir) -> dict:
    store = Store(data_dir)
    out = store.root / "derived"
    out.mkdir(parents=True, exist_ok=True)
    kb = []
    for name, info in TABLES.items():
        columns = list(store.dtypes(name))
        kb.append({"table": name, "description": info["about"], "grain": info["grain"], "keys": info["keys"],
                   "column_notes": info["columns"], "columns": columns})
    (out / "text_to_sql_kb.json").write_text(json.dumps(kb, indent=2))
    try:
        import duckdb
    except ImportError:
        print("duckdb not installed: wrote the knowledge base only (pip install 'ecommerce-simulator[sql]').")
        return {"kb": len(kb), "questions": 0}
    con = duckdb.connect()
    for name in TABLES:
        single = store.root / f"{name}.parquet"
        path = single if single.exists() else store.root / name / "month=*" / "part.parquet"
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
    kept = []
    for number, (level, question, sql) in enumerate(QUESTIONS, 1):
        try:
            rows = con.execute(sql).fetchall()
        except Exception as error:
            print(f"skipped q{number:03d}: {error}")
            continue
        kept.append({"id": f"q{number:03d}", "difficulty": level, "question": question, "gold_sql": sql,
                     "returns_rows": bool(rows)})
    (out / "text_to_sql_eval.json").write_text(json.dumps({"questions": kept}, indent=2))
    print(f"Text-to-SQL: {len(kb)} tables, {len(kept)}/{len(QUESTIONS)} verified questions in {out}")
    return {"kb": len(kb), "questions": len(kept)}
