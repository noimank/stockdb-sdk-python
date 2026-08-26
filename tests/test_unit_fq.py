"""复权折算单元测试（因子直接注入，不依赖服务）。"""

from stockdb_sdk import _fq


def _row(date, close):
    return {"code": "600000", "date": date, "open": close, "high": close,
            "low": close, "close": close, "pre_close": close}


def _factors(events):
    """events: [(日期str, cum)] -> _fq.Entry 形态的因子表。"""
    items = sorted(events)
    return {"600000": ([d for d, _ in items], [c for _, c in items])}


def test_qfq_anchor_at_latest():
    factors = _factors([("20260101", 2.0)])
    rows = [_row(20251231, 10.0), _row(20260105, 8.0)]
    out = _fq.apply(rows, "600000", "qfq", factors)
    assert out[0]["close"] == 5.0      # 事件前：10 × 1 / 2
    assert out[1]["close"] == 8.0      # 事件后即锚点：ratio = 1，原样


def test_hfq_multiplies_cum():
    factors = _factors([("20260101", 2.0)])
    rows = [_row(20251231, 10.0), _row(20260105, 8.0)]
    out = _fq.apply(rows, "600000", "hfq", factors)
    assert out[0]["close"] == 10.0     # 事件前 cum = 1
    assert out[1]["close"] == 16.0     # 事件后 cum = 2


def test_multi_events_pick_latest_le_date():
    factors = _factors([("20260101", 2.0), ("20260201", 4.0)])
    out = _fq.apply([_row(20260115, 10.0)], "600000", "hfq", factors)
    assert out[0]["close"] == 20.0     # 取 <= 当日的 20260101 事件


def test_stock_rounds_2_fund_rounds_3():
    stock_factors = {"600000": (["20260101"], [3.0])}
    fund_factors = {"159001": (["20260101"], [3.0])}
    stock = _fq.apply([_row(20260105, 10.557)], "600000", "hfq", stock_factors)[0]
    fund = _fq.apply([_row(20260105, 10.557)], "159001", "hfq", fund_factors)[0]
    assert (stock["close"], fund["close"]) == (31.67, 31.671)


def test_no_factor_returns_same_list():
    rows = [_row(20260105, 10.0)]
    assert _fq.apply(rows, "999999", "qfq", {}) is rows


def test_applies_in_place():
    # 行对象为本次调用独有，原地折算避免翻倍峰值内存
    factors = _factors([("20260101", 2.0)])
    rows = [_row(20260105, 10.0)]
    out = _fq.apply(rows, "600000", "hfq", factors)
    assert out is rows
    assert rows[0]["close"] == 20.0


def test_minute_date_uses_first_8_digits():
    factors = _factors([("20260101", 2.0)])
    rows = [{"code": "600000", "date": 20260105103000, "close": 10.0,
             "open": 10.0, "high": 10.0, "low": 10.0, "pre_close": 10.0}]
    out = _fq.apply(rows, "600000", "hfq", factors)
    assert out[0]["close"] == 20.0


def test_parse_bulk_keeps_only_needed():
    pairs = [
        ["复权:000001:19910430", {"cum": 1.41}],
        ["复权:000001:19920323", {"cum": 2.128}],
        ["复权:600633:19930705", {"cum": 1.0}],
    ]
    out = _fq._parse_bulk(pairs, frozenset({"000001"}))
    assert set(out) == {"000001"}
    dates, cums = out["000001"]
    assert dates == ["19910430", "19920323"]
    assert cums == [1.41, 2.128]
