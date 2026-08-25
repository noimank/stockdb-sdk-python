"""包基础冒烟测试：验证公共 API 与原生模块可正常导入。"""

import importlib

import pytest


def test_version():
    import stockdb_sdk as sdk

    assert sdk.__version__


def test_public_api():
    import stockdb_sdk as sdk

    for name in [
        "init",
        "StockDBClient",
        "BoardIndex",
        "get_data",
        "get_data_async",
        "jisuan",
        "gp",
        "rd",
        "bk",
        "zb",
    ]:
        assert hasattr(sdk, name), f"missing public API: {name}"


def test_native_modules_importable():
    stockdb = importlib.import_module("stockdb_sdk.stockdb")
    zb_core = importlib.import_module("stockdb_sdk.zb_core")
    assert hasattr(stockdb, "rd")
    assert hasattr(stockdb, "init")
    assert hasattr(zb_core, "BATCH")
