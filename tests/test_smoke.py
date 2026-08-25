"""包基础冒烟测试：公共 API 与原生模块可正常导入。"""

import importlib

import stockdb_sdk as sdk


def test_version():
    assert sdk.__version__ == "0.2.1"


def test_public_api():
    for name in sdk.__all__:
        assert hasattr(sdk, name), f"missing public API: {name}"


def test_removed_legacy_entries():
    # 0.2.0 移除的旧入口，防止意外回归
    for name in ("gp", "zb", "jisuan", "zhishu", "get_default_client"):
        assert not hasattr(sdk, name)
    assert not hasattr(sdk.rd, "get_data")


def test_native_modules_importable():
    stockdb = importlib.import_module("stockdb_sdk.stockdb")
    zb_core = importlib.import_module("stockdb_sdk.zb_core")
    assert hasattr(stockdb, "rd")
    assert hasattr(stockdb, "init")
    assert hasattr(zb_core, "BATCH")
