"""示例：K 线查询与 DataFrame 输出。"""

import stockdb_sdk as sdk

# 1. 配置服务端（本机默认 127.0.0.1:7899，通常可省略）
sdk.init(host="127.0.0.1", port=7899)

# 2. 单只股票日 K
bars = sdk.get_data(
    "000001.SZ",
    start="20260101",
    end="20260131",
    frequency="1d",
    fields="date,open,high,low,close,volume",
    fq="qfq",
)
print("日 K 前 3 条：")
for b in bars[:3]:
    print(" ", b)

# 3. 周 K
weekly = sdk.get_data("000001.SZ", frequency="1w", limit=3)
print("周 K：", weekly)

# 4. 多股票批量 -> DataFrame（需 pandas）
df = sdk.get_data(
    ["000001.SZ", "600000.SH"],
    start="20260101",
    as_df=True,
)
print("批量 DataFrame：")
print(df.head())
