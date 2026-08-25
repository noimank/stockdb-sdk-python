"""StockDB Python SDK.

针对 free-stockdb（https://github.com/hello245m/free-stockdb）项目的第三方
Python SDK，提供：

* 统一的高层 ``get_data`` 接口：日 K / 分钟 K / 周 K / 月 K 查询，
  支持同步与异步、多股票批量、复权、字段投影与 DataFrame 输出。
* 原生底层接口的完整透传（:mod:`stockdb_sdk.stockdb`）。
* 板块（概念 / 申万行业）检索（:data:`bk`）。
* 技术指标计算引擎（:data:`zb` / :func:`jisuan`），
  由原生 :mod:`stockdb_sdk.zb_core` 加速。

典型用法::

    import stockdb_sdk as sdk

    # 1. 配置服务端（默认 127.0.0.1:7899）
    sdk.init(host="127.0.0.1", port=7899)

    # 2. 查询日 K 线
    bars = sdk.get_data("000001.SZ", start="20260101", end="20260131")
"""

from . import stockdb
from . import zb_core
from ._sdk import (
    init,
    StockDBClient,
    get_default_client,
    get_default_raw_rd,
    gp,
    rd,
)
from ._zhibiao import bk, zb, jisuan, BoardIndex

__version__ = "0.1.0"

__all__ = [
    "init",
    "StockDBClient",
    "BoardIndex",
    "get_default_client",
    "get_default_raw_rd",
    "get_data",
    "get_data_async",
    "jisuan",
    "gp",
    "rd",
    "bk",
    "zb",
    "stockdb",
    "zb_core",
    "__version__",
]


def get_data(*args, **kwargs):
    """查询 K 线数据（转发到默认客户端）。

    等价于 ``stockdb_sdk.gp.get_data(...)``。参数与
    :meth:`StockDBClient.get_data` 完全一致，详见其文档。
    """
    return get_default_client().get_data(*args, **kwargs)


async def get_data_async(*args, **kwargs):
    """异步查询 K 线数据（转发到默认客户端）。

    等价于 ``await stockdb_sdk.gp.get_data_async(...)``。参数与
    :meth:`StockDBClient.get_data_async` 完全一致，详见其文档。
    """
    return await get_default_client().get_data_async(*args, **kwargs)
