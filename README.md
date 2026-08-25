# StockDB Python SDK

针对 [free-stockdb](https://github.com/hello245m/free-stockdb) 项目的**第三方** Python SDK，提供 K 线查询、板块（概念 / 申万行业）检索、技术指标计算与自定义指数合成能力，核心计算由原生二进制模块加速。

> ⚠️ **非官方项目**：本项目由社区开发者维护，与 [free-stockdb](https://github.com/hello245m/free-stockdb) 官方无隶属关系，亦非其官方 SDK。使用前请自行评估风险，相关问题请在本仓库提交 issue，而非上游项目。

- **K 线查询**：日 K / 分钟 K / 周 K / 月 K，支持同步与异步、多股票批量、前/后复权、字段投影与 `pandas.DataFrame` 输出。
- **技术指标**：MACD、KDJ、RSI、BOLL 等 38 个指标，支持金叉/死叉信号。
- **指数合成**：等权 / 市值 / 成交额 / 成交量加权的自定义指数。
- **板块检索**：概念板块、申万一/二/三级行业的按代码、名称、成分股双向查询。
- **原生底层透传**：完整暴露底层 `rd` 连接的全部接口，无性能损耗。

> 兼容 Python 3.10 – 3.13（Windows x64）。原生扩展使用稳定 ABI（`cp310-abi3`）。

---

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [股票代码](#股票代码)
- [K 线查询](#k-线查询)
- [技术指标](#技术指标)
- [指数合成](#指数合成)
- [板块检索](#板块检索)
- [异步接口](#异步接口)
- [从 0.1.x 迁移](#从-01x-迁移)
- [开发与构建](#开发与构建)
- [目录结构](#目录结构)
- [许可证](#许可证)

---

## 安装

从 PyPI 安装：

```bash
pip install stockdb-sdk
```

`pandas` 为必装依赖，会随包自动安装。

---

## 快速开始

```python
import stockdb_sdk as sdk

# 1. 配置服务端（默认 127.0.0.1:7899，本机通常无需调用）
sdk.init(host="127.0.0.1", port=7899)

# 2. 查询日 K 线（默认前复权）
bars = sdk.get_data("000001", start="20260701", end="20260824")
for b in bars[:3]:
    print(b["date"], b["open"], b["close"])
```

---

## 股票代码

- 本 SDK 统一使用 **6 位裸代码**（与数据库存储一致），如 `"000001"`（平安银行）、`"600633"`（浙数文化）。
- 带交易所后缀的写法（`"000001.SZ"`、`"600633.SH"`、`"000001.XSHE"` 等）会被自动归一化为裸代码，无需手动转换。
- 批量查询返回的 dict 键、记录中的 `code` 字段均为归一化后的裸代码。

---

## K 线查询

### 单只股票

```python
# 日 K，指定字段
bars = sdk.get_data(
    "000001",
    start="20260701",
    end="20260824",
    frequency="1d",
    fields="date,open,high,low,close,volume",
    fq="qfq",           # qfq 前复权（默认） / hfq 后复权 / None 不复权
)

# 周 K、月 K（注意大小写：'1M' 是月，'1m' 是分钟）
weekly = sdk.get_data("000001", frequency="1w")
monthly = sdk.get_data("000001", frequency="1M")

# 分钟 K（1m / 5m / 15m / 30m / 60m），8 位日期自动覆盖全天
min5 = sdk.get_data("000001", start="20260824", frequency="5m")
```

### 多股票批量

```python
codes = ["000001", "600633", "300750"]

# 返回 {code: [records]}
data = sdk.get_data(codes, start="20260701", end="20260824")

# 直接返回 DataFrame（首列为 code）
df = sdk.get_data(codes, start="20260701", as_df=True)
```

### 降序 / 限额

```python
# 最近 10 根日 K，降序
recent = sdk.get_data("000001", frequency="1d", desc=True, limit=10)
```

### 返回类型一览

| 调用方式 | 返回类型 |
|---|---|
| 单股，不传 `fields` | `List[Dict]`（按时间升序） |
| 单股 + `fields` | `List[List]`（每行按 `fields` 顺序取值） |
| 批量（code 传 list） | `Dict[code, List[...]]` |
| 任意 + `as_df=True` | `DataFrame`（批量时首列为 `code`） |

> ⚠️ **注意**：传入 `fields` 后，每条记录从 `dict` 变为按 `fields` 顺序取值的 `list`，
> 即 `bars[0]["close"]` 的写法需改为 `bars[0][2]`（与底层原生接口的二维数组结构一致）。

> 只传 `start` 不传 `end` 时按**单日点查询**处理（返回 0 或 1 条记录）；需要区间请同时传
> `end`（`end="N"` 表示上不封顶）。

### 底层原生接口

`rd` 直接透传底层连接的全部能力（`get` / `vals` / `keys` / `pipe` 等，支持通配符与范围表达式）：

```python
# 点查 / 通配符 / 范围（'<' 降序、'>' 升序、'N' 上不封顶）
res = sdk.rd.vals("日k", "000001", "20260701>20260824")

# 全部标的代码：{'0': [...], '6': [...], ...}
codes = sdk.rd.get("股票代码")
```

---

## 技术指标

```python
import stockdb_sdk as sdk

# MACD（end="N" 表示取到最新）
macd = sdk.indicator("macd", "000001", start="20260701", end="N")

# 多参数均线 MA5 / MA10 / MA20
r = sdk.indicator("ma", "000001", end="N", n="5,10,20")

# 金叉信号：cross=True 只返回信号（1=金叉，-1=死叉，0=无），
# cross="with_value" 同时保留指标数值与信号
r = sdk.indicator("ma", "000001", end="N", n=[5, 10], cross=True)

# 多股票批量
kdj = sdk.indicator("kdj", ["000001", "600633"], end="N")

# 基础指标可指定输入字段（默认 close）
r = sdk.indicator("ma", "000001", end="N", fields="open", n=5)
```

- 指标不传 `end` 时只会取到默认起始日的单日数据，通常需要传 `end="N"` 或具体日期。
- 支持的指标：`macd kdj rsi wr bias boll psy cci atr bbi dmi taq ktn trix vr cr
  emv dpo brar dfma mtm mass roc expma obv mfi asi xsii`，基础指标
  `ma ema sma wma dma std sum hhv llv ref`。
- 原生函数（`MA`、`MACD`、`CROSS` 等，直接传入数值列表计算）可通过
  `sdk.zb_core` 访问。

## 指数合成

```python
# 两只成分股的等权指数（基点 1000）
idx = sdk.index(["000001", "600633"], start="20260601", end="N", method=1)

# 加权方式：1 等权（默认）/ 2 流通市值 / 3 成交额 / 4 成交量 / 5 总市值
idx = sdk.index(codes, end="N", method=3, base=1000.0)
```

分钟 K 不含市值字段，仅支持 `method=1/3/4`。返回 `List[Dict]`，
每项含 `date/open/high/low/close/pct_chg/volume/amount/stock_count`。

---

## 板块检索

```python
import stockdb_sdk as sdk

# 获取全部板块
boards = sdk.bk.get()

# 按名称模糊检索
matched = sdk.bk.get("新能源")

# 按成分股反查所属板块（0 概念 / 1 申万一级 / 2 申万二级 / 3 申万三级）
names = sdk.bk.get("000001", 0, "name")

# 按板块代码精确命中
board = sdk.bk.get("801780.SL")

# 指定分类与字段
sw = sdk.bk.get(category=1, fields="name,code")
```

---

## 异步接口

```python
import asyncio
import stockdb_sdk as sdk

async def main():
    bars = await sdk.get_data_async("000001", start="20260801", end="N")
    print(bars[:3])

asyncio.run(main())
```

也可通过客户端实例使用：

```python
client = sdk.StockDBClient(host="127.0.0.1", port=7899)
bars = await client.get_data_async("000001", start="20260801", end="N")
```

底层 `rd` 的方法同样原生支持同步与异步（`await rd.vals(...)`）。

---

## 从 0.1.x 迁移

| 0.1.x | 0.2.0 |
|---|---|
| `sdk.get_data(...)` / `sdk.get_data_async(...)` | 不变 |
| `sdk.jisuan("macd", ...)` | `sdk.indicator("macd", ...)` |
| `sdk.jisuan("zhishu", codes, method=..., base=...)` | `sdk.index(codes, method=..., base=...)` |
| `sdk.zb.get(...)`、`sdk.zb.MACD(...)` | `sdk.indicator(...)`、`sdk.zb_core.MACD(...)` |
| `sdk.gp.get_data(...)`、`sdk.rd.get_data(...)` | `sdk.get_data(...)` |
| `sdk.get_default_client()` | `sdk.StockDBClient()` |
| 代码 `"000001.SZ"` | 仍可用（自动归一化为 `"000001"`） |

---

## 开发与构建

```bash
# 安装构建工具
pip install build

# 构建 wheel（产物在 dist/ 下，标签 cp310-abi3-win_amd64）
python -m build --wheel

# 运行测试（单元测试离线；集成测试需本地启动 stockdb 服务）
pip install pytest
pytest
```

构建产物为稳定 ABI wheel，可在 Python 3.10 及以上版本安装。

---

## 目录结构

```
stockdb-sdk-python/
├── src/stockdb_sdk/          # 包源码
│   ├── __init__.py           # 公共 API 与 get_data 转发
│   ├── _connection.py        # 默认端点状态与原生连接构建
│   ├── _client.py            # K 线高层客户端（查询/聚合/复权）
│   ├── _board.py             # 板块索引（bk）
│   ├── _indicator.py         # 指标计算与指数合成
│   ├── _default.py           # init 配置、默认单例与 rd 代理
│   ├── stockdb.pyd           # 原生核心（稳定 ABI）
│   └── zb_core.pyd           # 原生指标引擎（稳定 ABI）
├── binaries/
│   └── freethreaded-3.14/    # Python 3.14 自由线程版二进制
├── examples/                 # 示例脚本
├── tests/                    # 单元测试 + 集成测试
├── .github/workflows/        # GitHub Actions 流水线
├── pyproject.toml            # 打包配置
├── setup.py                  # 自定义 wheel 命令（abi3 标签）
└── README.md
```

---

## 发布到 PyPI

流水线会在推送 tag（`v*`）后自动构建 wheel 并发布到 PyPI。手动发布：

```bash
python -m build --wheel
pip install twine
twine upload dist/*
```

---

## 许可证

专有软件，保留所有权利。作者：noimank <noimank@163.com>。
