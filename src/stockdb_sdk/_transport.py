"""HTTP 传输层：端点配置与对 stockdb 服务的只读命令请求。

服务端协议（实测固化，v0.3.x）：

* 命令仅 ``get`` / ``vals`` / ``keys`` / ``len`` 四个，全部只读；
* 键有三种传法：
  - ``t=表:键1:键2`` 冒号串，**通配符 ``*`` 只能出现在最后一段**
    且全键至多一个（``日k:60063*`` / ``日k:600633:202606*`` / ``退市*``）；
  - ``k1`` / ``k2`` 参数形式，值必须带前缀修饰符：``key:<精确值>``、
    ``all:<全量>``、``fwd:<起>,<止>``（**返回降序**，由本层负责归一升序）；
    裸值不生效（返回空甚至超时），且不支持通配；
  - ``keys`` / ``len`` 只支持 ``k1`` / ``k2`` 参数形式。
* 无服务端字段投影（``f=`` / ``fields=`` 被忽略），投影在客户端做。

同步用 :class:`httpx.Client`，异步用 :class:`httpx.AsyncClient`，
各自惰性创建并在 :func:`init` 切换端点时重建。
"""

from typing import Any, Optional

import asyncio

import httpx

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7899

_TIMEOUT = httpx.Timeout(10.0, read=120.0)


class _State:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    sync: Optional[httpx.Client] = None
    async_client: Optional[httpx.AsyncClient] = None
    async_loop: Optional[asyncio.AbstractEventLoop] = None


_state = _State()


def init(host: str, port: int) -> None:
    """切换服务端点并丢弃旧连接与各模块缓存。"""
    if _state.sync is not None:
        _state.sync.close()
    _state.host = host
    _state.port = port
    _state.sync = None
    _state.async_client = None


def _params(cmd: str, t: Optional[str], k1: Optional[str],
            k2: Optional[str]) -> dict:
    params = {"cmd": cmd}
    if t is not None:
        params["t"] = t
    if k1 is not None:
        params["k1"] = k1
    if k2 is not None:
        params["k2"] = k2
    return params


def fetch(cmd: str, t: Optional[str] = None, k1: Optional[str] = None,
          k2: Optional[str] = None) -> Any:
    """同步执行一条只读命令并返回解析后的 JSON。"""
    if _state.sync is None:
        _state.sync = httpx.Client(
            base_url=f"http://{_state.host}:{_state.port}", timeout=_TIMEOUT)
    r = _state.sync.get("/", params=_params(cmd, t, k1, k2))
    r.raise_for_status()
    return r.json()


async def afetch(cmd: str, t: Optional[str] = None, k1: Optional[str] = None,
                 k2: Optional[str] = None) -> Any:
    """异步执行一条只读命令并返回解析后的 JSON。

    AsyncClient 绑定创建它的事件循环，因此按循环缓存：换循环
    （如多次 ``asyncio.run``）时重建；旧循环已销毁，旧客户端直接
    丢弃交给 GC，不做跨循环 close。
    """
    loop = asyncio.get_running_loop()
    if _state.async_client is None or _state.async_loop is not loop:
        _state.async_client = httpx.AsyncClient(
            base_url=f"http://{_state.host}:{_state.port}", timeout=_TIMEOUT)
        _state.async_loop = loop
    r = await _state.async_client.get("/", params=_params(cmd, t, k1, k2))
    r.raise_for_status()
    return r.json()
