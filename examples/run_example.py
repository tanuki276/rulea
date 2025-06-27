from rulea import RuleEngine

# ルールファイルのパス
engine = RuleEngine("examples/access.rulea")

# 実行時のデータ
context = {
    "user": {
        "username": "alice",
        "is_authenticated": True
    },
    "role": "user",
    "resource": {
        "owner": "alice",
        "status": "active"
    }
}

# ルールの評価
for rule_name in ["can_view", "can_edit", "can_delete"]:
    result, reason = engine.check(rule_name, context)
    if result:
        print(f"[✅ {rule_name}] → 許可")
    else:
        print(f"[❌ {rule_name}] → 拒否: {reason}")