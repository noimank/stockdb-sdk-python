"""集成测试：技术指标与指数合成（需本地 stockdb 服务）。"""

from math import isnan

import pytest

import stockdb_sdk as sdk

CODE = "000001"


def _rows_equal(a, b):
    """NaN 安全的行列表比较（指标前几行常为 NaN，nan != nan）。"""
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if set(x) != set(y):
            return False
        for k in x:
            vx, vy = x[k], y[k]
            if isinstance(vx, float) and isinstance(vy, float) and isnan(vx) and isnan(vy):
                continue
            if vx != vy:
                return False
    return True


def _closes(code, start):
    rows = sdk.get_data(code, start=start, end="N", fq="qfq", fields="date,close")
    return {r[0]: r[1] for r in rows}


def test_macd_shape():
    start = "20260601"
    rows = sdk.indicator("macd", CODE, start=start, end="N")
    closes = _closes(CODE, start)
    assert len(rows) == len(closes)
    assert [r["date"] for r in rows] == sorted(closes)
    assert set(rows[-1]) >= {"date", "dif", "dea", "macd"}


def test_ma_math():
    start = "20260601"
    rows = sdk.indicator("ma", CODE, start=start, end="N", n="5,10")
    closes = _closes(CODE, start)
    dates = sorted(closes)
    i = dates.index(rows[20]["date"])
    assert rows[20]["ma5"] == pytest.approx(
        sum(closes[d] for d in dates[i - 4:i + 1]) / 5, abs=1e-6)
    assert rows[20]["ma10"] == pytest.approx(
        sum(closes[d] for d in dates[i - 9:i + 1]) / 10, abs=1e-6)


def test_cross_signals():
    kw = dict(start="20260601", end="N")
    rows = sdk.indicator("ma", CODE, n=[5, 10], cross=True, **kw)
    assert set(rows[0]) == {"date", "cross"}
    assert {r["cross"] for r in rows} <= {-1, 0, 1}
    wv = sdk.indicator("ma", CODE, n=[5, 10], cross="with_value", **kw)
    assert set(wv[0]) >= {"date", "cross", "ma5", "ma10"}


def test_fields_input():
    kw = dict(start="20260601", end="N", n=5)
    on_open = sdk.indicator("ma", CODE, fields="open", **kw)
    on_close = sdk.indicator("ma", CODE, **kw)
    assert on_open[20]["ma5"] != on_close[20]["ma5"]


def test_batch_and_suffix():
    out = sdk.indicator("kdj", ["000001.SZ", "600633.SH"], start="20260701", end="N")
    assert set(out) == {CODE, "600633"}
    single = sdk.indicator("kdj", CODE, start="20260701", end="N")
    assert _rows_equal(out[CODE], single)


def test_errors():
    with pytest.raises(ValueError, match="unsupported indicator"):
        sdk.indicator("zhishu", CODE, end="N")  # 已独立为 index()
    with pytest.raises(ValueError, match="unsupported indicator"):
        sdk.indicator("nope", CODE, end="N")
    with pytest.raises(ValueError, match="cross only supports"):
        sdk.indicator("ma", CODE, end="N", cross=1)
    with pytest.raises(ValueError, match="fields only supports"):
        sdk.indicator("macd", CODE, end="N", fields="open")
    with pytest.raises(ValueError, match="length mismatch"):
        sdk.indicator("ma,kdj", CODE, end="N", n=[5])


def test_minute_indicator(minute_day):
    day, _ = minute_day
    rows = sdk.indicator("ma", CODE, start=day, end=day, frequency="1m", n=5)
    assert len(rows) > 100
    assert set(rows[0]) == {"date", "ma5"}


def test_index_synthesis():
    codes = [CODE, "600633"]
    rows = sdk.index(codes, start="20260601", end="N", method=1, base=1000)
    assert rows
    assert rows[0]["stock_count"] == 2
    assert set(rows[0]) == {"date", "open", "high", "low", "close", "pct_chg",
                            "volume", "amount", "stock_count"}
    # 首行基点被剔除：日期应为窗口内第二个交易日
    dates = sorted(_closes(codes[0], "20260601"))
    assert rows[0]["date"] == dates[1]
    for method in (2, 3, 4, 5):
        assert len(sdk.index(codes, start="20260601", end="N", method=method)) == len(rows)


def test_index_minute_guard():
    with pytest.raises(ValueError, match="method=1/3/4"):
        sdk.index([CODE], start="20260801", end="N", frequency="min", method=2)
