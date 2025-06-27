import argparse
from .engine import RuleEngine
import json
import sys

def main():
    parser = argparse.ArgumentParser(description="Rulea CLI - check rules.")
    parser.add_argument("rule_file", help=".rulea file path")
    parser.add_argument("rule_name", help="Rule name to check")
    parser.add_argument("--context", "-c", help="JSON string of context variables", default="{}")

    args = parser.parse_args()

    try:
        context = json.loads(args.context)
    except Exception as e:
        print(f"Invalid JSON context: {e}")
        sys.exit(1)

    engine = RuleEngine(args.rule_file)
    ok, reason = engine.check(args.rule_name, context)
    if ok:
        print("Rule passed ✅")
        sys.exit(0)
    else:
        print(f"Rule denied ❌ Reason: {reason}")
        sys.exit(1)