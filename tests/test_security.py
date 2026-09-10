import pytest

from rulea.evaluator import RuleEvaluationError, SafeEvaluator


def test_allows_expected_policy_expression():
    context = {"user": {"id": "alice"}, "resource": {"owner_id": "alice"}}
    assert SafeEvaluator(context).eval('user["id"] == resource["owner_id"]') is True


@pytest.mark.parametrize(
    "expression",
    [
        '__import__("os").system("id")',
        'user.__class__',
        '[x for x in user]',
        'lambda: True',
        'open("secret")',
        'user[0:1]',
        '1 + 1',
    ],
)
def test_rejects_executable_or_unsupported_python(expression):
    with pytest.raises(RuleEvaluationError):
        SafeEvaluator({"user": {}}).eval(expression)


def test_requires_boolean_result():
    with pytest.raises(RuleEvaluationError):
        SafeEvaluator({"role": "admin"}).eval('role')


def test_missing_variable_is_denied_as_evaluation_error():
    with pytest.raises(RuleEvaluationError):
        SafeEvaluator({}).eval('role == "admin"')


def test_limits_expression_size():
    expression = "x == 1 " + "or x == 1 " * 1000
    with pytest.raises(RuleEvaluationError):
        SafeEvaluator({"x": 1}).eval(expression)
