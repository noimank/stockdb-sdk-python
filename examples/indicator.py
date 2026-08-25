"""示例：技术指标计算与板块检索。"""

import stockdb_sdk as sdk

sdk.init(host="127.0.0.1", port=7899)

# 1. MACD 指标
macd = sdk.jisuan("macd", "000001.SZ", start="20260101", end="20260131")
print("MACD 前 3 条：")
for m in macd[:3]:
    print(" ", m)

# 2. 多均线 MA5 / MA10，附带金叉信号
ma = sdk.jisuan("ma", "000001.SZ", n=[5, 10], cross=True)
print("MA 交叉信号条数：", len(ma))

# 3. 板块检索
boards = sdk.bk.get("新能源")
print("新能源相关板块：", [b["name"] for b in boards])

# 4. 按成分股反查所属板块
belong = sdk.bk.get("000001.SZ")
print("000001.SZ 所属板块：", [b["name"] for b in belong])
