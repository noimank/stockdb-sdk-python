"""进程级默认端点：init 配置、惰性单例客户端与 rd 透传代理。"""

from typing import Any, Dict, List, Optional, Union

from ._board import reset_default_connection as _reset_boards
from ._board import warm_default_connection as _warm_boards
from ._client import StockDBClient
from ._connection import configure, get_default_raw_rd
from ._raw import RdClient

_default_client: Optional[StockDBClient] = None


def init(host: str = "127.0.0.1", port: int = 7899,
         socket_timeout: Optional[int] = None,
         password: Optional[str] = None,
         warm: bool = True):
    """配置 SDK 默认服务端，并可选地预热 SDK 数据。

    该函数只需在进程内调用一次（也可重复调用以切换服务端）。
    配置完成后，模块级 :func:`stockdb_sdk.get_data` /
    :func:`stockdb_sdk.indicator` 等入口即指向该服务端。

    Args:
        host: 服务端地址，默认 ``"127.0.0.1"``。
        port: 服务端端口，默认 ``7899``。
        socket_timeout: socket 超时（秒）。本机默认 ``1``，远程默认 ``3``。
        password: 访问密码（服务端开启鉴权时必填）。
        warm: 是否预热。为 ``True`` 时会预加载复权因子与板块映射，
            使首次业务调用更快。

    Returns:
        原生 K-V 客户端门面（:class:`stockdb_sdk.RdClient`）。

    Example::

        import stockdb_sdk as sdk

        sdk.init(host="127.0.0.1", port=7899)
        bars = sdk.get_data("000001", start="20260701")
    """
    global _default_client
    if socket_timeout is None:
        socket_timeout = 1 if host in ("127.0.0.1", "localhost", "::1") else 3

    raw = configure(host, port, socket_timeout, password)
    _default_client = None  # 旧默认客户端不得继续持有旧端点
    if warm:
        warm_default_connection()
    return RdClient(raw)


def get_default_client() -> StockDBClient:
    """惰性获取当前端点的高层 SDK 客户端。"""
    global _default_client
    if _default_client is None:
        _default_client = StockDBClient(_raw_client=get_default_raw_rd())
    return _default_client


def warm_default_connection() -> StockDBClient:
    """预加载复权因子与板块映射，使首次业务调用更快。"""
    client = get_default_client()
    _reset_boards()
    _warm_boards()
    return client


# 惰性默认端点门面：每次调用解析当前端点，跟随 init() 切换
rd = RdClient()


def get_data(
    code: Union[str, List[str]],
    start: Optional[str] = None,
    end: Optional[str] = None,
    frequency: str = "1d",
    fields: Optional[Union[str, List[str]]] = None,
    limit: Optional[int] = None,
    desc: bool = False,
    as_df: bool = False,
    fq: Optional[str] = "qfq",
) -> Union[List[Any], Dict[str, List[Any]], Any]:
    """同步查询 K 线数据（默认端点，转发到 :class:`StockDBClient`）。

    参数与 :meth:`StockDBClient.get_data` 完全一致，详见其文档。

    Example::

        bars = sdk.get_data("000001", start="20260701", end="20260824")
    """
    return get_default_client().get_data(
        code, start, end, frequency, fields, limit, desc, as_df, fq)


async def get_data_async(
    code: Union[str, List[str]],
    start: Optional[str] = None,
    end: Optional[str] = None,
    frequency: str = "1d",
    fields: Optional[Union[str, List[str]]] = None,
    limit: Optional[int] = None,
    desc: bool = False,
    as_df: bool = False,
    fq: Optional[str] = "qfq",
) -> Union[List[Any], Dict[str, List[Any]], Any]:
    """异步查询 K 线数据（默认端点，转发到 :class:`StockDBClient`）。

    参数与 :meth:`StockDBClient.get_data_async` 完全一致，需用 ``await``
    调用，详见其文档。

    Example::

        bars = await sdk.get_data_async("000001", start="20260701", end="N")
    """
    return await get_default_client().get_data_async(
        code, start, end, frequency, fields, limit, desc, as_df, fq)
