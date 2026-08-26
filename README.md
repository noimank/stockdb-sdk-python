# StockDB Python SDK

针对 [free-stockdb](https://github.com/hello245m/free-stockdb) 项目的**第三方**只读 Python SDK，提供 K 线查询（多周期 / 复权 / 字段投影 / DataFrame）、股票清单与板块（概念 / 申万行业）双向检索，以及原生三级键只读门面。

> ⚠️ **非官方项目**：本项目由社区开发者维护，与 [free-stockdb](https://github.com/hello245m/free-stockdb) 官方无隶属关系，亦非其官方 SDK。使用前请自行评估风险，相关问题请在本仓库提交 issue，而非上游项目。

- **纯 HTTP 实现**：不依赖任何原生二进制，Windows / macOS / Linux 通用，Python 3.10+ 即装即用。
- **只读定位**：本 SDK 只做数据读取；私有数据写入与管线不在 HTTP 协议内，不提供。
- **一次依赖到位**：`httpx` + `pandas`，无可选 extras。

## 安装

```bash
pip install stockdb-sdk
```

前提：本机（或局域网内）已运行 stockdb 服务（默认 `127.0.0.1:7899`）。远程端点用 `sdk.init()` 指定。

## 快速开始

```python
import stockdb_sdk as sdk

sdk.init(host="127.0.0.1", port=7899)   # 默认端点，本机可省略

# 日 K（默认前复权、时间升序）
rows = sdk.get("600633", start="20260701", end="20260824")

# 5 分钟线 + 字段投影 + DataFrame
df = sdk.get("600633", freq="5m", start="20260824", end="20260824",
             fields="date,close,high,low", as_df=True)

# 批量 / 代码前缀（可带交易所后缀），返回 {代码: 行列表}
batch = sdk.get(["600633", "000001.SZ"], start="20260818", end="20260824")
banks = sdk.get("60003*", start="20260818", end="20260824")

# 股票清单与板块
codes = sdk.codes()                # 在市代码（升序）
boards = sdk.boards("600633")      # 该股所属板块
members = sdk.members("AI芯片")    # 板块成员代码
```

异步版本与同步完全同构（代码列表并发请求）：

```python
rows = await sdk.get_async("600633", start="20260701")
data = await sdk.get_async(["600633", "000001"], start="20260818")
```

## API

### `get(code, *, start=None, end=None, freq="1d", fq="qfq", fields=None, as_df=False)`

K 线查询，返回时间升序的行列表（dict）；`get_async` 为异步版。

| 参数 | 说明 |
|---|---|
| `code` | 单个代码（`"600633"`，可带后缀）、代码前缀（`"60063*"`、`"*"` 全市场）或代码列表 |
| `start` / `end` | 8 位日期；分钟周期也接受 14 位，传 8 位自动展开为整个交易日；均可省略 |
| `freq` | `"1d"`（默认）/ `"1m"` / `"5m"` / `"15m"` / `"30m"` / `"60m"` / `"1w"` / `"1M"`（月线） |
| `fq` | `"qfq"` 前复权（默认）/ `"hfq"` 后复权 / `None` 或 `"none"` 不复权 |
| `fields` | 字段投影：`"date,close"` 或 `["date", "close"]`；字段不存在时报错并列出可用字段 |
| `as_df` | `True` 时返回 `pandas.DataFrame`（多代码合并为单个 DataFrame） |

返回形态：单个代码 → 行列表；前缀与列表 → `{代码: 行列表}`。日 K 行约 21 个字段（`open/high/low/close/volume/amount/turnover/pct_chg/pe_ttm/pb/total_mv/...`），分钟行 8 个字段（`open/high/low/close/volume/amount`）。

周期与复权说明：

- `1d` / `1m` 为库内原生周期；`5m/15m/30m/60m` 由 1 分钟聚合、`1w/1M` 由日 K 聚合，聚合行固定输出 `date/open/high/low/close/pre_close/pct_chg/volume/amount`（+`code/name`）。
- 分钟聚合按交易时段分桶（09:30-11:30、13:00-15:00），60 分钟线为 09:30 / 10:30 / 13:00 / 14:00 四段，午休不跨桶，收盘 K 并入最后一桶。
- 复权因子按调用取用、原地折算：少于 64 只代码逐只小请求，更多则一次全量请求（约 5MB）解析后只保留当次所需，用完即弃，不设跨调用缓存；`qfq` 锚定最新、`hfq` 按累计因子放大历史。

## 内存契约（面向全市场数据管道）

本 SDK 为"查遍所有标的"的训练/回测场景设计，除板块索引外**不在调用之间保留任何行情或因子数据**；单次调用的峰值内存即该次返回的数据本身：

- 复权因子零驻留（见上）；`members()` 只做 keys 扫描 + 单板块取值，同样零驻留。
- `boards()` 反向查找必须遍历全部板块成员表，首次调用建立有界索引（约 1300 个板块，10-20MB）并保留复用；不调用即不占用。
- 窄前缀（命中 ≤ 64 只）先枚举在市+退市代码清单，再逐只精准查询——避免为 `60063*` 这类前缀拉取全市场数据；更宽的前缀走全市场单请求后客户端过滤。
- 同步多代码（≥ 4 只）自动启用最多 8 线程并发请求；异步版 `asyncio.gather` 并发，复权取数也全异步，不阻塞事件循环。

### `codes()` / `delisted()`

在市 / 已退市股票代码列表（升序）。

### `boards(code)`

一只股票所属的全部板块，返回 `[{code, name, category, source}, ...]`，`category` 为 `"概念"` / `"申万一级"` ~ `"申万三级"`。

### `members(board, category=None)`

板块成员代码列表。`board` 接受名称（`"AI芯片"`，先精确后模糊）或板块代码（`"801170.SL"`）；名称模糊命中多个板块时须用 `category` 消歧，否则报错并列出候选。

### `rd` —— 原生只读门面

直接面向 `表[:键1[:键2]]` 三级键模型，与 HTTP 协议一一对应：

```python
rd = sdk.rd
rd.get("日k:600633:20260625")            # 精确键 -> 单行 dict
rd.get("日k:600633:2026062*")            # 通配（仅最后一段）-> [[键, 值], ...]
rd.vals("日k", "600633", "2026062*")     # 只取值列
rd.keys("日k", "600633")                 # 完整键列表（仅精确键）
rd.len("日k", "600633")                  # 5421
```

内置数据表：`日k` / `分钟k`（行情）、`股票代码` / `退市`（代码表）、`复权`（除权事件与累计因子）、`板块`（概念与申万行业）。

## 行为要点（实测固化）

- 服务端区间查询返回降序，本 SDK 统一交付**时间升序**。
- 服务端不支持前缀+区间组合查询：窄前缀走枚举+逐只请求，宽前缀（`"6*"`、`"*"`）的响应体积与「市场 × 区间」成正比，大区间全市场查询请留意内存。
- 代码列表去重后逐代码请求，请求数 = 代码数；异步版并发。
- 无服务端字段投影，`fields` 在客户端完成。

## 开发

```bash
pip install -e .[dev]
pytest                # 单元测试 + 集成测试（需本地 stockdb 服务运行中）
```

版本发布：更新 `pyproject.toml` 与 `__init__.py` 双版本号 → 打 tag `vX.Y.Z` → CI 自动构建纯 Python wheel（`py3-none-any`）并发布到 PyPI。

## License

Proprietary，见 [LICENSE](LICENSE)。
