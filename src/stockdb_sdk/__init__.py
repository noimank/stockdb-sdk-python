"""StockDB Python SDK.

针对 free-stockdb（https://github.com/hello245m/free-stockdb）项目的第三方
Python SDK，提供：

* 统一的高层 ``get_data`` / ``get_data_async`` 接口：日 K / 分钟 K / 周 K /
  月 K 查询，支持多股票批量、复权、字段投影与 DataFrame 输出。
* 技术指标计算（:func:`indicator`）与自定义指数合成（:func:`index`），
  由原生 :mod:`stockdb_sdk.zb_core` 加速。
* 板块（概念 / 申万行业）检索（:data:`bk`）。
* 原生 K-V 接口的类型化门面（:class:`RdClient`，经 :data:`rd` 使用），
  全部 13 个方法均带显式签名与完整语义文档。

所有公开接口均为显式参数签名（无 ``*args`` / ``**kwargs``），IDE 补全、
``help()`` 与静态检查开箱可用。股票代码使用 6 位裸代码（如 ``"000001"``）；
带交易所后缀的写法（如 ``"000001.SZ"``）会被自动归一化。

典型用法::

    import stockdb_sdk as sdk

    sdk.init(host="127.0.0.1", port=7899)  # 默认端点，本机可省略

    bars = sdk.get_data("000001", start="20260701", end="20260824")
    codes = sdk.rd.vals("退市*")            # 原生 K-V 读取
"""

from . import stockdb
from . import zb_core
from ._board import BoardIndex, bk
from ._client import StockDBClient
from ._default import get_data, get_data_async, init, rd
from ._indicator import index, indicator
from ._raw import Pipeline, RdClient, StockdbError

__version__ = "0.2.1"

__all__ = [
    "init",
    "StockDBClient",
    "RdClient",
    "Pipeline",
    "StockdbError",
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
