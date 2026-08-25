"""示例：技术指标、指数合成与板块检索。"""

import stockdb_sdk as sdk

sdk.init(host="127.0.0.1", port=7899)

# 1. MACD 指标
macd = sdk.indicator("macd", "000001", start="20260701", end="20260824")
print("MACD 前 3 条：")
for m in macd[:3]:
    print(" ", m)

# 2. 多均线 MA5 / MA10，附带金叉信号
ma = sdk.indicator("ma", "000001", end="N", n=[5, 10], cross=True)
print("MA 交叉信号条数：", len(ma))

# 3. 自定义指数合成（两只成分股，等权，基点 1000）
idx = sdk.index(["000001", "600633"], start="20260701", end="N", method=1)
print("合成指数最近 3 条：", idx[-3:])

# 4. 板块检索
boards = sdk.bk.get("新能源")
print("新能源相关板块：", [b["name"] for b in boards][:5])

# 5. 按成分股反查所属板块（申万一级）
belong = sdk.bk.get("000001", 1, "name")
print("000001 申万一级行业：", belong)
