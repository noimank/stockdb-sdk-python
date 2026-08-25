"""进程级默认端点：init 配置、惰性单例客户端与 rd 透传代理。"""

from typing import Optional

from ._board import reset_default_connection as _reset_boards
from ._board import warm_default_connection as _warm_boards
from ._client import StockDBClient
from ._connection import configure, get_default_raw_rd

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
        原生底层连接对象（:mod:`stockdb_sdk.stockdb` 的 rd）。

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
    return raw


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


class _RdProxy:
    """原生 rd 连接的惰性代理，始终指向当前默认服务端（纯透传，无高层方法）。"""

    def __getattr__(self, name):
        return getattr(get_default_raw_rd(), name)

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(get_default_raw_rd(), name, value)

    def __dir__(self):
        return sorted(set(dir(get_default_raw_rd()) + dir(self.__class__)))

    def __repr__(self):
        return repr(get_default_raw_rd())


rd = _RdProxy()


def get_data(*args, **kwargs):
    """查询 K 线数据（转发到默认客户端）。

    参数与 :meth:`StockDBClient.get_data` 完全一致，详见其文档。
    """
    return get_default_client().get_data(*args, **kwargs)


async def get_data_async(*args, **kwargs):
    """异步查询 K 线数据（转发到默认客户端）。

    参数与 :meth:`StockDBClient.get_data_async` 完全一致，详见其文档。
    """
    return await get_default_client().get_data_async(*args, **kwargs)
