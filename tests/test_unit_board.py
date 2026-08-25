"""离线单元测试：BoardIndex 索引构建与查询。"""

import pytest

from stockdb_sdk._board import BoardIndex, _LazyBoardIndex


ROWS = [
    ("板块:概念_新能源车:BK1001.TI", {
        "code": "BK1001.TI", "name": "新能源车", "source": "ths", "type": "concept",
        "group": "特色指数列表", "category": "概念",
        "symbols": ["000631", "600104.SH", ""],
    }),
    ("板块:申万一级_银行:801780.SL", {
        "code": "801780.SL", "name": "银行", "source": "sw", "type": "sw_1",
        "group": "申万行业指数列表", "category": "申万一级",
        "symbols": ["000001", "600000"],
    }),
    ("板块:申万二级_股份制银行:801781.SL", {
        "code": "801781.SL", "name": "股份制银行", "source": "sw", "type": "sw_2",
        "group": "申万行业指数列表", "category": "申万二级",
        "symbols": ["000001"],
    }),
    ("板块:概念_银行金融:BK1002.TI", {
        "code": "BK1002.TI", "name": "银行金融", "source": "ths", "type": "concept",
        "group": "特色指数列表", "category": "概念", "symbols": [],
    }),
    # 缺少 name，应被跳过
    ("板块:概念_缺名称:BK1003.TI", {"code": "BK1003.TI", "category": "概念", "symbols": []}),
]


@pytest.fixture
def bi():
    return BoardIndex(rows=ROWS)


def test_build_skips_invalid_rows(bi):
    assert len(bi.boards) == 4
    assert "BK1003.TI" not in bi.by_code
    # symbols 归一化为裸代码，空值剔除
    assert bi.by_code["BK1001.TI"]["symbols"] == ["000631", "600104"]


def test_get_all_and_category(bi):
    assert len(bi.get()) == 4
    sw1 = bi.get(category=1)
    assert [b["code"] for b in sw1] == ["801780.SL"]
    # 分类名 / 数字字符串与数字等价
    assert bi.get(category="申万一级") == sw1
    assert bi.get(category="1") == sw1


def test_get_by_board_code(bi):
    board = bi.get("801780.SL")
    assert isinstance(board, dict)
    assert board["code"] == "801780.SL"
    assert board["symbols"] == ["000001", "600000"]
    # 单字段投影 -> 单值
    assert bi.get("801780.SL", fields="name") == "银行"
    # 多字段投影 -> 扁平列表
    assert bi.get("801780.SL", fields="name,code") == ["银行", "801780.SL"]


def test_get_by_stock(bi):
    boards = bi.get("000001")
    assert {b["code"] for b in boards} == {"801780.SL", "801781.SL"}
    # 成分股反查结果不含 symbols
    assert all("symbols" not in b for b in boards)
    # 分类过滤
    assert [b["code"] for b in bi.get("000001", 1)] == ["801780.SL"]
    # 股票 + 单字段 -> 扁平列表
    assert bi.get("000001", 1, "name") == ["银行"]
    # 带后缀写法等价
    assert bi.get("000001.SZ") == boards


def test_get_by_name(bi):
    # 指定分类时精确命中 -> 单个 dict
    exact = bi.get("银行", 1)
    assert isinstance(exact, dict) and exact["code"] == "801780.SL"
    # 无分类时跨分类精确匹配优先
    assert bi.get("银行", None, "code") == ["801780.SL"]
    # 精确未命中再模糊匹配
    assert bi.get("新能源", None, "code") == ["BK1001.TI"]
    assert bi.get("银行金", None, "code") == ["BK1002.TI"]


def test_get_list_input(bi):
    out = bi.get(["000001", "600000"], 1, "name")
    assert out == {"000001": ["银行"], "600000": ["银行"]}


def test_get_empty_query(bi):
    assert bi.get("") == []
    assert bi.get("   ") == []


def test_invalid_args(bi):
    with pytest.raises(ValueError, match="unknown category"):
        bi.get("000001", 9)
    with pytest.raises(ValueError, match="unknown fields item"):
        bi.get("000001", 1, "bad")


def test_field_aliases(bi):
    assert bi.get("801780.SL", fields="symbol") == bi.get("801780.SL", fields="symbols")
    assert bi.get("801780.SL", fields="codelist") == ["000001", "600000"]


def test_lazy_singleton_reset(bi):
    lazy = _LazyBoardIndex()
    lazy._instance = bi
    assert lazy.get("801780.SL")["code"] == "801780.SL"
    lazy.reset()
    assert lazy._instance is None


def test_lazy_proxy_signature_matches_board_index():
    import inspect

    # 两侧均含 self，直接整体比较
    assert inspect.signature(_LazyBoardIndex.get) == inspect.signature(BoardIndex.get)
