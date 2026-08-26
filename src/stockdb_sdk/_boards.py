"""板块：概念 / 申万一二三级行业与股票代码的双向映射。

* :func:`members` —— 惰性路径：keys 扫描（约 1300 个键、几十 KB）
  定位目标板块后只取该板块的值，**不加载全量索引**，查完零驻留；
* :func:`boards` —— 反向查找必须遍历全部板块的成员表，首次调用
  通过一次 ``get t=板块*`` 建立索引（有界元数据，约 10-20MB）并
  保留复用；:func:`stockdb_sdk.init` 切换端点时自动失效。
"""

from typing import Any, Dict, List, Optional

from . import _transport

_index: List[Dict[str, Any]] = []


def reset() -> None:
    """清空板块索引（切换端点后由 :func:`stockdb_sdk.init` 调用）。"""
    _index.clear()


def _load_index() -> List[Dict[str, Any]]:
    if not _index:
        for key, val in _transport.fetch("get", t="板块*"):
            _, cat_name, board_code = key.split(":")
            _index.append({
                "code": board_code,
                "name": val.get("name"),
                "category": val.get("category", cat_name.split("_", 1)[0]),
                "source": val.get("source"),
                "symbols": val.get("symbols", []),
            })
    return _index


def boards(code: str) -> List[Dict[str, Any]]:
    """查询一只股票所属的全部板块（不含成员列表）。"""
    code = code.split(".")[0]
    return [
        {k: v for k, v in b.items() if k != "symbols"}
        for b in _load_index() if code in b["symbols"]
    ]


def _match(board: str, category: Optional[str]) -> tuple:
    """在 keys 扫描结果中定位唯一板块，返回 (类别, 名称, 板块代码)。"""
    entries = []
    for key in _transport.fetch("keys", t="板块", k1="all:", k2="all:"):
        _, cat_name, board_code = key.split(":", 2)
        cat, name = cat_name.split("_", 1)
        entries.append((cat, name, board_code))
    hits = [e for e in entries if e[2] == board or e[1] == board]
    if not hits:
        hits = [e for e in entries if board in e[1]]
    if category:
        hits = [e for e in hits if e[0] == category]
    if not hits:
        raise ValueError(f"板块不存在: {board!r}")
    if len(hits) > 1:
        names = "、".join(f"{n}({c})" for c, n, _ in hits[:8])
        raise ValueError(f"板块 {board!r} 匹配到多个，请用 category 消歧: {names}")
    return hits[0]


def members(board: str, category: Optional[str] = None) -> List[str]:
    """查询板块成员代码列表。

    Args:
        board: 板块名称（如 ``"AI芯片"``）或板块代码（如 ``"801170.SL"``）；
            名称先精确匹配，未命中再模糊包含匹配。
        category: 可选类别过滤（``"概念"`` / ``"申万一级"`` /
            ``"申万二级"`` / ``"申万三级"``），同名模糊命中多个板块时
            用于消歧。

    Raises:
        ValueError: 板块不存在，或模糊匹配到多个板块且未用 category 消歧。
    """
    cat, name, board_code = _match(board, category)
    val = _transport.fetch("get", t=f"板块:{cat}_{name}:{board_code}")
    return sorted(val.get("symbols", []))
