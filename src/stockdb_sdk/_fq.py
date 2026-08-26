"""复权因子：按调用取用，边查询边折算，零跨调用状态。

面向"查遍全市场"的数据管道场景，本模块不在调用之间保留任何因子
缓存：每次查询只为当次涉及的代码取因子——

* 少量代码（< :data:`_BULK_THRESHOLD`）：逐只小请求
  ``get t=复权 k1=key:<代码> k2=all:``（每只约几 KB）；
* 多代码：一次 ``get t=复权*`` 全量请求（约 5MB），解析后只保留
  当次需要的代码，用完即弃。

折算口径与官方客户端一致：

* ``hfq``（后复权）：``价格 × f_cur``；
* ``qfq``（前复权）：``价格 × f_cur / f_latest``；
* 其中 ``f_cur`` 为 ``<= 当日`` 的最近一次除权事件的 ``cum``（无事件
  则 1.0），``f_latest`` 为该代码最新事件的 ``cum``；
* 仅折算 ``open/high/low/close/pre_close``；基金/ETF（1/5 开头）保留
  3 位小数，股票 2 位；比例近似 1 时跳过，不产生浮点噪音；
* **原地修改**行对象——:mod:`._kline` 传入的行是本次调用新解析的，
  归调用方独有，拷贝只会徒增峰值内存。
"""

import asyncio
from bisect import bisect_right
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import _transport

PRICE_FIELDS = ("open", "high", "low", "close", "pre_close")

#: 参与复权的代码数达到该值时，改用一次全量请求取代逐只小请求。
_BULK_THRESHOLD = 64

Entry = Tuple[List[str], List[float]]


def _entry(pairs: list) -> Optional[Entry]:
    """把 ``[[复权:代码:日期, {cum: ...}], ...]`` 折成 (日期升序, cum)。"""
    items = sorted((key.split(":")[2], float(val["cum"]))
                   for key, val in pairs)
    return [d for d, _ in items], [c for _, c in items]


def _parse_bulk(pairs: list, needed: frozenset) -> Dict[str, Entry]:
    """全量响应中只保留当次需要的代码。"""
    bucket: Dict[str, list] = {}
    for key, val in pairs:
        code = key.split(":")[1]
        if code in needed:
            bucket.setdefault(code, []).append((key.split(":")[2],
                                                float(val["cum"])))
    out: Dict[str, Entry] = {}
    for code, items in bucket.items():
        items.sort()
        out[code] = ([d for d, _ in items], [c for _, c in items])
    return out


def prepare(codes: List[str]) -> Dict[str, Entry]:
    """同步取因子：少量代码逐只小请求，多代码一次全量后只留所需。"""
    uniq = list(dict.fromkeys(codes))
    if not uniq:
        return {}
    if len(uniq) < _BULK_THRESHOLD:
        out: Dict[str, Entry] = {}
        for code in uniq:
            pairs = _transport.fetch("get", t="复权",
                                     k1=f"key:{code}", k2="all:")
            if pairs:
                out[code] = _entry(pairs)
        return out
    return _parse_bulk(_transport.fetch("get", t="复权*"),
                       frozenset(uniq))


async def aprepare(codes: List[str]) -> Dict[str, Entry]:
    """异步版 :func:`prepare`（复权取数全走异步，不阻塞事件循环）。"""
    uniq = list(dict.fromkeys(codes))
    if not uniq:
        return {}
    if len(uniq) < _BULK_THRESHOLD:
        pair_lists = await asyncio.gather(
            *[_transport.afetch("get", t="复权", k1=f"key:{code}",
                                k2="all:") for code in uniq])
        return {code: _entry(pairs) for code, pairs in zip(uniq, pair_lists)
                if pairs}
    return _parse_bulk(await _transport.afetch("get", t="复权*"),
                       frozenset(uniq))


def apply(rows: List[Dict[str, Any]], code: str, fq: str,
          factors: Dict[str, Entry]) -> List[Dict[str, Any]]:
    """对单只代码的升序 K 线行原地执行 ``qfq`` / ``hfq`` 折算。

    ``factors`` 为本次调用经 :func:`prepare` / :func:`aprepare`
    取得的因子表；无该代码记录时原样返回。
    """
    entry = factors.get(code)
    if not entry:
        return rows
    dates, cums = entry
    f_latest = cums[-1]
    decimals = 3 if code.startswith(("1", "5")) else 2
    for r in rows:
        day = str(r.get("date", ""))[:8]
        idx = bisect_right(dates, day) - 1
        f_cur = cums[idx] if idx >= 0 else 1.0
        ratio = f_latest / f_cur if fq == "qfq" else 1.0 / f_cur
        if not day or abs(ratio - 1.0) < 1e-6:
            continue
        for field in PRICE_FIELDS:
            value = r.get(field)
            if value is not None:
                try:
                    r[field] = round(float(value) / ratio, decimals)
                except (TypeError, ValueError):
                    pass
    return rows
