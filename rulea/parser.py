# parser.py
def parse_rule_file(path: str):
    rules = {}
    current_rule = None
    current_block = None
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("rule "):
                rule_name = line.split()[1].rstrip(":")
                current_rule = {
                    "when": "",
                    "reason": "",
                    "imports": [],
                    "description": "",
                    "tags": [],
                    "priority": 100,
                    "action": "",
                    "extends": None,
                    "enabled": True
                }
                rules[rule_name] = current_rule

            elif current_rule is None:
                continue  # ファイル先頭にルール外の行があった場合スキップ

            elif line.startswith("when:"):
                current_block = "when"
                current_rule["when"] = line[len("when:"):].strip()

            elif line.startswith("reason:"):
                current_block = "reason"
                current_rule["reason"] = line[len("reason:"):].strip()

            elif line.startswith("description:"):
                current_rule["description"] = line[len("description:"):].strip()

            elif line.startswith("tags:"):
                current_rule["tags"] = [tag.strip() for tag in line[len("tags:"):].split(",")]

            elif line.startswith("priority:"):
                current_rule["priority"] = int(line[len("priority:"):].strip())

            elif line.startswith("action:"):
                current_block = "action"
                current_rule["action"] = line[len("action:"):].strip()

            elif line.startswith("import:"):
                current_rule["imports"] = [x.strip() for x in line[len("import:"):].split(",")]

            elif line.startswith("extends:"):
                current_rule["extends"] = line[len("extends:"):].strip()

            elif line.startswith("enabled:"):
                val = line[len("enabled:"):].strip().lower()
                current_rule["enabled"] = val in ("true", "yes", "1")

            else:
                if current_block:
                    current_rule[current_block] += "\n" + line
    return rules


# evaluator.py
import ast

class SafeEvaluator(ast.NodeVisitor):
    ALLOWED = {
        ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp,
        ast.Compare, ast.Name, ast.Load, ast.Constant,
        ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq, ast.Gt, ast.Lt,
        ast.GtE, ast.LtE
    }

    def __init__(self, context):
        self.context = context

    def eval(self, expr):
        tree = ast.parse(expr, mode='eval')
        return self.visit(tree.body)

    def visit(self, node):
        if type(node) not in self.ALLOWED:
            raise ValueError(f"Unsupported node: {type(node).__name__}")
        return super().visit(node)

    def visit_Name(self, node):
        if node.id not in self.context:
            raise ValueError(f"Undefined variable: {node.id}")
        return self.context[node.id]

    def visit_Constant(self, node):
        return node.value

    def visit_BoolOp(self, node):
        vals = [self.visit(v) for v in node.values]
        if isinstance(node.op, ast.And):
            return all(vals)
        elif isinstance(node.op, ast.Or):
            return any(vals)
        else:
            raise ValueError("Unsupported BoolOp")

    def visit_Compare(self, node):
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            if isinstance(op, ast.Eq) and not left == right:
                return False
            elif isinstance(op, ast.NotEq) and not left != right:
                return False
            elif isinstance(op, ast.Gt) and not left > right:
                return False
            elif isinstance(op, ast.Lt) and not left < right:
                return False
            elif isinstance(op, ast.GtE) and not left >= right:
                return False
            elif isinstance(op, ast.LtE) and not left <= right:
                return False
            else:
                raise ValueError("Unsupported comparison operator")
        return True

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        else:
            raise ValueError("Unsupported unary operation")


# action_registry.py
import ast

class ActionRegistry:
    def __init__(self):
        self._actions = {}

    def register(self, name, func):
        self._actions[name] = func

    def execute(self, expr: str, context: dict):
        tree = ast.parse(expr, mode='eval')
        call = tree.body

        if not isinstance(call, ast.Call):
            raise ValueError("Action は関数呼び出し形式である必要があります")

        if not isinstance(call.func, ast.Name):
            raise ValueError("関数名が不正です")

        func_name = call.func.id
        if func_name not in self._actions:
            raise ValueError(f"許可されていないアクション: {func_name}")

        args = []
        for arg in call.args:
            if isinstance(arg, ast.Name):
                if arg.id not in context:
                    raise ValueError(f"アクションの引数変数が未定義: {arg.id}")
                args.append(context[arg.id])
            elif isinstance(arg, ast.Constant):
                args.append(arg.value)
            else:
                raise ValueError("アクションの引数が不正です")

        return self._actions[func_name](*args)


# engine.py
from .evaluator import SafeEvaluator
from .parser import parse_rule_file
from .action_registry import ActionRegistry

class RuleEngine:
    def __init__(self, rule_path, action_registry=None):
        self.rules = parse_rule_file(rule_path)
        self.registry = action_registry or ActionRegistry()

    def resolve_rule(self, rule_name, visited=None):
        visited = visited or set()
        if rule_name in visited:
            raise ValueError(f"循環 extends 検出: {rule_name}")
        visited.add(rule_name)

        rule = self.rules.get(rule_name)
        if not rule:
            raise ValueError(f"ルールが見つかりません: {rule_name}")

        if rule.get("extends"):
            parent = self.resolve_rule(rule["extends"], visited)
            # 親ルールの内容をコピーしつつ、子ルールの値で上書き
            combined = dict(parent)
            combined.update(rule)
            return combined

        return rule

    def check(self, rule_name, context):
        try:
            rule = self.resolve_rule(rule_name)
        except Exception as e:
            return False, f"継承エラー: {e}"

        if not rule.get("enabled", True):
            return False, "ルールは無効化されています"

        expr = rule.get("when")
        reason = rule.get("reason", "アクセス拒否")

        try:
            evaluator = SafeEvaluator(context)
            result = evaluator.eval(expr)
            if result:
                action_expr = rule.get("action")
                if action_expr:
                    self.registry.execute(action_expr, context)
                return True, None
            else:
                return False, reason
        except Exception as e:
            return False, f"評価エラー: {e}"