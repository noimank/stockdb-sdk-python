"""示例：K 线查询与 DataFrame 输出。"""

import stockdb_sdk as sdk

# 1. 配置服务端（本机默认 127.0.0.1:7899，通常可省略）
sdk.init(host="127.0.0.1", port=7899)

# 2. 单只股票日 K（代码用 6 位裸代码，带后缀写法也会自动归一化）
bars = sdk.get_data(
    "000001",
    start="20260701",
    end="20260824",
    frequency="1d",
    fields="date,open,high,low,close,volume",
    fq="qfq",
)
print("日 K 前 3 条：")
for b in bars[:3]:
    print(" ", b)

# 3. 周 K
weekly = sdk.get_data("000001", frequency="1w", limit=3)
print("周 K：", weekly)

# 4. 多股票批量 -> DataFrame（pandas 为必装依赖）
df = sdk.get_data(
    ["000001", "600633"],
    start="20260701",
    as_df=True,
)
print("批量 DataFrame：")
print(df.head())
