"""原生 rd 连接的类型化门面：显式签名 + 完整语义文档。

底层是 ``stockdb.pyd`` 提供的 K-V 协议客户端（每连接一个对象），本模块
不改变任何行为，仅以显式参数与文档暴露其全部 13 个方法，使 IDE 补全、
``help()`` 与静态检查可用。

键模型
------
``表[:键1[:键2]]`` 三级键，冒号拼接存储（如 ``日k:600633:20260625``）。
值类型：``int / float / str / bytes / list / dict / DataFrame``。

键表达式（键1/键2 位置均可使用；箭头方向即扫描/输出方向）：

* ``*`` —— 前缀通配（``"60063*"``、单独用作键1 时匹配全表）；
* ``"a>b"`` —— 正向扫描闭区间 [a, b]，**升序**输出（要求 a ≤ b，
  否则返回空；高层 :func:`get_data` 即用此形态）；
* ``"a<b"`` —— 反向扫描，从 b 降到 a，**降序**输出；
* ``"a>N"`` —— 从 a 正向扫描到最新，升序；``"N"`` 单独使用表示
  不设限；
* 结果支持 ``[:n]`` 切片截取。

同步 / 异步双态
---------------
所有方法既可直接调用，也可 ``await``，但两种形态的保证不同（实测结论）：

* **读操作**同步调用即返回结果；
* **写操作**（set/setl/setr/mset/delete）同步调用只保证入队（返回 1），
  与后续读取的可见性顺序不保证——写后立读请 ``await`` 写操作；
* **管线**：同步上下文用 ``do()``，协程内用 ``await pipeline``；
  单条命令返回结果本体，多条命令返回结果列表；
  **读写命令不得混入同一管线**（协议限制，混用会死锁）。

QueryResult 物化
-----------------
``get`` / ``vals`` 返回 ``QueryResult``：repr、迭代、``len()``、切片与
``["字段"]`` 索引都直接可用（索引得到纯 Python 值）；但 ``.get("字段")``
返回的仍是 ``QueryResult`` 包装，参与 ``==`` 比较 / ``int()`` / 算术前需
调用 ``.do()`` 物化为纯 Python 值。
"""

from typing import Any, Optional

from ._connection import get_default_raw_rd
from .stockdb import StockdbError

__all__ = ["RdClient", "Pipeline", "StockdbError"]


class Pipeline:
    """``rd.pipe()`` 的类型化包装：批量命令队列。

    用 ``mget`` / ``mset`` 逐条入队后执行：同步上下文用 :meth:`do`，
    协程内用 ``await pipeline``。单条命令返回结果本体，多条命令返回
    结果列表。**读写命令不得混入同一管线**（协议限制，混用会死锁）。
    """

    def __init__(self, native):
        self._native = native

    def mget(self, table: str, key: Optional[str] = None,
             key2: Optional[str] = None) -> "Pipeline":
        """入队一条读命令（语义同 :meth:`RdClient.get`）。返回 self 支持链式。"""
        self._native.mget(*_key_args(table, key, key2))
        return self

    def mset(self, table: str, *keys_and_value: Any) -> "Pipeline":
        """入队一条写命令（语义同 :meth:`RdClient.set`）。返回 self 支持链式。"""
        self._native.mset(table, *keys_and_value)
        return self

    def do(self):
        """同步执行队列（同步上下文使用；协程内请 ``await pipeline``）。

        单条命令返回结果本体，多条命令返回结果列表。
        """
        return self._native.do()

    def __await__(self):
        """异步执行队列：``await pipeline``。"""
        return self._native.__await__()

    def __repr__(self):
        return repr(self._native)


def _key_args(table: str, key: Optional[str], key2: Optional[str]) -> tuple:
    """把 (table, key, key2) 折叠为原生接口接受的位置参数元组。"""
    if key2 is not None:
        return (table, key, key2)
    if key is not None:
        return (table, key)
    return (table,)


class RdClient:
    """原生 K-V 客户端的类型化门面（全部方法与原生 rd 一一对应）。

    Args:
        native: 已有的原生连接对象。缺省时惰性解析当前默认端点
            （跟随 :func:`stockdb_sdk.init` 切换）。

    内置数据表：``日k`` / ``分钟k``（行情）、``股票代码`` / ``退市*``
    （代码表）、``复权*``（复权因子）、``板块*``（板块映射）；私有数据
    建议写入自定义表名（如 ``mydb``）。

    Example::

        rd = sdk.rd
        bars = rd.vals("日k", "600633", "20260701>N")     # 近端日K
        rd.set("mydb", "signal", "20260824", {"buy": 1})  # 私有写入
    """

    def __init__(self, native=None):
        self._native = native

    def _rd(self):
        return self._native if self._native is not None else get_default_raw_rd()

    # ================= 读 =================

    def get(self, table: str, key: Optional[str] = None,
            key2: Optional[str] = None) -> Any:
        """读取：精确键返回值本体，表达式返回 ``[[键, 值], ...]``。

        Args:
            table: 表名；也接受冒号简写 ``"日k:600633:20260625"``（此时
                其余参数省略）。
            key: 键1，如股票代码；可含表达式（见模块说明）。
            key2: 键2，如日期/时间戳；可含表达式。

        Returns:
            精确命中时为值本体（dict / list / 标量）；键含 ``*`` 或范围
            表达式时为 ``[[完整键, 值], ...]`` 列表（天然按键升序）。

        返回的 ``QueryResult``：``["字段"]`` 索引得到纯 Python 值，迭代/
        切片/``len()`` 直接可用；``.get("字段")`` 列投影（多项逗号分隔）
        返回的仍是包装，需 ``==`` 比较 / ``int()`` 时先 ``.do()`` 物化
        （详见模块说明）。

        Example::

            rd.get("股票代码")                          # {'6': [...], ...}
            rd.get("日k", "600633", "20260625")         # 当日行情（字典式）
            rd.get("日k", "600633", "20260620<20260626")  # 键值对集合
            rd.get("日k", "600633", "202606*")["close"]   # 索引取纯值
        """
        return self._rd().get(*_key_args(table, key, key2))

    def vals(self, table: str, key: Optional[str] = None,
             key2: Optional[str] = None) -> Any:
        """读取纯值：精确键返回 ``[值]``，表达式返回 ``[值, ...]``（不带键）。

        参数同 :meth:`get`。与 ``get`` 的区别在于表达式结果只保留值列；
        结果为 ``QueryResult``，``list(...)`` 或 ``.do()`` 可物化为纯列表。

        Example::

            rd.vals("退市*")                      # ['600421', ...]
            rd.vals("日k", "600633", "2026062*")  # [行情 dict, ...]
        """
        return self._rd().vals(*_key_args(table, key, key2))

    def keys(self, table: str, key: Optional[str] = None,
             key2: Optional[str] = None) -> list:
        """列出匹配的完整键（物化为纯 ``list[str]``）。

        Args:
            table: 表名，支持 ``*`` 前缀通配（如 ``"退市*"``）。
            key: 键1（如股票代码），可含表达式。
            key2: 键2（如日期前缀 ``"202606*"``）。

        注意：只传到某一级时，仅返回该级键上**有值**的精确匹配；枚举
        子键需要低一级用通配（如 ``keys("日k", "600633", "*")``）。

        Example::

            rd.keys("日k", "600633", "202606*")  # ['日k:600633:20260601', ...]
        """
        return list(self._rd().keys(*_key_args(table, key, key2)))

    def len(self, table: str, key: Optional[str] = None,
            key2: Optional[str] = None) -> int:
        """统计匹配的键数量（物化为纯 ``int``）。参数与注意事项同 :meth:`keys`。"""
        return self._rd().len(*_key_args(table, key, key2)).do()

    # ================= 写 =================

    def set(self, table: str, *keys_and_value: Any) -> int:
        """覆盖写入，按参数个数自动选择键层级，成功返回 1。

        三种形式（末位参数恒为值）::

            rd.set("mydb", value)                  # 表级值
            rd.set("mydb", key, value)             # 二级键
            rd.set("mydb", key, key2, value)       # 三级键（推荐）

        值类型：``int / float / str / bytes / list / dict / DataFrame``。
        同键写入即覆盖。字段级修改可用链式：
        ``rd.get(t, k, k2).get("子键").val(新值)``。
        """
        return self._rd().set(table, *keys_and_value)

    def setl(self, table: str, *keys_and_value: Any) -> int:
        """列表左插写入：把值插到该键列表值的最前端。

        参数形式同 :meth:`set`。原值为列表时左插；原值为标量/不存在时
        重建为仅含新值的列表（原标量丢弃）。
        """
        return self._rd().setl(table, *keys_and_value)

    def setr(self, table: str, *keys_and_value: Any) -> int:
        """列表右追写入：把值追加到该键列表值的末尾。

        参数形式同 :meth:`set`。原值为列表时追加；原值为标量/不存在时
        重建为仅含新值的列表（原标量丢弃）。适合逐日追加的时间序列。
        """
        return self._rd().setr(table, *keys_and_value)

    def delete(self, table: str, key: Optional[str] = None,
               key2: Optional[str] = None) -> int:
        """删除匹配的键，返回删除状态。

        参数同 :meth:`get`；键位置可用 ``*`` 通配批量删除。
        注意整表清空须用 ``rd.delete("mydb", "*")``——冒号串内嵌通配
        （如 ``"mydb:*"``）对 delete 不生效。
        """
        return self._rd().delete(*_key_args(table, key, key2))

    # ================= 批量与管线 =================

    def mget(self, table: str, key: Optional[str] = None,
             key2: Optional[str] = None) -> Any:
        """读命令的管线形式（协议与 :meth:`get` 相同）。

        供 :meth:`pipe` 队列内使用；直接调用时行为同 ``get``。
        """
        return self._rd().mget(*_key_args(table, key, key2))

    def mset(self, table: str, *keys_and_value: Any) -> int:
        """写命令的管线形式（协议与 :meth:`set` 相同）。

        供 :meth:`pipe` 队列内使用；直接调用时行为同 ``set``。
        """
        return self._rd().mset(table, *keys_and_value)

    def pipe(self) -> Pipeline:
        """创建批量命令管线：一次网络往返执行多条命令。

        读写命令不得混入同一管线（协议限制，混用会死锁）；同步上下文
        用 ``pp.do()``，协程内用 ``await pp``；单条命令返回结果本体，
        多条命令返回结果列表。

        Example::

            pp = rd.pipe()                      # 纯读管线
            for code in ["000001", "600633"]:
                pp.mget("日k", code, "20260824")
            bars = pp.do()

            pp = rd.pipe()                      # 纯写管线
            for i in range(1000):
                pp.mset("mydb", "factor", f"k{i}", i)
            pp.do()
        """
        return Pipeline(self._rd().pipe())

    # ================= 连接与底层 =================

    def close(self) -> None:
        """关闭底层连接。之后的调用会自动重建连接。"""
        self._rd().close()

    def send(self, message: bytes) -> Any:
        """发送原始协议帧（异步模式）。

        message 为 ``tobytes()`` 所示的帧格式
        （``"<长度>\\nexec\\n<长度>\\ncmd=...\\n\\n"``）。仅供协议级
        调试/扩展，常规读写请使用上面的类型化方法。
        """
        return self._rd().send(message)

    def send_sync(self, message: bytes) -> Any:
        """发送原始协议帧（同步模式）。帧格式与注意事项同 :meth:`send`。"""
        return self._rd().send_sync(message)

    def __repr__(self):
        return f"<RdClient native={self._rd()!r}>"
