"""周期聚合单元测试（纯函数，不依赖服务）。"""

from stockdb_sdk._aggregate import resample_daily, resample_minutes


def _ts(day: int, hhmm: int) -> int:
    return day * 1000000 + hhmm * 100


def _m(ts, o, c, h, l, v=100):
    return {"code": "600633", "date": ts, "open": o, "close": c,
            "high": h, "low": l, "volume": v, "amount": v * 10.0,
            "pre_close": o}


def _susp(ts):
    """停牌占位 bar 形态一：OHLC 全 None、volume=0（服务端分钟表实测形态）。"""
    return {"code": "600633", "date": ts, "open": None, "close": None,
            "high": None, "low": None, "volume": 0, "amount": 0.0,
            "pre_close": None}


def _susp0(ts):
    """停牌占位 bar 形态二：OHLC 全 0、volume=0、pre_close=None。"""
    return {"code": "600633", "date": ts, "open": 0, "close": 0,
            "high": 0, "low": 0, "volume": 0, "amount": 0.0,
            "pre_close": None}


class TestMinute:
    def test_5m_basic(self):
        rows = [_m(_ts(20260625, 930 + i), 10, 10 + i, 11, 9) for i in range(5)]
        out = resample_minutes(rows, 5)
        assert len(out) == 1
        bar = out[0]
        assert bar["date"] == _ts(20260625, 930)
        assert bar["open"] == 10 and bar["close"] == 14
        assert bar["high"] == 11 and bar["low"] == 9
        assert bar["volume"] == 500 and bar["amount"] == 5000.0

    def test_5m_two_buckets(self):
        rows = [_m(_ts(20260625, 930 + i), 10, 10, 10, 10) for i in range(7)]
        out = resample_minutes(rows, 5)
        assert [b["date"] for b in out] == [_ts(20260625, 930),
                                            _ts(20260625, 935)]
        assert [b["volume"] for b in out] == [500, 200]

    def test_60m_session_aware(self):
        # 09:30-10:29 一段、10:30-11:29 一段、13:00-13:59 一段
        rows = [_m(_ts(20260625, hhmm), 10, 10, 10, 10)
                for hhmm in (930, 945, 1000, 1029, 1030, 1045, 1300, 1315)]
        out = resample_minutes(rows, 60)
        assert [b["date"] for b in out] == [_ts(20260625, 930),
                                            _ts(20260625, 1030),
                                            _ts(20260625, 1300)]

    def test_closing_minutes_not_dropped(self):
        # 11:30 / 15:00 的收盘 K 线并入前一小时段最后一桶，不丢数据
        rows = [_m(_ts(20260625, hhmm), 10, 10, 10, 10)
                for hhmm in (1129, 1130, 1459, 1500)]
        out = resample_minutes(rows, 30)
        assert [b["date"] for b in out] == [_ts(20260625, 1100),
                                            _ts(20260625, 1430)]
        assert [b["volume"] for b in out] == [200, 200]

    def test_lunch_boundary_not_merged(self):
        # 11:29 与 13:00 分属不同 30m 桶（午休不可跨越）
        rows = [_m(_ts(20260625, hhmm), 10, 10, 10, 10)
                for hhmm in (1029, 1130, 1300)]
        out = resample_minutes(rows, 30)
        assert [b["date"] for b in out] == [_ts(20260625, 1000),
                                            _ts(20260625, 1100),
                                            _ts(20260625, 1300)]

    def test_pre_close_chain(self):
        rows = ([_m(_ts(20260625, 930 + i), 10, 10, 10, 10) for i in range(5)]
                + [_m(_ts(20260625, 935 + i), 10, 10, 10, 10)
                   for i in range(5)])
        out = resample_minutes(rows, 5)
        assert out[0]["pre_close"] == 10
        assert out[1]["pre_close"] == out[0]["close"]
        assert out[1]["pct_chg"] == 0.0

    def test_placeholder_rows_dropped(self):
        # 同桶内混入两种停牌占位形态：均不参与 open/close/high/low/volume 合并
        rows = ([_susp(_ts(20260625, 930 + i)) for i in range(2)]
                + [_susp0(_ts(20260625, 932))]
                + [_m(_ts(20260625, 933 + i), 10 + i, 12 + i, 13, 9)
                   for i in range(2)])
        out = resample_minutes(rows, 5)
        assert len(out) == 1
        assert out[0]["open"] == 10 and out[0]["close"] == 13
        assert out[0]["high"] == 13 and out[0]["low"] == 9
        assert out[0]["volume"] == 200

    def test_all_placeholder_bucket_dropped(self):
        # 整个 5m 桶全为占位 bar（None / 0 两种形态混布）：整桶不输出
        rows = ([_m(_ts(20260625, 930 + i), 10, 10, 10, 10) for i in range(5)]
                + [_susp(_ts(20260625, 935 + i)) for i in range(3)]
                + [_susp0(_ts(20260625, 938 + i)) for i in range(2)])
        out = resample_minutes(rows, 5)
        assert [b["date"] for b in out] == [_ts(20260625, 930)]
        assert out[0]["volume"] == 500

    def test_partial_none_fields_no_crash(self):
        # 部分价格字段缺失（非占位行）：不再因 max()/min() 空序列崩溃
        rows = [_m(_ts(20260625, 930 + i), 10, 10 + i, None, None)
                for i in range(5)]
        out = resample_minutes(rows, 5)
        assert len(out) == 1
        assert out[0]["high"] is None and out[0]["low"] is None
        assert out[0]["open"] == 10 and out[0]["close"] == 14


class TestDaily:
    def test_weekly(self):
        # 20260803(一) - 20260807(五) 同一周，20260810(一) 进入下周
        rows = [_m(d, 10, 10 + i, 11, 9) for i, d in
                enumerate([20260803, 20260804, 20260805, 20260806, 20260807,
                           20260810])]
        out = resample_daily(rows, "1w")
        assert len(out) == 2
        assert out[0]["date"] == 20260807       # 标签 = 组内最后交易日
        assert out[0]["open"] == 10 and out[0]["close"] == 14
        assert out[1]["date"] == 20260810
        assert out[1]["pre_close"] == out[0]["close"]

    def test_monthly(self):
        rows = [_m(d, 10, 10, 10, 10) for d in
                (20260629, 20260630, 20260701)]
        out = resample_daily(rows, "1M")
        assert [b["date"] for b in out] == [20260630, 20260701]
        assert [b["volume"] for b in out] == [200, 100]

    def test_weekly_spans_year_boundary(self):
        # 2024-12-30/31 与 2025-01-02 同属 2025 年第 1 个 ISO 周
        rows = [_m(d, 10, 10, 10, 10) for d in
                (20241230, 20241231, 20250102)]
        out = resample_daily(rows, "1w")
        assert len(out) == 1

    def test_suspended_days_dropped(self):
        # 周内停牌占位日（OHLC 全 None 或全 0）不参与周线合并
        rows = ([_m(20260803, 10, 11, 12, 9)]
                + [_susp(20260804), _susp0(20260805)]
                + [_m(20260806, 13, 14, 15, 8)])
        out = resample_daily(rows, "1w")
        assert len(out) == 1
        assert out[0]["open"] == 10 and out[0]["close"] == 14
        assert out[0]["volume"] == 200
