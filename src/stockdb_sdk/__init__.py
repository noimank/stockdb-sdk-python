"""StockDB Python SDK.

针对 free-stockdb（https://github.com/hello245m/free-stockdb）项目的第三方
Python SDK，提供：

* 统一的高层 ``get_data`` / ``get_data_async`` 接口：日 K / 分钟 K / 周 K /
  月 K 查询，支持多股票批量、复权、字段投影与 DataFrame 输出。
* 技术指标计算（:func:`indicator`）与自定义指数合成（:func:`index`），
  由原生 :mod:`stockdb_sdk.zb_core` 加速。
* 板块（概念 / 申万行业）检索（:data:`bk`）。
* 原生底层接口的完整透传（:data:`rd` / :mod:`stockdb_sdk.stockdb`）。

股票代码使用 6 位裸代码（如 ``"000001"``）；带交易所后缀的写法
（如 ``"000001.SZ"``）会被自动归一化。

典型用法::

    import stockdb_sdk as sdk

    sdk.init(host="127.0.0.1", port=7899)  # 默认端点，本机可省略

    bars = sdk.get_data("000001", start="20260701", end="20260824")
"""

from . import stockdb
from . import zb_core
from ._board import BoardIndex, bk
from ._client import StockDBClient
from ._default import get_data, get_data_async, init, rd
from ._indicator import index, indicator

__version__ = "0.2.0"

__all__ = [
    "init",
    "StockDBClient",
    "BoardIndex",
    "get_data",
    "get_data_async",
    "indicator",
    "index",
    "bk",
    "rd",
    "stockdb",
    "zb_core",
    "__version__",
]
