"""股票清单与板块：概念 / 申万行业双向检索。"""

import stockdb_sdk as sdk

codes = sdk.codes()
print(f"在市 {len(codes)} 只；退市 {len(sdk.delisted())} 只")

# 股票 -> 板块
for b in sdk.boards("600633"):
    print(f"600633 属 {b['category']}：{b['name']} ({b['code']})")

# 板块 -> 成员
print(f"AI芯片 成员 {len(sdk.members('AI芯片'))} 只")
print(f"申万一级·交通运输 成员 {len(sdk.members('交通运输', category='申万一级'))} 只")

# 名称模糊命中多个板块时需用 category 消歧
try:
    sdk.members("AI")
except ValueError as e:
    print(f"消歧提示: {e}")
