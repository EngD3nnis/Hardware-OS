from app.forecasting import forecast_series, series_from_trend


def test_flat_history_projects_flat():
    f = forecast_series([100.0] * 14, horizon=7)
    assert f["horizon_days"] == 7
    assert f["projected_total"] == round(sum(f["projected_daily"]), 2)
    # ~flat series -> each projected day near 100
    assert all(abs(v - 100.0) < 1.0 for v in f["projected_daily"])
    assert f["confidence_band"]["low"] <= f["projected_total"] <= f["confidence_band"]["high"]


def test_upward_trend_detected():
    history = [float(i) for i in range(1, 21)]  # 1..20 rising
    f = forecast_series(history, horizon=5)
    assert f["trend_per_day"] > 0
    # next-day projection should exceed the last observed value's neighbourhood
    assert f["projected_daily"][0] > 15


def test_empty_history_is_safe():
    f = forecast_series([], horizon=10)
    assert f["method"] == "insufficient_data"
    assert f["projected_total"] == 0.0
    assert f["projected_daily"] == [0.0] * 10


def test_no_negative_projections():
    history = [50, 40, 30, 20, 10, 5, 0]  # steep decline
    f = forecast_series(history, horizon=10)
    assert all(v >= 0 for v in f["projected_daily"])


def test_series_from_trend_extracts_amounts():
    points = [{"date": "2026-06-01", "amount": "10"}, {"date": "2026-06-02", "amount": 20}]
    assert series_from_trend(points) == [10.0, 20.0]
