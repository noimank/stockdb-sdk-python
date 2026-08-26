"""StockDB Python SDK —— 基于 HTTP 的跨平台只读行情接口。

针对 free-stockdb（https://github.com/hello245m/free-stockdb）本地数据库
的第三方只读 SDK：K 线查询（日 / 周 / 月 / 1-60 分钟、前/后复权、字段
投影、DataFrame 输出）、股票与板块（概念 / 申万行业）双向检索，以及原生
三级键只读门面。纯 Python 实现，Windows / macOS / Linux 通用，只需本地
（或局域网内）运行着 stockdb 服务。

典型用法::

    import stockdb_sdk as sdk

    sdk.init(host="127.0.0.1", port=7899)   # 默认端点，本机可省略

    rows = sdk.get("600633", start="20260701", end="20260824")
    df = sdk.get(["600633", "000001"], freq="5m", as_df=True)
    boards = sdk.boards("600633")           # 该股所属板块
    members = sdk.members("AI芯片")         # 板块成员代码
"""

from typing import List

from . import _transport
from ._boards import boards, members
from ._boards import reset as _reset_boards
from ._kline import get, get_async
from ._rd import rd
from ._transport import DEFAULT_HOST, DEFAULT_PORT
from ._transport import init as _init_transport

__version__ = "0.3.1"

__all__ = [
    "init",
    "get",
    "get_async",
    "codes",
    "delisted",
    "boards",
    "members",
    "rd",
    "__version__",
]


def init(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """配置服务端点（默认 ``http://127.0.0.1:7899``，本机可省略）。

    切换端点会重建连接并清空板块索引；行情与复权因子均为按调用
    取用，无跨调用状态需要清理。
    """
    _init_transport(host, port)
    _reset_boards()


def codes() -> List[str]:
    """全部在市股票代码（升序）。"""
    table = _transport.fetch("get", t="股票代码")
    return sorted(code for group in table.values() for code in group)


def delisted() -> List[str]:
    """已退市股票代码（升序，去重——服务端退市表存在同一代码多行）。"""
    return sorted({c for c in _transport.fetch("vals", t="退市*")
                   if isinstance(c, str)})
