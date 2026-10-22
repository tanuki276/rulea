"""Development tools kept outside the decision interpreter."""
import argparse
import json
import sys
import time
from pathlib import Path
from .engine import RuleEngine
from .model import PolicyError, Result


def main(argv=None):
    parser = argparse.ArgumentParser(description="rulea v2 decision tools")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "lint", "explain", "test", "benchmark", "fmt", "diff", "simulate"):
        p = sub.add_parser(command)
        p.add_argument("policy")
        if command in ("explain", "benchmark"):
            p.add_argument("rule")
            p.add_argument("--context", "-c", default="{}")
        if command in ("diff", "simulate"):
            p.add_argument("candidate")
        if command == "simulate":
            p.add_argument("cases")
        if command == "test":
            p.add_argument("cases", help="JSON array of {rule, context, result}")
        if command == "benchmark":
            p.add_argument("--iterations", type=int, default=1000)
        if command == "fmt":
            p.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in ("diff", "simulate", "lint", "test"):
            from .quality import lint, run_suite, semantic_diff, behavioral_diff
            source = Path(args.policy).read_text(encoding="utf-8")
            if args.command == "lint":
                diagnostics = lint(source)
                print(json.dumps([d.to_dict() for d in diagnostics], indent=2))
                return int(any(d.severity == "ERROR" for d in diagnostics))
            if args.command == "test":
                report = run_suite(source, json.loads(Path(args.cases).read_text(encoding="utf-8")))
                print(json.dumps(report, ensure_ascii=False, indent=2))
                return int(report["passed"] != report["total"])
            candidate = Path(args.candidate).read_text(encoding="utf-8")
            report = semantic_diff(source, candidate) if args.command == "diff" else behavioral_diff(
                source, candidate, json.loads(Path(args.cases).read_text(encoding="utf-8")))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        engine = RuleEngine(args.policy)
        if args.command in ("check", "lint"):
            print("Policy valid: " + engine.policy_hash)
            return 0
        if args.command == "fmt":
            # Conservative formatting preserves expressions, strings and declaration order.
            source = Path(args.policy).read_text(encoding="utf-8")
            formatted = "\n".join(("    " + line.strip() if line[:1].isspace() and line.strip() else line.rstrip()) for line in source.splitlines()).rstrip() + "\n"
            RuleEngine.from_string(formatted)
            if args.write:
                Path(args.policy).write_text(formatted, encoding="utf-8")
            else:
                print(formatted, end="")
            return 0
        context = json.loads(args.context)
        if args.command == "explain":
            decision = engine.decide(args.rule, context)
            print(json.dumps(decision.to_dict(), ensure_ascii=False, indent=2))
            return 0 if decision.allowed else 2 if decision.result is Result.ERROR else 1
        if not 1 <= args.iterations <= 1000000:
            raise ValueError("iterations must be between 1 and 1000000")
        start = time.perf_counter()
        for _ in range(args.iterations):
            decision = engine.decide(args.rule, context)
            if decision.result is Result.ERROR:
                raise ValueError(decision.reason)
        print(json.dumps({"iterations": args.iterations, "seconds": time.perf_counter() - start}))
        return 0
    except (PolicyError, OSError, ValueError, TypeError, KeyError) as exc:
        print("rulea: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
