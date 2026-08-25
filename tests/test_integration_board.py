"""集成测试：板块检索（需本地 stockdb 服务）。"""

import pytest

import stockdb_sdk as sdk


@pytest.fixture(scope="module")
def boards():
    all_boards = sdk.bk.get()
    assert all_boards
    return all_boards


def test_get_all(boards):
    for b in boards:
        for key in ("code", "name", "source", "type", "group", "category", "symbols"):
            assert key in b


def test_by_board_code(boards):
    board = next(b for b in boards if b["symbols"])
    got = sdk.bk.get(board["code"])
    assert isinstance(got, dict)
    assert got["code"] == board["code"]
    assert got["symbols"] == board["symbols"]
    assert sdk.bk.get(board["code"], fields="name") == board["name"]


def test_by_stock_with_suffix(boards):
    board = next(b for b in boards if b["symbols"])
    stock = board["symbols"][0]
    plain = sdk.bk.get(stock)
    suffix = ".SZ" if stock.startswith(("0", "3")) else ".SH"
    assert sdk.bk.get(stock + suffix) == plain
    assert board["code"] in {b["code"] for b in plain}


def test_by_stock_category():
    assert sdk.bk.get("000001", 1, "name") == ["银行"]


def test_category_filter():
    sw1 = sdk.bk.get(category=1)
    assert sw1
    assert all(b["category"] == "申万一级" for b in sw1)
    # 分类名 / 数字字符串与数字等价
    assert sdk.bk.get(category="申万一级") == sw1
    assert sdk.bk.get(category="1") == sw1


def test_name_lookup():
    exact = sdk.bk.get("银行", 1)
    assert isinstance(exact, dict) and exact["name"] == "银行"
    fuzzy = sdk.bk.get("新能源")
    assert fuzzy and all("新能源" in b["name"] for b in fuzzy)


def test_fields_and_list_input():
    pairs = sdk.bk.get(category=1, fields="name,code")
    assert pairs
    assert all(isinstance(p, list) and len(p) == 2 for p in pairs)

    out = sdk.bk.get(["000001", "600633"], 1, "name")
    assert out["000001"] == ["银行"]
    assert out["600633"]


def test_invalid_args():
    with pytest.raises(ValueError, match="unknown category"):
        sdk.bk.get("000001", 9)
    with pytest.raises(ValueError, match="unknown fields item"):
        sdk.bk.get("000001", 1, "bad")
