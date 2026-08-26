"""原生只读门面集成测试（对本地 stockdb 服务）。"""

from conftest import requires_server
from stockdb_sdk import rd


@requires_server
class TestRd:
    def test_get_exact(self):
        row = rd.get("日k:600633:20260625")
        assert isinstance(row, dict) and row["code"] == "600633"

    def test_get_wildcard_returns_pairs(self):
        pairs = rd.get("日k:600633:2026062*")
        assert pairs and all(isinstance(p, list) and len(p) == 2 for p in pairs)
        assert all(p[0].startswith("日k:600633:2026062") for p in pairs)

    def test_vals_wildcard(self):
        rows = rd.vals("日k", "600633", "2026062*")
        assert rows and isinstance(rows[0], dict)

    def test_keys_and_len_agree(self):
        keys = rd.keys("日k", "600633")
        assert keys and all(k.startswith("日k:600633:") for k in keys)
        assert rd.len("日k", "600633") == len(keys)

    def test_len_with_key2(self):
        assert rd.len("日k", "600633", "20260625") == 1

    def test_delisted_vals(self):
        rows = rd.vals("退市*")
        assert rows and isinstance(rows[0], str)
