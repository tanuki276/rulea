"""Restricted expression evaluator for Rulea policies.

The evaluator intentionally does *not* execute Python.  Rule expressions are
parsed as Python AST only so we can reuse familiar syntax, then interpreted by
this allow-listed evaluator.
"""

from __future__ import annotations

import ast
from typing import Any, Mapping


class RuleEvaluationError(ValueError):
    """Raised when a policy expression cannot be evaluated safely."""


class SafeEvaluator(ast.NodeVisitor):
    """Evaluate a deliberately small, side-effect-free expression language."""

    MAX_EXPRESSION_LENGTH = 4096
    MAX_AST_NODES = 256
    MAX_CONTEXT_DEPTH = 16

    ALLOWED_NODES = {
        ast.Expression,
        ast.BoolOp,
        ast.Compare,
        ast.UnaryOp,
        ast.Name,
        ast.Load,
        ast.Constant,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Eq,
        ast.NotEq,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.In,
        ast.NotIn,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.Subscript,
    }

    def __init__(self, context: Mapping[str, Any]):
        if not isinstance(context, Mapping):
            raise RuleEvaluationError("context must be a mapping")
        self.context = context
        self._node_count = 0
        self._validate_context(context, 0)

    def eval(self, expr: str) -> bool:
        if not isinstance(expr, str) or not expr.strip():
            raise RuleEvaluationError("empty rule expression")
        if len(expr) > self.MAX_EXPRESSION_LENGTH:
            raise RuleEvaluationError("rule expression is too long")

        try:
            tree = ast.parse(expr, mode="eval")
        except (SyntaxError, ValueError, TypeError) as exc:
            raise RuleEvaluationError("invalid rule expression") from exc

        result = self.visit(tree.body)
        if not isinstance(result, bool):
            raise RuleEvaluationError("rule expression must evaluate to true or false")
        return result

    def visit(self, node: ast.AST) -> Any:
        self._node_count += 1
        if self._node_count > self.MAX_AST_NODES:
            raise RuleEvaluationError("rule expression is too complex")
        if type(node) not in self.ALLOWED_NODES:
            raise RuleEvaluationError("unsupported expression construct")
        return super().visit(node)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id not in self.context:
            raise RuleEvaluationError("undefined policy variable")
        return self.context[node.id]

    def visit_Constant(self, node: ast.Constant) -> Any:
        if not isinstance(node.value, (str, int, float, bool, type(None))):
            raise RuleEvaluationError("unsupported literal")
        return node.value

    def visit_List(self, node: ast.List) -> list:
        return [self.visit(item) for item in node.elts]

    def visit_Tuple(self, node: ast.Tuple) -> tuple:
        return tuple(self.visit(item) for item in node.elts)

    def visit_Dict(self, node: ast.Dict) -> dict:
        if len(node.keys) > 64:
            raise RuleEvaluationError("literal is too large")
        result = {}
        for key, value in zip(node.keys, node.values):
            if key is None:
                raise RuleEvaluationError("dictionary unpacking is not allowed")
            result[self.visit(key)] = self.visit(value)
        return result

    def visit_BoolOp(self, node: ast.BoolOp) -> bool:
        # Preserve short-circuit semantics without ever evaluating arbitrary Python.
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not self._truth(self.visit(value)):
                    return False
            return True
        if isinstance(node.op, ast.Or):
            for value in node.values:
                if self._truth(self.visit(value)):
                    return True
            return False
        raise RuleEvaluationError("unsupported boolean operator")

    def visit_Compare(self, node: ast.Compare) -> bool:
        left = self.visit(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.visit(comparator)
            try:
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                elif isinstance(op, ast.In):
                    ok = left in right
                elif isinstance(op, ast.NotIn):
                    ok = left not in right
                else:
                    raise RuleEvaluationError("unsupported comparison operator")
            except (TypeError, KeyError, IndexError):
                raise RuleEvaluationError("incompatible values in comparison")
            if not isinstance(ok, bool) or not ok:
                return False
            left = right
        return True

    def visit_UnaryOp(self, node: ast.UnaryOp) -> bool:
        if not isinstance(node.op, ast.Not):
            raise RuleEvaluationError("only 'not' is supported")
        return not self._truth(self.visit(node.operand))

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        value = self.visit(node.value)
        # Slices and attribute access are intentionally not supported.
        if isinstance(node.slice, ast.Slice):
            raise RuleEvaluationError("slicing is not allowed")
        key = self.visit(node.slice)
        if not isinstance(value, (dict, list, tuple)):
            raise RuleEvaluationError("subscript access requires a JSON-like value")
        try:
            return value[key]
        except (KeyError, IndexError, TypeError):
            raise RuleEvaluationError("invalid subscript access")

    @staticmethod
    def _truth(value: Any) -> bool:
        if not isinstance(value, (bool, str, int, float, list, tuple, dict, type(None))):
            raise RuleEvaluationError("unsupported runtime value")
        return bool(value)

    def _validate_context(self, value: Any, depth: int) -> None:
        if depth > self.MAX_CONTEXT_DEPTH:
            raise RuleEvaluationError("context is too deeply nested")
        if isinstance(value, Mapping):
            if len(value) > 1024:
                raise RuleEvaluationError("context contains too many keys")
            for key, item in value.items():
                if not isinstance(key, str):
                    raise RuleEvaluationError("context keys must be strings")
                self._validate_context(item, depth + 1)
        elif isinstance(value, (list, tuple)):
            if len(value) > 1024:
                raise RuleEvaluationError("context contains too many items")
            for item in value:
                self._validate_context(item, depth + 1)
        elif not isinstance(value, (str, int, float, bool, type(None))):
            raise RuleEvaluationError("context must contain JSON-like values only")
