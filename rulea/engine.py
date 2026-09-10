from __future__ import annotations

from .evaluator import SafeEvaluator
from .parser import parse_rule_file


class RuleEngine:
    """Evaluate named authorization rules with fail-closed behavior."""

    def __init__(self, rule_path):
        self.rules = parse_rule_file(rule_path)

    def check(self, rule_name, context):
        """Return (allowed, reason).

        Any malformed rule, missing variable, or evaluator failure is denied.
        Internal exception details are deliberately not exposed to callers.
        """
        rule = self.rules.get(rule_name)
        if not rule:
            return False, "Rule not found"
        if not rule.get("enabled", True):
            return False, "Rule is disabled"

        expr = rule.get("when", "")
        reason = rule.get("reason") or "Permission denied"
        try:
            result = SafeEvaluator(context).eval(expr)
        except Exception:
            return False, "Policy evaluation failed"
        return (True, None) if result else (False, reason)
