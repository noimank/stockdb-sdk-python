"""K 线高层客户端：统一的 get_data 查询与周/月 K、多分钟 K 聚合。"""

import bisect
import datetime
import warnings
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from ._connection import _connect, _default_connection

MINUTE_FREQUENCIES = ("1m", "5m", "15m", "30m", "60m")


def _normalize_codes(codes: Union[str, List[str]]) -> List[str]:
    """把 ``"000001.SZ"`` 等带后缀代码归一化为数据库使用的 6 位裸代码。

    注意不能使用二进制模块的 ``normalize_code``——那是带调用配额的在线
    补充行情接口，不适合在每次查询前调用。
    """
    def normalize(c) -> str:
        return str(c).strip().split(".")[0]

    if isinstance(codes, str):
        return [normalize(codes)]
    return [normalize(c) for c in codes]


def _build_time_query(start: Optional[str], end: Optional[str],
                      frequency: str) -> str:
    """根据起止日期构建底层范围查询表达式（恒为升序，降序由调用方反转）。

    分钟级查询允许 8 位日期，自动补全为覆盖全天交易时段的 14 位时间。
    """
    if frequency in MINUTE_FREQUENCIES:
        if start and len(start) == 8:
            start = start + "000000"
        if end and len(end) == 8:
            end = end + "235959"

    if not start and not end:
        return "*"

    # 单日查询：start 存在且（end 缺省或与 start 相同）时退化为一次点查询
    if start and (not end or start == end):
        return start

    s_val = start if start else "N"
    e_val = end if end else "N"
    return f"{s_val}>{e_val}"


def _fields_list(fields: Optional[Union[str, List[str]]]) -> List[str]:
    if isinstance(fields, list):
        return fields
    if isinstance(fields, str):
        return [f.strip() for f in fields.split(",")]
    return []


def _filter_fields(data_list: List[Dict[str, Any]],
                   fields: Optional[Union[str, List[str]]]) -> List[List[Any]]:
    """按 fields 投影为二维列表，保持与底层接口一致的天然二维数组结构。"""
    if not fields:
        return data_list
    names = _fields_list(fields)
    return [[item.get(f) for f in names] for item in data_list]


def _to_dataframe(data: Any, is_batch: bool,
                  fields: Optional[Union[str, List[str]]] = None) -> Any:
    """转换为 pandas DataFrame。"""
    columns = _fields_list(fields)

    if is_batch:
        all_records = []
        for code, records in data.items():
            for r in records:
                record = dict(zip(columns, r)) if isinstance(r, list) else r.copy()
                record["code"] = code
                all_records.append(record)
        if not all_records:
            return pd.DataFrame()
        df = pd.DataFrame(all_records)
        cols = ["code"] + [col for col in df.columns if col != "code"]
        return df[cols]

    if not data:
        return pd.DataFrame()
    if isinstance(data[0], list):
        return pd.DataFrame(data, columns=columns)
    return pd.DataFrame(data)


def _merge_to_period(daily_data: List[Dict[str, Any]],
                     frequency: str) -> List[Dict[str, Any]]:
    """将日 K 聚合为周 K（``'1w'``）或月 K（``'1M'``）。输入须按日期升序。"""
    if not daily_data:
        return []

    # LevelDB 天然按日期升序，无需排序
    grouped = defaultdict(list)
    for item in daily_data:
        date_val = item.get("date")
        if not date_val:
            continue
        try:
            dt = datetime.datetime.strptime(str(date_val), "%Y%m%d")
        except ValueError:
            continue

        if frequency == "1w":
            iso = dt.isocalendar()
            key = (iso[0], iso[1])  # (ISO 年, ISO 周)
        else:
            key = (dt.year, dt.month)

        grouped[key].append(item)

    merged_list = []
    for key in sorted(grouped.keys()):
        items = grouped[key]
        first_item = items[0]
        last_item = items[-1]

        # None 表示该日该字段没有有效观测值，不能当作 0 参与聚合。
        def valid_values(field: str) -> List[Any]:
            return [x[field] for x in items if x.get(field) is not None]

        open_values = valid_values("open")
        high_values = valid_values("high")
        low_values = valid_values("low")
        close_values = valid_values("close")

        # 没有可用的 OHLC 数据时，无法构成可信的周期 K 线。
        if not (open_values and high_values and low_values and close_values):
            continue

        high = max(high_values)
        low = min(low_values)
        volume_values = valid_values("volume")
        amount_values = valid_values("amount")
        volume = sum(volume_values) if volume_values else None
        amount = sum(amount_values) if amount_values else None

        merged_item = {
            "date": last_item["date"],  # 以周期内最后一个交易日日期作为标识
            "code": last_item["code"],
            "name": last_item.get("name", ""),
            "open": open_values[0],
            "high": high,
            "low": low,
            "close": close_values[-1],
            "volume": volume,
            "amount": amount,
        }

        # 前收盘价：续接上一周期收盘，否则取周期首日的前收盘
        if merged_list:
            pre_close = merged_list[-1]["close"]
        else:
            pre_close = first_item.get("pre_close")
            if pre_close is None:
                pre_close = open_values[0]
        merged_item["pre_close"] = pre_close

        # 涨跌幅与振幅
        if pre_close:
            merged_item["pct_chg"] = round(
                ((merged_item["close"] - pre_close) / pre_close) * 100, 3)
            merged_item["amplitude"] = round(((high - low) / pre_close) * 100, 3)
        else:
            merged_item["pct_chg"] = 0.0
            merged_item["amplitude"] = 0.0

        # 换手率加和、量比求均值
        turnover_values = valid_values("turnover")
        if turnover_values:
            merged_item["turnover"] = round(sum(turnover_values), 3)
        vol_ratio_values = valid_values("vol_ratio")
        if vol_ratio_values:
            merged_item["vol_ratio"] = round(
                sum(vol_ratio_values) / len(vol_ratio_values), 3)

        # 复制周期末端的截面属性（如市值、ST 状态等）
        for field in ("pe_ttm", "pb", "total_mv", "float_mv", "float_share",
                      "total_share", "is_st"):
            if field in last_item:
                merged_item[field] = last_item[field]

        merged_list.append(merged_item)

    return merged_list


def _merge_minutes_to_period(minute_data: List[Dict[str, Any]],
                             frequency: str) -> List[Dict[str, Any]]:
    """将一分钟 K 聚合为 5m/15m/30m/60m K，按交易时段对齐分组边界。输入须按时间升序。"""
    if not minute_data:
        return []

    interval = int(frequency[:-1])  # '5m' -> 5

    def trading_elapsed(minute_of_day: int) -> Optional[int]:
        """交易日内序号：09:30 为 1，11:30 为 120，13:01 为 121，15:00 为 240。"""
        if 570 <= minute_of_day <= 690:
            return minute_of_day - 570
        if 780 <= minute_of_day <= 900:
            if minute_of_day == 780:
                return 121
            return 120 + (minute_of_day - 780)
        return None

    def elapsed_to_minute_of_day(elapsed: int) -> int:
        if elapsed <= 120:
            return 570 + elapsed
        if elapsed > 240:
            elapsed = 240
        return 780 + (elapsed - 120)

    grouped = defaultdict(list)
    for item in minute_data:
        date_val = item.get("date")
        if not date_val:
            continue
        try:
            date_int = int(date_val)
        except (TypeError, ValueError):
            continue
        if date_int < 10000000000000:  # 非 14 位分钟时间戳
            continue

        ymd = date_int // 1000000
        hour = (date_int // 10000) % 100
        minute = (date_int // 100) % 100
        elapsed = trading_elapsed(hour * 60 + minute)
        if elapsed is None:
            continue

        # 以对齐的周期结束时刻作为分组键（09:30 的 elapsed 为 0，归入首个周期）
        if elapsed <= 0:
            group_end_elapsed = interval
        else:
            group_end_elapsed = ((elapsed - 1) // interval + 1) * interval
        grouped[(ymd, group_end_elapsed)].append(item)

    merged_list = []
    for idx, (ymd, end_elapsed) in enumerate(sorted(grouped.keys())):
        items = grouped[(ymd, end_elapsed)]
        first_item = items[0]
        last_item = items[-1]

        high = max(x["high"] for x in items if "high" in x)
        low = min(x["low"] for x in items if "low" in x)
        volume = sum(x["volume"] for x in items if "volume" in x)
        amount = sum(x["amount"] for x in items if "amount" in x)

        end_minute_of_day = elapsed_to_minute_of_day(end_elapsed)
        end_hour = end_minute_of_day // 60
        end_minute = end_minute_of_day % 60
        if end_hour >= 24:  # 溢出保护
            end_hour = 23
            end_minute = 59
        aligned_date_int = ymd * 1000000 + end_hour * 10000 + end_minute * 100

        merged_item = {
            "date": aligned_date_int,
            "code": last_item["code"],
            "name": last_item.get("name", ""),
            "open": first_item["open"],
            "high": high,
            "low": low,
            "close": last_item["close"],
            "volume": volume,
            "amount": amount,
        }

        if idx > 0:
            pre_close = merged_list[-1]["close"]
        else:
            pre_close = first_item.get("pre_close", first_item["open"])
        merged_item["pre_close"] = pre_close

        if pre_close:
            merged_item["pct_chg"] = round(
                ((merged_item["close"] - pre_close) / pre_close) * 100, 3)
            merged_item["amplitude"] = round(((high - low) / pre_close) * 100, 3)
        else:
            merged_item["pct_chg"] = 0.0
            merged_item["amplitude"] = 0.0

        for field in ("vol_ratio", "pe_ttm", "pb", "total_mv", "float_mv",
                      "float_share", "total_share", "is_st"):
            if field in last_item:
                merged_item[field] = last_item[field]

        merged_list.append(merged_item)

    return merged_list


def _parse_pipe_results(codes: List[str], raw: Any) -> Dict[str, List[Dict[str, Any]]]:
    """解析 pipeline 批量查询结果为 {code: [records]}。"""
    if not isinstance(raw, list):
        raw = [raw]
    data_dict = {}
    for c, items in zip(codes, raw):
        if isinstance(items, dict):
            data_dict[c] = [items]
        elif isinstance(items, list):
            data_dict[c] = [item[1] for item in items
                            if isinstance(item, (list, tuple)) and len(item) > 1]
        else:
            data_dict[c] = []
    return data_dict


def _wrap_result(data_dict, codes, is_batch, as_df, fields):
    """按批量/单股与 as_df 封装最终返回格式。"""
    if is_batch:
        return _to_dataframe(data_dict, True, fields) if as_df else data_dict
    single_res = data_dict[codes[0]]
    return _to_dataframe(single_res, False, fields) if as_df else single_res


class StockDBClient:
    """StockDB 股票数据库的 Python SDK 客户端。

    提供统一的 :meth:`get_data` / :meth:`get_data_async` 接口，支持同步/异步
    操作，并支持在内存中合成周 K、月 K 及多分钟 K 线。

    Attributes:
        rd: 底层原生连接对象，可直接调用其全部方法（如 ``rd.vals``、``rd.pipe``）。
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 password: Optional[str] = None,
                 socket_timeout: Optional[int] = None,
                 _raw_client=None):
        """初始化 StockDB 客户端连接。

        若 ``host`` 等参数未显式给出，则回退到 :func:`stockdb_sdk.init`
        配置的默认值。实例化时会一次性预加载全部复权因子到内存，
        用于后续复权折算。

        Args:
            host: 服务端地址，默认取自全局配置。
            port: 服务端端口，默认取自全局配置。
            password: 访问密码，默认取自全局配置。
            socket_timeout: socket 超时（秒），默认取自全局配置。
            _raw_client: 内部参数，传入已有的原生连接对象。

        Example::

            client = StockDBClient(host="127.0.0.1", port=7899)
            bars = client.get_data("000001", start="20260701")
        """
        if host is None:
            host = _default_connection["host"]
        if port is None:
            port = _default_connection["port"]
        if password is None:
            password = _default_connection["password"]
        if socket_timeout is None:
            socket_timeout = _default_connection["socket_timeout"]

        if _raw_client is not None:
            self.rd = _raw_client
        else:
            self.rd = _connect(host, port, socket_timeout, password)

        # 一次性预加载全部复权因子到内存（LevelDB 天然有序，无需排序）
        self._fq_dates: Dict[str, List[str]] = {}   # {code: [date_str, ...]}
        self._fq_cums: Dict[str, List[float]] = {}  # {code: [cum, ...]}
        try:
            tmp = defaultdict(list)
            for item in self.rd.get("复权*").get("cum"):
                key_str, cum_val = item[0], float(item[1])
                _, code, date = key_str.split(":")
                tmp[code].append((date, cum_val))
            for code, pairs in tmp.items():
                self._fq_dates[code] = [p[0] for p in pairs]
                self._fq_cums[code] = [p[1] for p in pairs]
        except Exception as e:
            warnings.warn(
                f"复权因子加载失败（{e}）；fq='qfq'/'hfq' 将退化为不复权数据。",
                RuntimeWarning,
                stacklevel=2,
            )

    # ================= 查询计划与取数 =================

    @staticmethod
    def _prepare_query(code: Union[str, List[str]], start: Optional[str],
                       end: Optional[str], frequency: str):
        is_batch = isinstance(code, (list, tuple))
        codes = _normalize_codes(code)
        table = "分钟k" if frequency in MINUTE_FREQUENCIES else "日k"
        time_query = _build_time_query(start, end, frequency)
        return codes, is_batch, table, time_query

    def _fetch_sync(self, codes: List[str], table: str, time_query: str):
        if len(codes) == 1:
            return {codes[0]: list(self.rd.vals(table, codes[0], time_query))}
        pp = self.rd.pipe()
        for c in codes:
            pp.mget(table, c, time_query)
        return _parse_pipe_results(codes, pp.do())

    async def _fetch_async(self, codes: List[str], table: str, time_query: str):
        if len(codes) == 1:
            return {codes[0]: await self.rd.vals(table, codes[0], time_query)}
        pp = self.rd.pipe()
        for c in codes:
            pp.mget(table, c, time_query)
        return _parse_pipe_results(codes, await pp)

    def _finalize(self, data_dict, codes, frequency, fq, desc, limit, fields):
        """过滤无效记录 -> 复权 -> 周期聚合 -> 降序 -> 限额 -> 字段投影。"""
        for c in codes:
            records = [r for r in data_dict[c] if isinstance(r, dict)]

            if fq in ("qfq", "hfq"):
                records = self._apply_fq_in_memory(c, records, fq)

            if frequency in ("1w", "1M"):
                records = _merge_to_period(records, frequency)
            elif frequency in ("5m", "15m", "30m", "60m"):
                records = _merge_minutes_to_period(records, frequency)

            # 取数恒为升序（聚合也依赖升序），降序在此统一反转
            if desc:
                records = records[::-1]

            if limit is not None:
                records = records[:limit]

            if fields:
                records = _filter_fields(records, fields)

            data_dict[c] = records
        return data_dict

    # ================= 复权 =================

    def _apply_fq_in_memory(self, code: str, records: List[Dict[str, Any]],
                            fq_type: str) -> List[Dict[str, Any]]:
        """在内存中对 K 线记录执行动态前复权（qfq）或后复权（hfq）折算。

        复权因子已在 :meth:`__init__` 中预加载到 ``_fq_dates`` / ``_fq_cums``。
        """
        if not records or fq_type not in ("qfq", "hfq"):
            return records

        dates = self._fq_dates.get(code)
        cums = self._fq_cums.get(code)
        if not dates:
            return records

        # 前复权需要最新因子（列表天然有序，最后一个即最新）
        if fq_type == "qfq":
            f_latest = cums[-1]

        # 基金/ETF 代码（1/5 开头）净值类价格保留 3 位小数，股票保留 2 位
        decimals = 3 if code.startswith(("1", "5")) else 2
        adjusted_records = []

        for r in records:
            # 分钟 K 的 date 是 14 位整数（如 20260629150000），日 K 是 8 位
            r_date_str = str(r.get("date", ""))[:8]
            if not r_date_str:
                adjusted_records.append(r)
                continue

            # 二分查找：<= r_date_str 的最大除权日对应的 cum
            idx = bisect.bisect_right(dates, r_date_str) - 1
            f_current = cums[idx] if idx >= 0 else 1.0

            if fq_type == "qfq":
                ratio = f_latest / f_current
            else:
                ratio = 1.0 / f_current

            if abs(ratio - 1.0) < 1e-6:
                adjusted_records.append(r)
                continue

            # 拷贝记录字典，避免直接修改底层数据库缓存的对象
            r_copy = r.copy()
            for field in ("open", "high", "low", "close", "pre_close"):
                if field in r_copy and r_copy[field] is not None:
                    try:
                        r_copy[field] = round(float(r_copy[field]) / ratio, decimals)
                    except Exception:
                        pass
            adjusted_records.append(r_copy)

        return adjusted_records

    # ================= 同步接口 =================

    def get_data(
        self,
        code: Union[str, List[str]],
        start: Optional[str] = None,
        end: Optional[str] = None,
        frequency: str = "1d",
        fields: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = None,
        desc: bool = False,
        as_df: bool = False,
        fq: Optional[str] = "qfq",
    ) -> Union[List[Any], Dict[str, List[Any]], Any]:
        """同步获取 K 线数据（日 K、分钟 K、周 K、月 K）。

        Args:
            code: 股票代码，如 ``"000001"``；也支持列表/元组批量查询
                （如 ``["000001", "600633"]``）。带交易所后缀的写法
                （如 ``"000001.SZ"``）会被自动归一化为 6 位裸代码。
            start: 起始日期，``"YYYYMMDD"`` 格式，含当日；分钟 K 也接受
                14 位时间戳。**只传 start 不传 end 时按单日点查询处理**。
            end: 结束日期，``"YYYYMMDD"`` 格式，含当日；``"N"`` 表示上不封顶。
            frequency: 周期。日 K ``"1d"``（默认）；分钟 K
                ``"1m"/"5m"/"15m"/"30m"/"60m"``；周 K ``"1w"``；月 K ``"1M"``
                （注意大小写：``"1M"`` 是月，``"1m"`` 是分钟）。
            fields: 需要返回的字段，逗号分隔字符串或列表，如
                ``"date,open,close"``。不传则返回全部字段的 dict 列表；
                **传入后每条记录变为按 fields 顺序取值的 list**。
            limit: 最多返回的记录条数。
            desc: 是否按时间降序返回。
            as_df: 为 ``True`` 时返回 ``pandas.DataFrame``。
            fq: 复权方式。``"qfq"`` 前复权（默认）、``"hfq"`` 后复权、
                ``None`` 不复权。

        Returns:
            单股票且无 fields: ``List[Dict]``（按时间升序）；
            单股票且有 fields: ``List[List]``（行内按 fields 顺序取值）；
            批量（code 为 list）: ``Dict[code, List[...]]``，键为归一化后的
            裸代码；``as_df=True`` 时返回对应的 ``DataFrame``（批量时首列为
            ``code``）。

        Example::

            bars = client.get_data("000001", start="20260701", end="20260824",
                                   fields="date,open,close", fq="qfq")
            df = client.get_data(["000001", "600633"], start="20260701",
                                 as_df=True)
            weekly = client.get_data("000001", frequency="1w")
        """
        codes, is_batch, table, time_query = \
            self._prepare_query(code, start, end, frequency)
        data_dict = self._fetch_sync(codes, table, time_query)
        self._finalize(data_dict, codes, frequency, fq, desc, limit, fields)
        return _wrap_result(data_dict, codes, is_batch, as_df, fields)

    # ================= 异步接口 =================

    async def get_data_async(
        self,
        code: Union[str, List[str]],
        start: Optional[str] = None,
        end: Optional[str] = None,
        frequency: str = "1d",
        fields: Optional[Union[str, List[str]]] = None,
        limit: Optional[int] = None,
        desc: bool = False,
        as_df: bool = False,
        fq: Optional[str] = "qfq",
    ) -> Union[List[Any], Dict[str, List[Any]], Any]:
        """异步获取 K 线数据（日 K、分钟 K、周 K、月 K）。

        参数与返回值同 :meth:`get_data`，但需用 ``await`` 调用。

        Example::

            bars = await client.get_data_async("000001", start="20260701")
        """
        codes, is_batch, table, time_query = \
            self._prepare_query(code, start, end, frequency)
        data_dict = await self._fetch_async(codes, table, time_query)
        self._finalize(data_dict, codes, frequency, fq, desc, limit, fields)
        return _wrap_result(data_dict, codes, is_batch, as_df, fields)
