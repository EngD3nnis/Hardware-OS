from app.inventory import predict_stockouts


def _item(sku, qty, avg_daily, reorder=0):
    return {
        "product_id": sku, "sku": sku, "name": sku,
        "quantity": qty, "avg_daily_sales": avg_daily, "reorder_level": reorder,
    }


def test_flags_products_within_horizon():
    items = [
        _item("FAST", qty=10, avg_daily=2.0),    # 5 days -> at risk in 14
        _item("SLOW", qty=100, avg_daily=1.0),   # 100 days -> not at risk
        _item("DEAD", qty=50, avg_daily=0.0),    # no demand -> excluded
    ]
    risks = predict_stockouts(items, horizon_days=14)
    skus = [r["sku"] for r in risks]
    assert skus == ["FAST"]
    assert risks[0]["days_to_stockout"] == 5.0


def test_sorted_by_soonest_stockout():
    # days-to-stockout: A=20/2=10, B=6/2=3, C=30/5=6 -> B, C, A
    items = [_item("A", 20, 2.0), _item("B", 6, 2.0), _item("C", 30, 5.0)]
    risks = predict_stockouts(items, horizon_days=14)
    assert [r["sku"] for r in risks] == ["B", "C", "A"]


def test_suggested_reorder_covers_horizon_and_buffer():
    risks = predict_stockouts([_item("X", qty=5, avg_daily=2.0, reorder=4)], horizon_days=10)
    # need ~ 2*10 + 4 - 5 = 19
    assert risks[0]["suggested_reorder_qty"] == 19
