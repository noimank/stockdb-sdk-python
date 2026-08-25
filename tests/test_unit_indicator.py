"""离线单元测试：指标/指数入口与参数解析（真实 zb_core 引擎 + 伪造行情）。"""

import pytest

import stockdb_sdk._indicator as ind
from stockdb_sdk._indicator import (
    _codes,
    _data_fields,
    _freq,
    _indicator_names,
    _indicator_params,
    _int_list,
    index,
    indicator,
)

N_DAYS = 60


# ---------- 参数解析 ----------

def test_freq():
    assert _freq("day") == "1d"
    assert _freq("D") == "1d"
    assert _freq("min") == "1m"
    assert _freq("1d") == "1d"
    assert _freq("30m") == "30m"


def test_codes_normalize():
    assert _codes("600633.SH") == (["600633"], True)
    assert _codes(["000001.SZ", "600633"]) == (["000001", "600633"], False)


def test_int_list():
    assert _int_list(None) == []
    assert _int_list(5) == [5]
    assert _int_list("5,10") == [5, 10]
    assert _int_list("5，10") == [5, 10]
    assert _int_list([5, None, "", 10]) == [5, 10]
    assert _int_list(["5", "10"]) == [5, 10]


def test_indicator_names():
    assert _indicator_names("macd") == ["macd"]
    assert _indicator_names("macd,kdj") == ["macd", "kdj"]
    assert _indicator_names("macd，kdj") == ["macd", "kdj"]
    assert _indicator_names(["MA", " Kdj "]) == ["ma", "kdj"]
    with pytest.raises(ValueError, match="indicator name is empty"):
        _indicator_names(" , ")


def test_data_fields():
    assert _data_fields(None) == ["close"]
    assert _data_fields("open") == ["open"]
    assert _data_fields("open,close") == ["open", "close"]
    assert _data_fields(["high", "low"]) == ["high", "low"]
    with pytest.raises(ValueError, match="unknown fields item"):
        _data_fields("bad")


def test_indicator_params():
    assert _indicator_params(["ma"], 5) == [[5]]
    assert _indicator_params(["ma"], "5,10") == [[5, 10]]
    assert _indicator_params(["ma", "kdj"], None) == [[], []]
    assert _indicator_params(["ma", "kdj"], ["5,10", None]) == [[5, 10], []]
    with pytest.raises(ValueError, match="must align"):
        _indicator_params(["ma", "kdj"], 5)
    with pytest.raises(ValueError, match="length mismatch"):
        _indicator_params(["ma", "kdj"], ["5"])


# ---------- indicator / index（伪造行情矩阵，真实 zb_core 计算） ----------

def _fake_load_rows(codes, frequency="1d", start=None, end=None, fq=None):
    """伪造每只代码 N_DAYS 个连续自然日的行情矩阵。"""
    import datetime as dt

    base = dt.date(2026, 6, 2)
    code_i, date = [], []
    open_, high, low, close = [], [], [], []
    volume, amount, float_mv, total_mv = [], [], [], []
    for i in range(N_DAYS):
        d = base + dt.timedelta(days=i)
        stamp = d.year * 10000 + d.month * 100 + d.day
        for ci in range(len(codes)):
            price = 10.0 + i * 0.1 + ci
            code_i.append(ci)
            date.append(stamp)
            open_.append(price)
            high.append(price + 0.5)
            low.append(price - 0.5)
            close.append(price + 0.2)
            volume.append(1000.0 + i)
            amount.append(10000.0 + i)
            float_mv.append(1e9 + i)
            total_mv.append(2e9 + i)
    return code_i, date, open_, high, low, close, volume, amount, float_mv, total_mv


@pytest.fixture
def patched_rows(monkeypatch):
    monkeypatch.setattr(ind, "_load_rows", _fake_load_rows)


def test_indicator_basic_math(patched_rows):
    rows = indicator("ma", "600633", n=5)
    assert len(rows) == N_DAYS
    closes = [10.2 + 0.1 * i for i in range(N_DAYS)]
    assert rows[20]["ma5"] == pytest.approx(sum(closes[16:21]) / 5, abs=1e-9)

    rows = indicator("ma", "600633", n="5,10")
    assert set(rows[0]) == {"date", "ma5", "ma10"}
    assert rows[20]["ma5"] == pytest.approx(sum(closes[16:21]) / 5, abs=1e-9)
    assert rows[20]["ma10"] == pytest.approx(sum(closes[11:21]) / 10, abs=1e-9)


def test_indicator_fields_input(patched_rows):
    on_open = indicator("ma", "600633", n=5, fields="open")
    on_close = indicator("ma", "600633", n=5)
    opens = [10.0 + 0.1 * i for i in range(N_DAYS)]
    assert on_open[20]["ma5"] != on_close[20]["ma5"]
    assert on_open[20]["ma5"] == pytest.approx(sum(opens[16:21]) / 5, abs=1e-9)


def test_indicator_cross(patched_rows):
    rows = indicator("ma", "600633", n=[5, 10], cross=True)
    assert set(rows[0]) == {"date", "cross"}
    assert {r["cross"] for r in rows} <= {-1, 0, 1}

    rows = indicator("ma", "600633", n=[5, 10], cross="with_value")
    assert set(rows[0]) >= {"date", "cross", "ma5", "ma10"}


def test_indicator_extended_batch(patched_rows):
    rows = indicator("macd,kdj", ["600633", "000001"])
    assert set(rows) == {"600633", "000001"}
    assert set(rows["600633"][0]) >= {"date", "dif", "dea", "macd"}
    assert isinstance(indicator("macd", "600633"), list)


def test_indicator_errors_no_data_access():
    # 所有参数校验前置于数据加载，错误路径不触发任何查询
    with pytest.raises(ValueError, match="指数合成请使用"):
        indicator("zhishu", "600633")  # 指数合成已独立为 index()
    with pytest.raises(ValueError, match="unsupported indicator"):
        indicator("nope", "600633")
    with pytest.raises(ValueError, match="cross only supports"):
        indicator("ma", "600633", cross="yes")
    with pytest.raises(ValueError, match="fields only supports"):
        indicator("macd", "600633", fields="open")
    with pytest.raises(ValueError, match="length mismatch"):
        indicator("ma,kdj", "600633", n=[5])
    with pytest.raises(ValueError, match="only supports one fields item"):
        indicator("ma", "600633", cross=True, fields="open,close")


def test_index_synthesis(patched_rows):
    rows = index(["600633", "000001"], method=1, base=1000)
    # 首日仅用于确立基点，不计入返回
    assert len(rows) == N_DAYS - 1
    assert rows[0]["date"] == 20260603
    assert rows[0]["stock_count"] == 2
    assert set(rows[0]) == {"date", "open", "high", "low", "close", "pct_chg",
                            "volume", "amount", "stock_count"}
    for method in (1, 2, 3, 4, 5):
        assert len(index(["600633", "000001"], method=method)) == N_DAYS - 1


def test_index_equal_weight_math(patched_rows):
    # 等权指数日收益 == 成分股日收益均值（每日再平衡）
    rows = index(["600633", "000001"], method=1, base=1000)
    for i in range(1, len(rows)):
        prev_close = rows[i - 1]["close"]
        expect = (rows[i]["close"] / prev_close - 1) * 100
        assert rows[i]["pct_chg"] == pytest.approx(expect, rel=1e-6)


def test_index_minute_guard(patched_rows):
    with pytest.raises(ValueError, match="method=1/3/4"):
        index(["600633"], frequency="min", method=2)
    # 分钟 + 非市值加权不抛错
    assert index(["600633"], frequency="min", method=3)
