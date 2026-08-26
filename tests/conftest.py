"""测试公共设施：本地无 stockdb 服务时自动跳过集成测试。"""

import httpx
import pytest


def _server_up() -> bool:
    try:
        httpx.get("http://127.0.0.1:7899/",
                  params={"cmd": "get", "t": "股票代码"}, timeout=5)
        return True
    except Exception:
        return False


requires_server = pytest.mark.skipif(
    not _server_up(), reason="本地 stockdb 服务未运行 (127.0.0.1:7899)")
