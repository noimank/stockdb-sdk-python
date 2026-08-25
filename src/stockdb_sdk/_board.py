"""板块（概念 / 申万行业）检索：板块 <-> 股票双向映射。"""

from __future__ import annotations

from collections import defaultdict
from copy import copy
from typing import Any

from ._connection import get_default_raw_rd

BOARD_FIELDS = ("code", "name", "source", "type", "group", "category", "symbols")
FIELD_ALIASES = {
    "symbol": "symbols",
    "symbols": "symbols",
    "symbls": "symbols",
    "codelist": "symbols",
}
CATEGORY_MAP = {
    0: "概念",
    1: "申万一级",
    2: "申万二级",
    3: "申万三级",
}


class BoardIndex:
    """板块索引：支持按代码 / 名称 / 成分股 / 分类查询板块。

    通过 :data:`stockdb_sdk.bk` 使用其惰性单例，无需手动实例化。
    """

    def __init__(self, rows: list | None = None):
        self.rows = rows if rows is not None else get_default_raw_rd().get("板块*").do()
        self.boards: list[dict[str, Any]] = []
        self.by_code: dict[str, dict[str, Any]] = {}
        self.by_stock: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._build()

    def get(
        self,
        x: Any = None,
        category: int | str | None = None,
        fields: str | None = None,
    ) -> Any:
        """查询板块。

        Args:
            x: 查询目标。``None`` 取分类全集；6 位股票代码（含后缀写法）
                反查所属板块；板块代码（如 ``"801780.SL"``）精确命中单个板块；
                其他字符串按板块名称精确 / 模糊匹配；列表则逐项查询并按
                原样返回 ``dict``。
            category: 分类过滤。``0`` 概念 / ``1`` 申万一级 / ``2`` 申万二级 /
                ``3`` 申万三级，也接受分类名称字符串。
            fields: 需要返回的字段，逗号分隔。单项时返回值的扁平列表，
                多项时返回二维列表；不传返回板块 dict。

        Example::

            bk.get("000001", 1, "name")      # -> ['银行']
            bk.get("新能源")                  # -> [板块 dict, ...]
            bk.get("801780.SL")               # -> 单个板块 dict
        """
        category = self._category(category)
        fields = self._fields(fields)

        if isinstance(x, (list, tuple, set)):
            return {str(item): self.get(item, category, fields) for item in x}

        if x is None:
            items = self.boards if category is None else self.by_category.get(category, [])
            return self._result(items, fields, single=False, with_symbols=True)

        query = str(x).strip()
        if not query:
            return []

        if query in self.by_code:
            return self._result([self.by_code[query]], fields, single=True, with_symbols=True)

        if self._is_stock_code(query):
            stock = self._stock_code(query)
            items = self.by_stock.get(stock, [])
            if category is not None:
                items = [item for item in items if item["category"] == category]
            return self._result(items, fields, single=False, with_symbols=False)

        if category is not None:
            exact = self.by_name.get(f"{category}_{query}", [])
            if exact:
                return self._result(exact, fields, single=True, with_symbols=True)
            matched = self._match_name(query, category)
            return self._result(matched, fields, single=False, with_symbols=True)

        matched: list[dict[str, Any]] = []
        for cat in CATEGORY_MAP.values():
            matched.extend(self.by_name.get(f"{cat}_{query}", []))
        if not matched:
            matched = self._match_name(query, category=None)
        return self._result(matched, fields, single=False, with_symbols=True)

    def _build(self) -> None:
        for key, board in self.rows:
            if not isinstance(board, dict):
                continue

            code = str(board.get("code", "")).strip()
            name = str(board.get("name", "")).strip()
            category = str(board.get("category", "")).strip()
            if not code or not name or not category:
                continue

            symbols = [
                self._stock_code(symbol)
                for symbol in board.get("symbols", []) or []
                if str(symbol).strip()
            ]

            item = {
                **board,
                "code": code,
                "name": name,
                "category": category,
                "symbols": symbols,
            }

            self.boards.append(item)
            self.by_code[code] = item
            self.by_name[f"{category}_{name}"].append(item)
            self.by_category[category].append(item)

            stock_item = self._board(item, with_symbols=False)
            for stock in symbols:
                self.by_stock[stock].append(stock_item)

    def _result(
        self,
        items: list[dict[str, Any]],
        fields: str | None,
        single: bool,
        with_symbols: bool,
    ) -> Any:
        boards = [self._board(item, with_symbols) for item in items]
        if fields:
            selected = fields.split(",")
            if len(selected) == 1:
                values = [item.get(selected[0]) for item in boards]
            else:
                values = [[item.get(key) for key in selected] for item in boards]
            if single:
                if values:
                    return values[0]
                # 单字段 symbols 无命中时返回 []，调用方可直接迭代成分股列表
                return [] if selected == ["symbols"] else None
            return values
        if single:
            return boards[0] if boards else {}
        return boards

    def _match_name(self, keyword: str, category: str | None) -> list[dict[str, Any]]:
        items = self.boards if category is None else self.by_category.get(category, [])
        return [item for item in items if keyword in item["name"]]

    def _board(self, item: dict[str, Any], with_symbols: bool) -> dict[str, Any]:
        value = {field: copy(item[field]) for field in BOARD_FIELDS if field in item}
        if not with_symbols:
            value.pop("symbols", None)
        return value

    def _category(self, category: int | str | None) -> str | None:
        if category is None:
            return None
        if isinstance(category, int):
            if category not in CATEGORY_MAP:
                raise ValueError(f"unknown category number: {category}")
            return CATEGORY_MAP[category]

        category_text = str(category).strip()
        if category_text.isdigit():
            return self._category(int(category_text))
        return category_text

    def _fields(self, fields: str | None) -> str | None:
        if fields is None:
            return None
        selected = []
        for item in str(fields).split(","):
            item = item.strip()
            if not item:
                continue
            item = FIELD_ALIASES.get(item, item)
            if item not in BOARD_FIELDS:
                raise ValueError(f"unknown fields item: {item}")
            selected.append(item)
        if not selected:
            return None
        return ",".join(selected)

    def _is_stock_code(self, value: str) -> bool:
        code = self._stock_code(value)
        return len(code) == 6 and code.isdigit()

    def _stock_code(self, value: Any) -> str:
        return str(value).strip().split(".")[0]


class _LazyBoardIndex:
    """BoardIndex 的惰性单例包装。"""

    def __init__(self):
        self._instance = None

    def _target(self):
        if self._instance is None:
            self._instance = BoardIndex()
        return self._instance

    def get(
        self,
        x: Any = None,
        category: int | str | None = None,
        fields: str | None = None,
    ) -> Any:
        """查询板块，参数与 :meth:`BoardIndex.get` 完全一致，详见其文档。"""
        return self._target().get(x, category, fields)

    def __getattr__(self, name):
        return getattr(self._target(), name)

    def __dir__(self):
        return dir(self._target())

    def __repr__(self):
        return repr(self._target())

    def reset(self):
        self._instance = None


bk = _LazyBoardIndex()


def reset_default_connection():
    """丢弃为旧服务端加载的板块缓存。"""
    bk.reset()


def warm_default_connection():
    """立即加载当前服务端的板块映射。"""
    return bk._target()
