import ast

class SafeEvaluator(ast.NodeVisitor):
    ALLOWED = {
        ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp,
        ast.Compare, ast.Name, ast.Load, ast.Constant,
        ast.And, ast.Or, ast.Not, ast.Eq, ast.NotEq, ast.Gt, ast.Lt,
        ast.GtE, ast.LtE,
        ast.Subscript,  # 添字アクセスを許可
        ast.Index,      # Python3.8以下用（slice内のindex）
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
        return self.context.get(node.id, None)

    def visit_Constant(self, node):
        return node.value

    def visit_BoolOp(self, node):
        vals = [self.visit(v) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)

    def visit_Compare(self, node):
        left = self.visit(node.left)
        for op, comp in zip(node.ops, node.comparators):
            right = self.visit(comp)
            if isinstance(op, ast.Eq) and not left == right:
                return False
            if isinstance(op, ast.NotEq) and not left != right:
                return False
            if isinstance(op, ast.Gt) and not left > right:
                return False
            if isinstance(op, ast.Lt) and not left < right:
                return False
        return True

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return not operand
        raise ValueError("Unsupported unary operation")

    def visit_Subscript(self, node):
        # 添字アクセス対応
        value = self.visit(node.value)
        # Python3.9以降は node.slice が ast.Constantかも。3.8以下はast.Index
        if isinstance(node.slice, ast.Index):  # Python3.8以下対応
            index = self.visit(node.slice.value)
        else:
            index = self.visit(node.slice)
        try:
            return value[index]
        except Exception as e:
            raise ValueError(f"Subscriptアクセスエラー: {e}")