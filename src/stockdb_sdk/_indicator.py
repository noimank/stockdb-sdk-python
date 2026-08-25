"""技术指标计算与自定义指数合成（由原生 zb_core 引擎加速）。"""

from __future__ import annotations

from math import nan
from typing import Any

from ._client import _normalize_codes
from ._default import get_default_client
from .zb_core import BATCH, BATCH_CROSS, ZHISHU

DEFAULT_START = "20260302"
# 字段在 _load_rows 返回的行情矩阵中的下标（0/1 为 code_i/date）
DATA_FIELD_INDEX = {
    "open": 2,
    "high": 3,
    "low": 4,
    "close": 5,
    "volume": 6,
    "amount": 7,
    "float_mv": 8,
    "total_mv": 9,
}
BASIC_INDICATORS = {"ma", "ema", "sma", "wma", "dma", "std", "sum", "hhv", "llv", "ref"}
EXTENDED_INDICATORS = {
    "macd", "kdj", "rsi", "wr", "bias", "boll", "psy", "cci", "atr", "bbi",
    "dmi", "taq", "ktn", "trix", "vr", "cr", "emv", "dpo", "brar", "dfma",
    "mtm", "mass", "roc", "expma", "obv", "mfi", "asi", "xsii",
}


def _freq(frequency: str) -> str:
    return {"day": "1d", "d": "1d", "min": "1m"}.get(str(frequency).lower(), frequency)


def _codes(codes: Any) -> tuple[list[str], bool]:
    if isinstance(codes, str):
        return _normalize_codes(codes), True
    return _normalize_codes(list(codes)), False


def _row_value(row: list, idx: int, default: float = 0.0) -> float:
    if idx >= len(row) or row[idx] is None:
        return default
    try:
        return float(row[idx])
    except Exception:
        return default


def _load_rows(codes: list[str], frequency: str, start: str | None, end: str | None, fq: str | None):
    """拉取行情并整理为原生引擎需要的平行矩阵（各列与 code_i 一一对应）。"""
    fields = "date,open,high,low,close,volume,amount,float_mv,total_mv"
    data = get_default_client().get_data(
        codes, start=start or DEFAULT_START, end=end,
        frequency=_freq(frequency), fields=fields, fq=fq)

    code_i: list[int] = []
    date: list[int] = []
    open_: list[float] = []
    high: list[float] = []
    low: list[float] = []
    close: list[float] = []
    volume: list[float] = []
    amount: list[float] = []
    float_mv: list[float] = []
    total_mv: list[float] = []

    for i, code in enumerate(codes):
        rows = sorted((row for row in data.get(code, []) if row and row[0] is not None),
                      key=lambda row: int(row[0]))
        for row in rows:
            code_i.append(i)
            date.append(int(row[0]))
            open_.append(_row_value(row, 1, nan))
            high.append(_row_value(row, 2, nan))
            low.append(_row_value(row, 3, nan))
            close.append(_row_value(row, 4, nan))
            volume.append(_row_value(row, 5, 0.0))
            amount.append(_row_value(row, 6, 0.0))
            float_mv.append(_row_value(row, 7, 0.0))
            total_mv.append(_row_value(row, 8, 0.0))

    return code_i, date, open_, high, low, close, volume, amount, float_mv, total_mv


def _indicator_result(codes: list[str], raw, single: bool):
    code_i, dates, names, cols = raw
    out = {code: [] for code in codes}
    for row_i, ci in enumerate(code_i):
        item = {"date": dates[row_i]}
        for name, col in zip(names, cols):
            item[name] = col[row_i]
        out[codes[ci]].append(item)
    return out[codes[0]] if single else out


def _cross_indicator_result(codes: list[str], raw, single: bool):
    code_i, dates, names, cols = raw
    out = {code: [] for code in codes}
    has_named_signals = any(name.endswith("_cross") for name in names)
    for row_i, ci in enumerate(code_i):
        item = {"date": dates[row_i]}
        for name, col in zip(names, cols):
            if name.endswith("_cross"):
                item[name] = int(col[row_i])
            elif name == "cross":
                value = int(col[row_i])
                item[name] = bool(value == 1) if has_named_signals else value
            else:
                item[name] = col[row_i]
        out[codes[ci]].append(item)
    return out[codes[0]] if single else out


def _data_fields(fields: Any) -> list[str]:
    if fields is None:
        return ["close"]

    out = []
    if isinstance(fields, (list, tuple)):
        items = fields
    else:
        items = str(fields).replace("，", ",").split(",")
    for item in items:
        item = str(item).strip().lower()
        if not item:
            continue
        if item not in DATA_FIELD_INDEX:
            raise ValueError(f"unknown fields item: {item}")
        out.append(item)
    return out or ["close"]


def _with_input_as_close(arrays, values: list[float]):
    values = list(values)
    return (arrays[0], arrays[1], arrays[2], arrays[3], arrays[4], values,
            arrays[6], arrays[7], arrays[8], arrays[9])


def _rename_indicator(raw, prefix: str):
    code_i, dates, names, cols = raw
    names = [f"{prefix}_{name}" for name in names]
    return code_i, dates, names, cols


def _merge_field_results(codes: list[str], raws: list[tuple], single: bool):
    out = {code: {} for code in codes}
    for raw in raws:
        code_i, dates, names, cols = raw
        for row_i, ci in enumerate(code_i):
            code = codes[ci]
            date = dates[row_i]
            item = out[code].setdefault(date, {"date": date})
            for name, col in zip(names, cols):
                item[name] = col[row_i]

    result = {code: [rows[date] for date in sorted(rows)] for code, rows in out.items()}
    return result[codes[0]] if single else result


def _indicator_names(name: Any) -> list[str]:
    names = []
    if isinstance(name, (list, tuple)):
        items = name
    else:
        items = str(name).replace("，", ",").split(",")
    for item in items:
        item = str(item).strip().lower()
        if item:
            names.append(item)
    if not names:
        raise ValueError("indicator name is empty")
    return names


def _int_list(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, str):
        items = value.replace("，", ",").split(",")
        return [int(item.strip()) for item in items if item.strip()]
    if isinstance(value, (list, tuple)):
        out = []
        for item in value:
            if item is None or item == "":
                continue
            out.append(int(item))
        return out
    return [int(value)]


def _format_param_mapping_error(title: str, names: list[str], n: Any) -> str:
    if isinstance(n, (list, tuple)):
        values = list(n)
    else:
        values = [n]

    lines = [title, ""]
    max_len = max(len(names), len(values))
    for i in range(max_len):
        name = names[i] if i < len(names) else "X EXTRA"
        if i < len(values):
            lines.append(f"'{name}': {values[i]!r},")
        else:
            lines.append(f"'{name}': X ERROR,")
    return "\n".join(lines).rstrip(",")


def _indicator_params(names: list[str], n: Any) -> list[list[int]]:
    if len(names) == 1:
        return [_int_list(n)]

    if n is None:
        return [[] for _ in names]

    if not isinstance(n, (list, tuple)):
        raise ValueError(_format_param_mapping_error(
            "multi indicator n must align with names:", names, n
        ))

    if len(n) != len(names):
        raise ValueError(_format_param_mapping_error(
            "multi indicator n length mismatch:", names, n
        ))

    return [_int_list(item) for item in n]


def _zhishu_result(raw):
    dates, opens, highs, lows, closes, pct, volumes, amounts, counts = raw
    return [
        {
            "date": dates[i],
            "open": opens[i],
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "pct_chg": pct[i],
            "volume": volumes[i],
            "amount": amounts[i],
            "stock_count": counts[i],
        }
        for i in range(len(dates))
    ]


def indicator(
    name: str,
    codes: Any,
    *,
    start: str | None = None,
    end: str | None = None,
    frequency: str = "1d",
    fq: str | None = "qfq",
    fields: Any = None,
    n: Any = None,
    cross: Any = False,
):
    """计算技术指标。

    支持 MACD、KDJ、RSI、BOLL 等 28 个扩展指标及 MA/EMA 等基础指标，
    并可附加金叉/死叉（``cross``）信号。

    Args:
        name: 指标名，支持逗号分隔或列表，如 ``"macd"``、``"macd,kdj"``、
            ``["ma", "ema"]``。基础指标：``ma/ema/sma/wma/dma/std/sum/hhv/
            llv/ref``；扩展指标：``macd/kdj/rsi/wr/bias/boll/psy/cci/atr/
            bbi/dmi/taq/ktn/trix/vr/cr/emv/dpo/brar/dfma/mtm/mass/roc/
            expma/obv/mfi/asi/xsii``。
        codes: 股票代码或代码列表（``"000001"`` 或
            ``["000001", "600633"]``，带后缀写法自动归一化）。
        start: 起始日期 ``"YYYYMMDD"``，默认 :data:`DEFAULT_START`。
        end: 结束日期 ``"YYYYMMDD"``，``"N"`` 表示上不封顶。
            注意：不传 ``end`` 且不传 ``start`` 时只会取到默认起始日的单日数据。
        frequency: 周期，``"1d"``（默认，亦接受 ``"day"``）、
            ``"1m"``（分钟，亦接受 ``"min"``）。
        fq: 复权方式，``"qfq"``（默认）/``"hfq"``/``None``。
        fields: 基础指标的输入字段（如 ``"close"``/``"open"``，可多项），
            仅对 ma/ema 等基础指标生效；多项字段会分别计算并合并。
        n: 指标参数。单个指标传整数或逗号串（如 ``n=5``、``n="5,10,20"``）；
            多个指标时传与 ``name`` 等长的列表（如 ``["5,10,20", None, "12,26,9"]``）。
        cross: 交叉信号。``False`` 不计算；``True`` 只返回信号
            （单项信号 1=金叉 / -1=死叉 / 0=无交叉，多指标 cross 字段为
            全部金叉时的 True）；``"with_value"`` 同时保留指标数值与信号。

    Returns:
        单股票时返回 ``List[Dict]``（每项含 ``date`` 与指标值）；
        多股票时返回 ``Dict[code, List[Dict]]``。

    Example::

        import stockdb_sdk as sdk

        macd = sdk.indicator("macd", "000001", start="20260701", end="N")
        ma = sdk.indicator("ma", "000001", end="N", n=[5, 10], cross=True)
        kdj = sdk.indicator("kdj", ["000001", "600633"], end="N")
    """
    code_list, single = _codes(codes)
    names = _indicator_names(name)

    supported = BASIC_INDICATORS | EXTENDED_INDICATORS
    for key in names:
        if key not in supported:
            hint = "（指数合成请使用 index()）" if key == "zhishu" else ""
            raise ValueError(f"unsupported indicator: {key}{hint}")

    if cross is not False and cross is not True and cross != "with_value":
        raise ValueError('cross only supports False, True, or "with_value"')

    params = _indicator_params(names, n)
    basic_only = all(key in BASIC_INDICATORS for key in names)
    use_cross = cross is True or cross == "with_value"

    # 参数校验前置：非法请求不触发数据加载
    if not basic_only and fields is not None:
        raise ValueError("fields only supports ma/ema/sma/wma/dma/std/sum/hhv/llv/ref")
    data_fields = _data_fields(fields) if basic_only else None
    if use_cross and basic_only and len(data_fields) != 1:
        raise ValueError('cross=True/cross="with_value" only supports one fields item')

    arrays = _load_rows(code_list, frequency, start, end, fq)

    if use_cross:
        keep_values = cross == "with_value"
        if basic_only:
            # 基础指标支持自定义输入字段：把该字段的值放到 close 槽位传给引擎
            arrays = _with_input_as_close(arrays, arrays[DATA_FIELD_INDEX[data_fields[0]]])
        raw = BATCH_CROSS(names, params, *arrays[:7], keep_values)
        return _cross_indicator_result(code_list, raw, single)

    if basic_only:
        raws = []
        for data_field in data_fields:
            field_arrays = _with_input_as_close(arrays, arrays[DATA_FIELD_INDEX[data_field]])
            raw = BATCH(names, params, *field_arrays[:7])
            if len(data_fields) > 1:
                raw = _rename_indicator(raw, data_field)
            raws.append(raw)
        if len(raws) == 1:
            return _indicator_result(code_list, raws[0], single)
        return _merge_field_results(code_list, raws, single)

    raw = BATCH(names, params, *arrays[:7])
    return _indicator_result(code_list, raw, single)


def index(
    codes: Any,
    *,
    start: str | None = None,
    end: str | None = None,
    frequency: str = "1d",
    fq: str | None = "qfq",
    method: int = 1,
    base: float = 1000.0,
):
    """合成自定义指数。

    Args:
        codes: 成分股票代码或代码列表。
        start: 起始日期 ``"YYYYMMDD"``，默认 :data:`DEFAULT_START`。
        end: 结束日期 ``"YYYYMMDD"``，``"N"`` 表示上不封顶。
        frequency: 周期，``"1d"``（默认）或 ``"1m"``。
        fq: 复权方式，``"qfq"``（默认）/``"hfq"``/``None``。
        method: 加权方式。``1`` 等权（默认）、``2`` 流通市值、``3`` 成交额、
            ``4`` 成交量、``5`` 总市值。分钟 K 不含市值字段，仅支持
            ``method=1/3/4``。
        base: 指数初始基点，默认 ``1000.0``。

    Returns:
        ``List[Dict]``：每项含 ``date/open/high/low/close/pct_chg/volume/
        amount/stock_count``。首个交易日仅用于确立基点，不计入返回。

    Example::

        import stockdb_sdk as sdk

        idx = sdk.index(["000001", "600633"], start="20260601", end="N", method=1)
    """
    code_list, _single = _codes(codes)
    if _freq(frequency) != "1d" and method in (2, 5):
        raise ValueError("分钟K不含 float_mv/total_mv，只支持 method=1/3/4")
    arrays = _load_rows(code_list, frequency, start, end, fq)
    return _zhishu_result(ZHISHU(*arrays, method=method, base=base))
