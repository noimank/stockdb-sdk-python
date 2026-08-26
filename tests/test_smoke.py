"""冒烟测试：导入面与版本。"""

import stockdb_sdk as sdk


def test_version():
    assert sdk.__version__ == "0.3.1"


def test_public_surface():
    for name in ("init", "get", "get_async", "codes", "delisted",
                 "boards", "members"):
        assert callable(getattr(sdk, name)), name
    for method in ("get", "vals", "keys", "len"):
        assert callable(getattr(sdk.rd, method)), method


def test_default_endpoint():
    from stockdb_sdk._transport import DEFAULT_HOST, DEFAULT_PORT
    assert (DEFAULT_HOST, DEFAULT_PORT) == ("127.0.0.1", 7899)
