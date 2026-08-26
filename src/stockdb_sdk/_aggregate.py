"""客户端周期聚合：5/15/30/60 分钟由 1 分钟合并，周/月由日 K 合并。

分钟聚合按交易时段感知分桶（09:30-11:30、13:00-15:00 共 240 个交易分钟），
因此 60 分钟线得到的是 09:30/10:30/13:00/14:00 四段，而非自然小时的
09:00/10:00/13:00/14:00；周/月以组内最后一个交易日为标签。

聚合行固定包含 ``code/date/open/high/low/close/pre_close/pct_chg/volume/amount``
（有名称时附 ``name``），其余字段（估值、换手等）不具跨周期可加性，不输出。

服务端分钟表对停牌日会写入占位 bar，实测两种形态：OHLC 全为
``None``、或全为 ``0``（volume=0、pre_close=None）。A 股价格恒为正，
两种形态都没有可聚合的价格，聚合前一律丢弃——某桶因此为空时整桶
不输出，而不是产出 None/0 价格的合并行（``max()`` 空序列崩溃 /
下游 ``price > 0`` 校验拒收）。
"""

import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple

_SESSIONS: Tuple[Tuple[int, int], Tuple[int, int]] = ((570, 690), (780, 900))
_SESSION_MINUTES = 120


def _to_traded(minute_of_day: int) -> Optional[int]:
    """把一天内的分钟数映射为第几个交易分钟（0..239），盘外返回 None。

    收盘分钟 11:30 / 15:00 也有 K 线（收盘价所在），归入各自时段的
    最后一个交易分钟，避免被当作盘外数据丢弃。
    """
    if minute_of_day == 690:
        return _SESSION_MINUTES - 1
    if minute_of_day == 900:
        return 2 * _SESSION_MINUTES - 1
    for i, (start, stop) in enumerate(_SESSIONS):
        if start <= minute_of_day < stop:
            return minute_of_day - start + i * _SESSION_MINUTES
    return None


def _from_traded(index: int) -> int:
    """把交易分钟序号还原为一天内的分钟数。"""
    start = _SESSIONS[0 if index < _SESSION_MINUTES else 1][0]
    offset = index if index < _SESSION_MINUTES else index - _SESSION_MINUTES
    return start + offset


def _usable(value: Any) -> bool:
    """价格可用：非 None 且 > 0（0 与 None 一样是停牌占位）。"""
    return value is not None and value > 0


def _priced(r: Dict[str, Any]) -> bool:
    """行内至少有一个可用价格（停牌占位 bar 的 OHLC 全为 None 或全为 0）。"""
    return any(_usable(r.get(f)) for f in ("open", "high", "low", "close"))


def _merge(rows: List[Dict[str, Any]], date: int,
           prev_close: Optional[float]) -> Dict[str, Any]:
    opens = [r["open"] for r in rows if _usable(r.get("open"))]
    closes = [r["close"] for r in rows if _usable(r.get("close"))]
    highs = [r["high"] for r in rows if _usable(r.get("high"))]
    lows = [r["low"] for r in rows if _usable(r.get("low"))]
    row: Dict[str, Any] = {
        "code": rows[0].get("code"),
        "name": rows[-1].get("name"),
        "date": date,
        "open": opens[0] if opens else None,
        "close": closes[-1] if closes else None,
        "high": max(highs) if highs else None,
        "low": min(lows) if lows else None,
        "volume": sum(r.get("volume", 0) for r in rows),
        "amount": sum(r.get("amount", 0.0) for r in rows),
        "pre_close": prev_close,
        "pct_chg": None,
    }
    if prev_close:
        try:
            row["pct_chg"] = round((row["close"] / prev_close - 1) * 100, 3)
        except (TypeError, ZeroDivisionError):
            pass
    return row


def resample_minutes(rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    """把升序 1 分钟行合并为 n 分钟行（n 为 5/15/30/60）。"""
    buckets: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for r in rows:
        ts = r.get("date")
        if not isinstance(ts, int) or not _priced(r):
            continue
        day, clock = divmod(ts // 100, 10000)
        traded = _to_traded(clock // 100 * 60 + clock % 100)
        if traded is None:
            continue
        buckets.setdefault((day, traded // n), []).append(r)
    out: List[Dict[str, Any]] = []
    prev_close: Optional[float] = None
    for (day, bucket), group in buckets.items():
        start = _from_traded(bucket * n)
        date = day * 1000000 + (start // 60) * 10000 + (start % 60) * 100
        if prev_close is None:
            prev_close = group[0].get("pre_close")
        out.append(_merge(group, date, prev_close))
        prev_close = out[-1]["close"]
    return out


def resample_daily(rows: List[Dict[str, Any]], freq: str) -> List[Dict[str, Any]]:
    """把升序日 K 行合并为周线（``1w``）或月线（``1M``）。"""
    groups: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
    for r in rows:
        if not _priced(r):
            continue
        try:
            day = _dt.datetime.strptime(str(r.get("date"))[:8], "%Y%m%d")
        except ValueError:
            continue
        iso = day.isocalendar()
        key = (iso.year, iso.week) if freq == "1w" else (day.year, day.month)
        groups.setdefault(key, []).append(r)
    out: List[Dict[str, Any]] = []
    prev_close: Optional[float] = None
    for group in groups.values():
        if prev_close is None:
            prev_close = group[0].get("pre_close")
        out.append(_merge(group, group[-1]["date"], prev_close))
        prev_close = out[-1]["close"]
    return out
