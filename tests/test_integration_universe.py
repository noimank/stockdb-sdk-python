"""股票清单与板块集成测试（对本地 stockdb 服务）。"""

import pytest

import stockdb_sdk as sdk
from conftest import requires_server


@requires_server
class TestUniverse:
    def test_codes(self):
        codes = sdk.codes()
        assert isinstance(codes, list)
        assert codes == sorted(codes)
        assert "000001" in codes and "600633" in codes
        assert all(len(c) == 6 and c.isdigit() for c in codes[:100])

    def test_delisted(self):
        gone = sdk.delisted()
        assert gone and gone == sorted(gone)
        assert "600633" not in gone


@requires_server
class TestBoards:
    def test_boards_of_stock(self):
        boards = sdk.boards("600633")
        assert boards
        for b in boards:
            assert {"code", "name", "category"} <= b.keys()
            assert "symbols" not in b
        categories = {b["category"] for b in boards}
        assert any("申万" in c for c in categories)

    def test_members_by_name(self):
        members = sdk.members("AI芯片")
        assert members and all(len(c) == 6 for c in members)
        assert "603160" in members  # 实测样本中的成员

    def test_members_by_code_with_category(self):
        by_code = sdk.members("801170.SL")
        by_name = sdk.members("交通运输", category="申万一级")
        assert by_code == by_name and by_code

    def test_members_fuzzy_disambiguation(self):
        with pytest.raises(ValueError, match="category"):
            sdk.members("AI")   # AI芯片 / AI视频 等多个模糊命中

    def test_members_unknown(self):
        with pytest.raises(ValueError, match="不存在"):
            sdk.members("不存在的板块xyz")

    def test_boards_of_unknown_code(self):
        assert sdk.boards("999999") == []
