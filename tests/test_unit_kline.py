"""K 线接口单元测试：参数校验与归一化（不依赖服务）。"""

import pytest

from stockdb_sdk._kline import _bound, _normalize, _validate


class TestValidate:
    def test_valid(self):
        _validate("1d", "qfq")
        _validate("60m", None)

    def test_bad_freq(self):
        with pytest.raises(ValueError, match="freq"):
            _validate("2h", "qfq")

    def test_bad_fq(self):
        with pytest.raises(ValueError, match="fq"):
            _validate("1d", "raw")


class TestBound:
    def test_daily_accepts_8_and_14(self):
        assert _bound("20260701", False, True) == "20260701"
        assert _bound("20260701103000", False, False) == "20260701"

    def test_minute_expands_8_digit(self):
        assert _bound("20260824", True, True) == "20260824000000"
        assert _bound("20260824", True, False) == "20260824235959"

    def test_minute_keeps_14_digit(self):
        assert _bound("20260824100000", True, True) == "20260824100000"

    def test_rejects_bad(self):
        for bad in ("2026-07-01", "2026071", 202607.1):
            with pytest.raises(ValueError):
                _bound(bad, False, True)


class TestNormalize:
    def test_suffix_stripped(self):
        assert _normalize("600633.SH") == "600633"
        assert _normalize(" 000001 ") == "000001"

    def test_list(self):
        assert _normalize(["000001.SZ", "600633"]) == ["000001", "600633"]

    def test_bad_type(self):
        with pytest.raises(TypeError):
            _normalize(600633)
