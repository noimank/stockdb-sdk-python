"""原生 K-V 只读门面：直接面向 ``表[:键1[:键2]]`` 三级键模型。

v0.3 起本 SDK 只走 HTTP 只读通道，因此这里只暴露与协议一一对应的
四个读方法；写入（set/setl/setr/delete）与管线（pipe）不在 HTTP
协议内，不提供。

键表达式规则（与传输层约束一致）：

* :meth:`get` / :meth:`vals` 走 ``t`` 冒号串形式，**通配符 ``*`` 只能
  出现在最后一段且全键至多一个**（``"日k:60063*"``, ``"退市*"``
  合法；``"日k:*:20260625"`` 返回空）；
* :meth:`keys` / :meth:`len` 走 ``k1`` / ``k2`` 参数形式，只接受精确
  三级键（``len("日k", "600633")`` 统计该代码全部 K 线数量）。

Example::

    rd = stockdb_sdk.rd
    rd.get("日k:600633:20260625")          # 单行 dict
    rd.vals("日k:600633:202606*")          # 行列表
    rd.keys("日k", "600633")               # 完整键列表
    rd.len("日k", "600633")                # 5421
"""

from typing import Any, List, Optional

from . import _transport


def _key_args(table: str, key: Optional[str], key2: Optional[str]) -> tuple:
    if key2 is not None:
        return (table, key, key2)
    if key is not None:
        return (table, key)
    return (table,)


class RdClient:
    """原生只读门面（模块级单例 :data:`stockdb_sdk.rd`）。"""

    def get(self, table: str, key: Optional[str] = None,
            key2: Optional[str] = None) -> Any:
        """读键值：精确键返回值本体（dict / list / 标量），含通配符的
        表达式返回 ``[[完整键, 值], ...]``。"""
        return _transport.fetch("get", t=":".join(_key_args(table, key, key2)))

    def vals(self, table: str, key: Optional[str] = None,
             key2: Optional[str] = None) -> Any:
        """只读值列：精确键返回 ``[值]``，表达式返回 ``[值, ...]``。"""
        return _transport.fetch("vals", t=":".join(_key_args(table, key, key2)))

    def keys(self, table: str, key: Optional[str] = None,
             key2: Optional[str] = None) -> List[str]:
        """列出匹配的完整键（要求各级均为精确值，不支持通配）。"""
        return _transport.fetch(
            "keys", t=table,
            k1=f"key:{key}" if key is not None else "all:",
            k2=f"key:{key2}" if key2 is not None else "all:")

    def len(self, table: str, key: Optional[str] = None,
            key2: Optional[str] = None) -> int:
        """统计匹配的键数量（参数规则同 :meth:`keys`）。"""
        return _transport.fetch(
            "len", t=table,
            k1=f"key:{key}" if key is not None else "all:",
            k2=f"key:{key2}" if key2 is not None else "all:")


rd = RdClient()
