"""K 线集成测试（对本地 stockdb 服务）。"""

import asyncio

import pandas as pd
import pytest

import stockdb_sdk as sdk
from conftest import requires_server


@requires_server
class TestDaily:
    def test_range_and_order(self):
        rows = sdk.get("600633", start="20260620", end="20260626")
        assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)
        assert rows[0]["date"] >= 20260620
        assert rows[-1]["date"] <= 20260626
        assert all(r["code"] == "600633" for r in rows)
        assert {"open", "high", "low", "close", "volume"} <= rows[0].keys()

    def test_suffix_normalized(self):
        rows = sdk.get("600633.SH", start="20260625", end="20260625")
        assert len(rows) == 1

    def test_fields_projection(self):
        rows = sdk.get("600633", start="20260625", end="20260626",
                       fields="date,close")
        assert rows and set(rows[0]) == {"date", "close"}

    def test_fields_invalid_raises(self):
        with pytest.raises(ValueError, match="字段不存在"):
            sdk.get("600633", start="20260625", end="20260626",
                    fields="date,not_a_field")

    def test_as_df(self):
        df = sdk.get("600633", start="20260620", end="20260626", as_df=True)
        assert isinstance(df, pd.DataFrame)
        assert list(df["date"]) == sorted(df["date"])


@requires_server
class TestMinute:
    def test_single_day_1m(self):
        rows = sdk.get("600633", freq="1m", start="20260625",
                       end="20260625", fq=None)
        assert rows
        assert all(20260625000000 < r["date"] < 20260626000000 for r in rows)
        assert [r["date"] for r in rows] == sorted(r["date"] for r in rows)

    def test_5m_consistent_with_1m(self):
        raw = sdk.get("600633", freq="1m", start="20260625",
                      end="20260625", fq=None)
        agg = sdk.get("600633", freq="5m", start="20260625",
                      end="20260625", fq=None)
        assert agg and len(agg) <= len(raw)
        assert agg[0]["open"] == raw[0]["open"]
        assert agg[0]["high"] == max(r["high"] for r in raw[:5])
        assert agg[0]["volume"] == sum(r["volume"] for r in raw[:5])


@requires_server
class TestAggregateFreq:
    def test_weekly_from_daily(self):
        daily = sdk.get("600633", start="20260803", end="20260810", fq=None)
        weekly = sdk.get("600633", freq="1w", start="20260803",
                         end="20260810", fq=None)
        assert len(weekly) == 2
        assert weekly[0]["date"] == max(r["date"] for r in daily
                                        if r["date"] <= 20260807)
        assert weekly[0]["close"] == [r for r in daily
                                      if r["date"] <= 20260807][-1]["close"]

    def test_monthly(self):
        rows = sdk.get("600633", freq="1M", start="20260601",
                       end="20260731", fq=None)
        assert [r["date"] for r in rows] == [20260630, 20260731]


@requires_server
class TestFq:
    def test_qfq_anchored_at_latest(self):
        raw = sdk.get("000001", start="20260601", end="20260630", fq=None)
        qfq = sdk.get("000001", start="20260601", end="20260630")
        # 000001 有大量除权事件：qfq 末期价格 == 原始价（锚定最新）
        assert qfq[-1]["close"] == raw[-1]["close"]
        # 早期价格被向下折算（cum_latest > 1）
        assert qfq[0]["close"] == pytest.approx(raw[0]["close"], abs=1e-9) \
            or qfq[0]["close"] < raw[0]["close"]

    def test_hfq_inflates_history(self):
        # 库内日K覆盖 2000-01 起；2023 年有除权事件（cum ≈ 113）
        raw = sdk.get("000001", start="20230601", end="20230630", fq=None)
        hfq = sdk.get("000001", start="20230601", end="20230630", fq="hfq")
        assert hfq[-1]["close"] > raw[-1]["close"] * 100


@requires_server
class TestBatch:
    def test_prefix(self):
        data = sdk.get("60063*", start="20260622", end="20260626", fq=None)
        assert isinstance(data, dict) and len(data) >= 3
        assert all(c.startswith("60063") for c in data)
        assert all(rows for rows in data.values())

    def test_narrow_prefix_matches_per_code(self):
        # 窄前缀走枚举+逐代码路径，结果须与逐只查询完全一致
        data = sdk.get("60063*", start="20260622", end="20260626", fq=None)
        for code, rows in list(data.items())[:3]:
            assert rows == sdk.get(code, start="20260622",
                                   end="20260626", fq=None)

    def test_pool_path(self):
        # >= 4 只代码走线程池并发路径
        codes = ["600633", "000001", "300750", "688981", "601398"]
        data = sdk.get(codes, start="20260818", end="20260824", fq=None)
        assert set(data) == set(codes)
        assert all(rows for rows in data.values())

    def test_list_dedup(self):
        data = sdk.get(["600633", "600633"], start="20260625",
                       end="20260626", fq=None)
        assert set(data) == {"600633"}

    def test_list(self):
        data = sdk.get(["600633", "000001"], start="20260625",
                       end="20260626", fq=None)
        assert set(data) == {"600633", "000001"}

    def test_list_as_df_concatenated(self):
        df = sdk.get(["600633", "000001"], start="20260625",
                     end="20260626", fq=None, as_df=True)
        assert isinstance(df, pd.DataFrame)
        assert set(df["code"]) == {"600633", "000001"}


@requires_server
class TestAsync:
    def test_matches_sync(self):
        rows = asyncio.run(sdk.get_async("600633", start="20260620",
                                         end="20260626", fq=None))
        sync_rows = sdk.get("600633", start="20260620", end="20260626",
                            fq=None)
        assert rows == sync_rows

    def test_list_concurrent(self):
        data = asyncio.run(sdk.get_async(["600633", "000001", "300750"],
                                         start="20260625", end="20260626",
                                         fq=None))
        assert set(data) == {"600633", "000001", "300750"}
        assert all(isinstance(rows, list) for rows in data.values())
