# StockDB Python SDK

针对 [free-stockdb](https://github.com/hello245m/free-stockdb) 项目的**第三方** Python SDK，提供 K 线查询、板块（概念 / 申万行业）检索与技术指标计算能力，核心计算由原生二进制模块加速。

> ⚠️ **非官方项目**：本项目由社区开发者维护，与 [free-stockdb](https://github.com/hello245m/free-stockdb) 官方无隶属关系，亦非其官方 SDK。使用前请自行评估风险，相关问题请在本仓库提交 issue，而非上游项目。

- **K 线查询**：日 K / 分钟 K / 周 K / 月 K，支持同步与异步、多股票批量、前/后复权、字段投影与 `pandas.DataFrame` 输出。
- **板块检索**：概念板块、申万一/二/三级行业的按代码、名称、成分股查询。
- **技术指标**：MACD、KDJ、RSI、BOLL 等 30+ 指标，支持金叉/死叉信号与指数合成。
- **原生底层透传**：完整暴露底层 `rd` 连接的全部接口，无性能损耗。

> 兼容 Python 3.10 – 3.13（Windows x64）。原生扩展使用稳定 ABI（`cp310-abi3`）。

---

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [K 线查询](#k-线查询)
- [技术指标](#技术指标)
- [板块检索](#板块检索)
- [异步接口](#异步接口)
- [DataFrame 输出](#dataframe-输出)
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

# 2. 查询日 K 线（前复权）
bars = sdk.get_data("000001.SZ", start="20260101", end="20260131")
for b in bars[:3]:
    print(b["date"], b["open"], b["close"])
```

---

## K 线查询

### 单只股票

```python
# 日 K，指定字段
bars = sdk.get_data(
    "000001.SZ",
    start="20260101",
    end="20260131",
    frequency="1d",
    fields="date,open,high,low,close,volume",
    fq="qfq",           # qfq 前复权 / hfq 后复权 / None 不复权
)

# 周 K、月 K
weekly = sdk.get_data("000001.SZ", frequency="1w")
monthly = sdk.get_data("000001.SZ", frequency="1M")

# 分钟 K（1m / 5m / 15m / 30m / 60m）
min5 = sdk.get_data("000001.SZ", start="20260129", frequency="5m")
```

### 多股票批量

```python
codes = ["000001.SZ", "600000.SH", "300750.SZ"]

# 返回 {code: [records]}
data = sdk.get_data(codes, start="20260101", end="20260131")

# 直接返回 DataFrame（含 code 列）
df = sdk.get_data(codes, start="20260101", as_df=True)
```

### 降序 / 限额

```python
# 最近 10 根日 K，降序
recent = sdk.get_data("000001.SZ", frequency="1d", desc=True, limit=10)
```

### 底层原生接口

`rd` 直接透传底层连接的全部能力：

```python
# 底层表查询（原生接口，性能与原生一致）
res = sdk.rd.vals("日k", "000001.SZ", "20260101>20260131")
```

---

## 技术指标

```python
import stockdb_sdk as sdk

# MACD
macd = sdk.jisuan("macd", "000001.SZ", start="20260101", end="20260131")

# 多指标 / 多周期参数
r = sdk.jisuan("ma", "000001.SZ", n=[5, 10, 20])

# 金叉信号：cross=True 输出 1/-1，cross="with_value" 同时保留数值与信号
r = sdk.jisuan("macd", "000001.SZ", cross="with_value")

# 多股票批量
kdj = sdk.jisuan("kdj", ["000001.SZ", "600000.SH"], start="20260101")
```

支持的指标：`macd kdj rsi wr bias boll psy cci atr bbi dmi taq ktn trix vr cr
emv dpo brar dfma mtm mass roc expma obv mfi asi xsii`，基础指标 `ma ema sma
wma dma std sum hhv llv ref`，以及指数合成 `zhishu`。

对象式调用同样可用：

```python
r = sdk.zb.get("macd", "000001.SZ", start="20260101")
```

---

## 板块检索

```python
import stockdb_sdk as sdk

# 获取全部板块
boards = sdk.bk.get()

# 按名称检索
matched = sdk.bk.get("新能源")

# 按成分股反查（返回该股票所属板块）
boards = sdk.bk.get("000001.SZ")

# 指定分类（0 概念 / 1 申万一级 / 2 申万二级 / 3 申万三级）
sw = sdk.bk.get(category=1)

# 指定返回字段
names = sdk.bk.get(category=0, fields="code,name")
```

---

## 异步接口

```python
import asyncio
import stockdb_sdk as sdk

async def main():
    bars = await sdk.get_data_async("000001.SZ", start="20260101")
    print(bars[:3])

asyncio.run(main())
```

也可通过客户端实例使用：

```python
client = sdk.StockDBClient(host="127.0.0.1", port=7899)
bars = await client.get_data_async("000001.SZ", start="20260101")
```

---

## DataFrame 输出

```python
# 单只股票 -> DataFrame
df = sdk.get_data("000001.SZ", start="20260101", as_df=True)

# 批量 -> 带 code 列的合并 DataFrame
df = sdk.get_data(["000001.SZ", "600000.SH"], start="20260101", as_df=True)
```

---

## 开发与构建

```bash
# 安装构建工具
pip install build

# 构建 wheel（产物在 dist/ 下，标签 cp310-abi3-win_amd64）
python -m build --wheel
```

构建产物为稳定 ABI wheel，可在 Python 3.10 及以上版本安装。

---

## 目录结构

```
stockdb-sdk-python/
├── src/stockdb_sdk/          # 包源码
│   ├── __init__.py           # 公共 API
│   ├── _sdk.py               # K 线高层客户端（get_data 等）
│   ├── _zhibiao.py           # 板块 + 指标接口
│   ├── stockdb.pyd           # 原生核心（稳定 ABI）
│   └── zb_core.pyd           # 原生指标引擎（稳定 ABI）
├── binaries/
│   └── freethreaded-3.14/    # Python 3.14 自由线程版二进制
├── examples/                 # 示例脚本
├── tests/                    # 测试
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
