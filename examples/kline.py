"""K 线查询：多周期、复权、批量与 DataFrame 输出。"""

import stockdb_sdk as sdk

# 近两个月日K（默认前复权、时间升序）
rows = sdk.get("600633", start="20260601", end="20260824")
print(f"日K {len(rows)} 根，最新收盘 {rows[-1]['close']}")
print("字段:", sorted(rows[-1]))

# 当日 5 分钟线（8 位日期自动展开为整个交易日），只取价格列
bars = sdk.get("600633", freq="5m", start="20260824", end="20260824",
               fields="date,close,high,low")
print(f"5 分钟线 {len(bars)} 根")

# 周线 / 月线由日 K 客户端聚合
weekly = sdk.get("600633", freq="1w", start="20260701", end="20260824")
monthly = sdk.get("600633", freq="1M", start="20260101", end="20260824")
print(f"周线 {len(weekly)} 根，月线 {len(monthly)} 根")

# 不复权 / 后复权
raw = sdk.get("600633", start="20260601", end="20260824", fq=None)
hfq = sdk.get("600633", start="20260601", end="20260824", fq="hfq")

# 批量与代码前缀，返回 {代码: 行列表}
batch = sdk.get(["600633", "000001"], start="20260801", end="20260824")
prefix = sdk.get("60063*", start="20260818", end="20260824")
print(f"批量 {sorted(batch)}，前缀命中 {len(prefix)} 只")

# DataFrame 输出（多代码合并为单个 DataFrame，行内含 code 列）
df = sdk.get("60063*", start="20260818", end="20260824", as_df=True)
print(df.head())
