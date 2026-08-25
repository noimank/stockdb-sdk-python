"""默认服务端端点状态与原生连接的构建。"""

from typing import Optional

from .stockdb import init as _native_init
from .stockdb import rd as _raw_rd

_default_connection = {
    "host": "127.0.0.1",
    "port": 7899,
    "socket_timeout": 1,
    "password": None,
}
_default_raw_rd = None


def _connect(host: str, port: int, socket_timeout: int, password: Optional[str]):
    """按端点参数构建原生连接；默认端点直接复用二进制模块自带的 rd。"""
    if host == "127.0.0.1" and port == 7899 and password is None:
        return _raw_rd
    return _native_init(
        host=host,
        port=port,
        socket_timeout=socket_timeout,
        password=password,
    )


def configure(host: str, port: int, socket_timeout: int, password: Optional[str]):
    """把默认端点切换到指定服务端，并立即重建原生连接。"""
    global _default_raw_rd
    _default_connection.update({
        "host": host,
        "port": port,
        "socket_timeout": socket_timeout,
        "password": password,
    })
    # 显式切换端点总是新建连接（即使指向默认端点），确保旧连接状态不残留
    _default_raw_rd = _native_init(
        host=host,
        port=port,
        socket_timeout=socket_timeout,
        password=password,
    )
    return _default_raw_rd


def get_default_raw_rd():
    """惰性获取当前默认端点的原生连接。"""
    global _default_raw_rd
    if _default_raw_rd is None:
        _default_raw_rd = _connect(
            host=_default_connection["host"],
            port=_default_connection["port"],
            socket_timeout=_default_connection["socket_timeout"],
            password=_default_connection["password"],
        )
    return _default_raw_rd
