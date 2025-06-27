from .evaluator import SafeEvaluator
from .parser import parse_rule_file

class RuleEngine:
    def __init__(self, rule_path):
        self.rules = parse_rule_file(rule_path)

    def check(self, rule_name, context):
        rule = self.rules.get(rule_name)
        if not rule:
            return False, "No such rule"

        expr = rule.get("when")
        reason = rule.get("reason", "Permission denied")

        try:
            evaluator = SafeEvaluator(context)
            result = evaluator.eval(expr)
            return result, None if result else reason
        except Exception as e:
            return False, f"Rule error: {e}"