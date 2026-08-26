"""K 线主接口：:func:`get` / :func:`get_async`。

查询规划（全部基于实测协议）：

* 精确代码：``k1=key:<代码>`` + ``k2`` 区间，一次请求；
* 代码前缀（含 ``*``）：候选数 ≤ :data:`_ENUM_LIMIT` 时先枚举
  在市+退市代码清单（两个小请求），再逐代码精准查询——服务端
  不支持前缀+区间组合，宽前缀只能 ``k1=all:`` 全市场单请求后
  客户端过滤，响应体积与「市场 × 区间」成正权，窄前缀走枚举
  可把传输与瞬时内存缩小到实际涉及的代码；
* 代码列表：去重后逐代码请求；同步版 ≥ :data:`_POOL_MIN` 只时用
  线程池并发，异步版 ``asyncio.gather`` 并发；
* ``1d`` / ``1m`` 原生直查；``5m/15m/30m/60m`` 由 1 分钟聚合、
  ``1w/1M`` 由日 K 聚合（客户端，见 :mod:`._aggregate`）；
* ``fq="qfq"/"hfq"`` 先折算再聚合（与官方口径一致），因子按调用
  取用（见 :mod:`._fq`），无跨调用状态；
* 服务端返回降序，本层统一排序为时间升序后交付。

内存契约：除 :mod:`._boards` 的板块索引外，本 SDK 不在调用间保留
任何行情/因子数据；单次调用的峰值内存即该次返回的数据本身。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Union

import pandas as pd

from . import _aggregate, _fq, _transport

_MINUTE_FREQS = frozenset({"1m", "5m", "15m", "30m", "60m"})
_FREQS = frozenset({"1m", "5m", "15m", "30m", "60m", "1d", "1w", "1M"})
_FQS = frozenset({None, "none", "qfq", "hfq"})

#: 前缀候选代码不超过该值时逐代码精准查询，超过则全市场单请求过滤。
_ENUM_LIMIT = 64
#: 同步多代码请求启用线程池的下限与最大线程数。
_POOL_MIN = 4
_POOL_WORKERS = 8

CodeSpec = Union[str, Sequence[str]]


def _validate(freq: str, fq: Optional[str]) -> None:
    if freq not in _FREQS:
        raise ValueError(f"freq 只支持 {sorted(_FREQS)}，收到 {freq!r}")
    if fq not in _FQS:
        raise ValueError(f"fq 只支持 None/'none'/'qfq'/'hfq'，收到 {fq!r}")


def _bound(value: Any, minute: bool, is_start: bool) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    if not s.isdigit() or len(s) not in (8, 14):
        raise ValueError(f"日期须为 8 位或 14 位数字，收到 {value!r}")
    if not minute:
        return s[:8]
    if len(s) == 14:
        return s
    return s + ("000000" if is_start else "235959")


def _k2(lo: Optional[str], hi: Optional[str], minute: bool) -> str:
    if lo is None and hi is None:
        return "all:"
    width = 14 if minute else 8
    return f"fwd:{lo or '0' * width},{hi or '9' * width}"


def _fetch_rows(code: Optional[str], lo: Optional[str], hi: Optional[str],
                freq: str) -> List[Dict[str, Any]]:
    table = "分钟k" if freq in _MINUTE_FREQS else "日k"
    rows = _transport.fetch(
        "vals", t=table,
        k1="all:" if code is None else f"key:{code}",
        k2=_k2(lo, hi, freq in _MINUTE_FREQS))
    return [r for r in rows if isinstance(r, dict)]


async def _afetch_rows(code: Optional[str], lo: Optional[str],
                       hi: Optional[str], freq: str) -> List[Dict[str, Any]]:
    table = "分钟k" if freq in _MINUTE_FREQS else "日k"
    rows = await _transport.afetch(
        "vals", t=table,
        k1="all:" if code is None else f"key:{code}",
        k2=_k2(lo, hi, freq in _MINUTE_FREQS))
    return [r for r in rows if isinstance(r, dict)]


def _universe() -> List[str]:
    """在市 + 退市代码全集（前缀枚举用，两个小请求，不缓存，已去重）。"""
    table = _transport.fetch("get", t="股票代码")
    codes = [c for group in table.values() for c in group]
    codes += [c for c in _transport.fetch("vals", t="退市*")
              if isinstance(c, str)]
    return list(dict.fromkeys(codes))


async def _auniverse() -> List[str]:
    table = await _transport.afetch("get", t="股票代码")
    codes = [c for group in table.values() for c in group]
    codes += [c for c in await _transport.afetch("vals", t="退市*")
              if isinstance(c, str)]
    return codes


def _fetch_many(codes: List[str], lo: Optional[str], hi: Optional[str],
                freq: str) -> Dict[str, List[Dict[str, Any]]]:
    if len(codes) >= _POOL_MIN:
        with ThreadPoolExecutor(min(_POOL_WORKERS, len(codes))) as pool:
            results = list(pool.map(
                lambda c: _fetch_rows(c, lo, hi, freq), codes))
    else:
        results = [_fetch_rows(c, lo, hi, freq) for c in codes]
    return {c: r for c, r in zip(codes, results) if r}


async def _afetch_many(codes: List[str], lo: Optional[str],
                       hi: Optional[str], freq: str) -> Dict[str, List]:
    rows_list = await asyncio.gather(
        *[_afetch_rows(c, lo, hi, freq) for c in codes])
    return {c: r for c, r in zip(codes, rows_list) if r}


def _fetch_groups(code: Union[str, List[str]], lo: Optional[str],
                  hi: Optional[str], freq: str) -> Dict[str, List]:
    """拉取阶段：返回 {代码: 行}，多代码时丢弃空结果。"""
    if isinstance(code, str):
        if "*" not in code:
            return {code: _fetch_rows(code, lo, hi, freq)}
        prefix = code[:-1]
        if len(prefix) >= 2:
            candidates = [c for c in _universe() if c.startswith(prefix)]
            if len(candidates) <= _ENUM_LIMIT:
                return _fetch_many(candidates, lo, hi, freq)
        rows = _fetch_rows(None, lo, hi, freq)
        rows.sort(key=lambda r: r.get("date", 0))
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            row_code = r.get("code", "")
            if row_code.startswith(prefix):
                groups.setdefault(row_code, []).append(r)
        return groups
    return _fetch_many(list(dict.fromkeys(code)), lo, hi, freq)


async def _afetch_groups(code: Union[str, List[str]], lo: Optional[str],
                         hi: Optional[str], freq: str) -> Dict[str, List]:
    if isinstance(code, str):
        if "*" not in code:
            return {code: await _afetch_rows(code, lo, hi, freq)}
        prefix = code[:-1]
        if len(prefix) >= 2:
            candidates = [c for c in await _auniverse()
                          if c.startswith(prefix)]
            if len(candidates) <= _ENUM_LIMIT:
                return await _afetch_many(candidates, lo, hi, freq)
        rows = await _afetch_rows(None, lo, hi, freq)
        rows.sort(key=lambda r: r.get("date", 0))
        groups = {}
        for r in rows:
            row_code = r.get("code", "")
            if row_code.startswith(prefix):
                groups.setdefault(row_code, []).append(r)
        return groups
    return await _afetch_many(list(dict.fromkeys(code)), lo, hi, freq)


def _finalize(rows: List[Dict[str, Any]], code: str, freq: str,
              fq: Optional[str],
              factors: Dict[str, "_fq.Entry"]) -> List[Dict[str, Any]]:
    rows.sort(key=lambda r: r.get("date", 0))
    if fq in ("qfq", "hfq"):
        rows = _fq.apply(rows, code, fq, factors)
    if freq in ("5m", "15m", "30m", "60m"):
        rows = _aggregate.resample_minutes(rows, int(freq[:-1]))
    elif freq in ("1w", "1M"):
        rows = _aggregate.resample_daily(rows, freq)
    return rows


def _project(data: Any, fields: Optional[Union[str, Sequence[str]]]) -> Any:
    if fields is None:
        return data
    if isinstance(fields, str):
        flist = [f.strip() for f in fields.split(",") if f.strip()]
    else:
        flist = list(fields)

    def proj(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return rows
        missing = [f for f in flist if f not in rows[0]]
        if missing:
            raise ValueError(
                f"字段不存在: {missing}；该数据可用字段: {sorted(rows[0])}")
        return [{f: r[f] for f in flist} for r in rows]

    if isinstance(data, dict):
        return {code: proj(rows) for code, rows in data.items()}
    return proj(data)


def _to_df(data: Any, as_df: bool) -> Any:
    if not as_df:
        return data
    if isinstance(data, dict):
        rows = [r for group in data.values() for r in group]
        return pd.DataFrame(rows)
    return pd.DataFrame(data)


def _normalize(code: CodeSpec) -> Union[str, List[str]]:
    if isinstance(code, str):
        return code.strip().split(".")[0]
    if isinstance(code, Sequence):
        return [str(c).strip().split(".")[0] for c in code]
    raise TypeError(f"code 须为 str 或 str 序列，收到 {type(code).__name__}")


def get(code: CodeSpec, *, start: Optional[str] = None, end: Optional[str] = None,
        freq: str = "1d", fq: Optional[str] = "qfq", fields: Optional[Union[str,
        Sequence[str]]] = None, as_df: bool = False) -> Any:
    """查询 K 线（时间升序）。

    Args:
        code: 单个代码（``"600633"``，可带后缀 ``"600633.SH"``）、代码
            前缀（``"60063*"``、``"*"`` 全市场）或代码列表。
        start / end: 8 位日期（分钟周期亦接受 14 位，8 位自动展开为
            整个交易日）；均可省略，省略 ``end`` 表示至今。
        freq: ``"1d"``（默认）/ ``"1m"`` / ``"5m"`` / ``"15m"`` /
            ``"30m"`` / ``"60m"`` / ``"1w"`` / ``"1M"``（月线，大写 M）。
        fq: ``"qfq"`` 前复权（默认）/ ``"hfq"`` 后复权 / ``None`` 或
            ``"none"`` 不复权。
        fields: 字段投影，``"date,close"`` 或 ``["date", "close"]``。
        as_df: 为 ``True`` 时返回 :class:`pandas.DataFrame`。

    Returns:
        单个代码返回行列表（或 DataFrame）；前缀与列表返回
        ``{代码: 行列表}``（或所有代码合并的单个 DataFrame，行内含
        ``code`` 字段）。前缀命中不超过 64 只代码时逐只精准查询，
        更宽的前缀为全市场单请求后过滤。

    Example::

        import stockdb_sdk as sdk

        rows = sdk.get("600633", start="20260701", end="20260824")
        df = sdk.get(["600633", "000001"], freq="1m", start="20260824",
                     end="20260824", as_df=True)
    """
    _validate(freq, fq)
    code = _normalize(code)
    lo = _bound(start, freq in _MINUTE_FREQS, True)
    hi = _bound(end, freq in _MINUTE_FREQS, False)

    single = isinstance(code, str) and "*" not in code
    groups = _fetch_groups(code, lo, hi, freq)
    factors = _fq.prepare(list(groups)) if fq in ("qfq", "hfq") else {}
    data: Any = {c: _finalize(g, c, freq, fq, factors)
                 for c, g in groups.items()}
    if single:
        data = data[code]
    return _to_df(_project(data, fields), as_df)


async def get_async(code: CodeSpec, *, start: Optional[str] = None,
                    end: Optional[str] = None, freq: str = "1d",
                    fq: Optional[str] = "qfq",
                    fields: Optional[Union[str, Sequence[str]]] = None,
                    as_df: bool = False) -> Any:
    """异步版 :func:`get`，参数与返回完全一致。

    代码列表会并发请求（``asyncio.gather``）。Example::

        rows = await sdk.get_async("600633", start="20260701")
    """
    _validate(freq, fq)
    code = _normalize(code)
    lo = _bound(start, freq in _MINUTE_FREQS, True)
    hi = _bound(end, freq in _MINUTE_FREQS, False)

    single = isinstance(code, str) and "*" not in code
    groups = await _afetch_groups(code, lo, hi, freq)
    factors = (await _fq.aprepare(list(groups))
               if fq in ("qfq", "hfq") else {})
    data: Any = {c: _finalize(g, c, freq, fq, factors)
                 for c, g in groups.items()}
    if single:
        data = data[code]
    return _to_df(_project(data, fields), as_df)
