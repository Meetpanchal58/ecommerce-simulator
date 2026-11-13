"""End-to-end tests on a small shop (a few hundred products and customers)."""
import shutil

import pandas as pd
import pytest

from ecommerce_sim.derive import derive_all
from ecommerce_sim.settings import Settings
from ecommerce_sim.simulate import run
from ecommerce_sim.store import Store
from ecommerce_sim.validate import TABLES, validate

SMALL = dict(n_products=250, n_sellers=30, traffic_scale=0.05, daily_new_visitors=15)
QUIET = lambda *args, **kwargs: None  # noqa: E731


def small(tmp_path, name, today):
    return Settings(data_dir=tmp_path / name, today=today, **SMALL)


@pytest.fixture(scope="module")
def shops(tmp_path_factory):
    """One shop loaded straight to 20 Feb, and one loaded to 25 Jan then incremented to 20 Feb."""
    root = tmp_path_factory.mktemp("shops")
    run(small(root, "full", "2025-02-20"), "load", progress=QUIET)
    run(small(root, "stepwise", "2025-01-25"), "load", progress=QUIET)
    run(small(root, "stepwise", "2025-02-20"), "increment", progress=QUIET)
    yield root
    shutil.rmtree(root, ignore_errors=True)


def test_all_validation_checks_pass(shops):
    assert validate(shops / "full", print_results=False)
    assert validate(shops / "stepwise", print_results=False)


@pytest.mark.parametrize("table", TABLES)
def test_increment_gives_the_same_data_as_one_load(shops, table):
    full = Store(shops / "full").read(table)
    stepwise = Store(shops / "stepwise").read(table)
    assert len(full) > 0 or table in ("auth_events",), f"{table} is empty"
    pd.testing.assert_frame_equal(full.reset_index(drop=True), stepwise.reset_index(drop=True), check_dtype=False)


def test_increment_skips_when_up_to_date(shops):
    messages = []
    result = run(small(shops, "full", "2025-02-20"), "increment", progress=messages.append)
    assert result["days"] == 0
    assert "Already up to date" in messages[0]


def test_increment_needs_existing_data(tmp_path):
    with pytest.raises(RuntimeError, match="load"):
        run(small(tmp_path, "empty", "2025-01-10"), "increment", progress=QUIET)


def test_order_status_only_shows_milestones_reached(shops):
    sales = Store(shops / "full").read("sales")
    today = pd.Timestamp("2025-02-20") + pd.Timedelta(days=1)
    for column in ("delivered_at", "refunded_at", "return_requested_at", "shipped_at"):
        assert (sales[column].dropna() < today).all()
    recent = sales[sales.placed_at >= "2025-02-10"]
    assert len(recent) > 0
    assert not recent.order_status.isin(["Delivered", "Refunded"]).all()


def test_sales_happen_only_on_event_days_at_event_prices(shops):
    store = Store(shops / "full")
    prices = store.read("price_history")
    events = store.read("sale_events").set_index("event_id")
    on_sale = prices.dropna(subset=["event_id"])
    starts = on_sale.event_id.map(events.start_date)
    ends = on_sale.event_id.map(events.end_date)
    assert (on_sale.valid_from >= starts).all()
    assert (on_sale.valid_to.fillna(ends) <= ends).all()


def test_derived_tables(shops):
    derive_all(shops / "full")
    features = pd.read_parquet(shops / "full" / "derived" / "customer_monthly_features.parquet")
    assert set(features.snapshot_date.dt.day) == {1}
    affinity = pd.read_parquet(shops / "full" / "derived" / "product_affinity.parquet")
    assert set(affinity.affinity_type) <= {"co_purchase", "co_view"}
    assert (pd.read_parquet(shops / "full" / "derived" / "mmm_weekly.parquet").revenue >= 0).all()
