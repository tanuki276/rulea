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