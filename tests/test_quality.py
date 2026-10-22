import pytest
from rulea import PolicyError
from rulea.quality import behavioral_diff, lint, run_suite, semantic_diff, validate_context

SOURCE = 'namespace checkout\nschema:\n    age: int\nrule adult:\n    when: age >= 18\n    reason: minimum_age\n'


def test_lint_diagnostics():
    assert lint(SOURCE) == []
    assert lint(SOURCE + '\nrule adult:\n    when: True')[0].code == 'duplicate_rule'
    assert lint('rule a:\n    when: matches("missing")')[0].code == 'unknown_reference'
    assert lint(SOURCE.replace('age >= 18', 'unknown >= 18'))[0].code == 'schema_unknown_field'
    assert lint(SOURCE.replace('18', '"18"'))[0].code == 'type_mismatch'
    codes = {d.code for d in lint('rule a:\n    when: False', entrypoints=[])}
    assert {'always_false', 'missing_reason', 'unused_rule'} <= codes


def test_shadowing_analysis_is_conservative():
    source = 'rule a:\n    when: True\nrule b:\n    when: age > 18\nruleset entry:\n    rules: a,b\n    strategy: first_match\n    default: DENY'
    assert any(d.code == 'shadowed_rule' and d.rule == 'b' for d in lint(source))
    assert not any(d.code == 'shadowed_rule' for d in lint(source.replace('when: True', 'when: age > 0')))


def test_schema_is_local_only_and_checks_types():
    schema = {'type': 'object', 'properties': {'age': {'type': 'integer', 'minimum': 0}}, 'required': ['age']}
    assert validate_context(schema, {'age': 18}) == []
    assert validate_context(schema, {'age': True})
    assert validate_context(schema, {'age': -1})
    with pytest.raises(PolicyError, match='local'):
        validate_context({'$ref': 'https://example.org/schema'}, {})
    assert not validate_context({'$defs': {'n': {'type': 'integer'}}, '$ref': '#/$defs/n'}, 18)


def test_suite_assertions():
    cases = [dict(rule='checkout.adult', context={'age': 17}, expect={
        'result': 'DENY', 'reason': 'minimum_age', 'trace_contains': ['age >= 18'], 'decision_count': 1})]
    assert run_suite(SOURCE, cases)['passed'] == 1
    cases[0]['expect']['result'] = 'ALLOW'
    assert run_suite(SOURCE, cases)['passed'] == 0
    with pytest.raises(ValueError):
        run_suite(SOURCE, [dict(rule='checkout.adult', context={'age': 18}, expect={'typo': 1})])
    source = SOURCE + 'rule composed:\n    when: matches("adult")\n    reason: adult_required\n'
    assert run_suite(source, [dict(rule='checkout.composed', context={'age': 18}, expect={
        'decision_count': 2, 'children': [{'rule': 'checkout.adult', 'result': 'ALLOW'}]})])['passed'] == 1


def test_diffs_do_not_echo_context():
    candidate = SOURCE.replace('>= 18', '>= 17')
    assert semantic_diff(SOURCE, candidate)['semantic'] == [dict(kind='changed', section='rules', name='checkout.adult',
        field='when', before='age >= 18', after='age >= 17')]
    report = behavioral_diff(SOURCE, candidate, [dict(rule='checkout.adult', context={'age': age, 'private': 'secret'}) for age in [16, 17, 18]])
    assert report['evaluated'] == 3 and report['unchanged'] == 2
    assert report['transitions'] == {'DENY -> ALLOW': 1}
    assert report['changes'][0]['index'] == 1
    assert 'secret' not in str(report)
    assert behavioral_diff(SOURCE, SOURCE, [])['changed_percent'] == 0


@pytest.mark.parametrize('expect', [{'result': 'unknown'}, {'reason': 1}, {'trace_contains': 'x'},
    {'decision_count': True}, {'children': [{}]}, {'children': [{'unknown': 'value'}]}])
def test_invalid_assertions_are_rejected(expect):
    with pytest.raises(ValueError):
        run_suite(SOURCE, [dict(rule='checkout.adult', context={'age': 18}, expect=expect)])


def test_invalid_schema_is_a_policy_error():
    with pytest.raises(PolicyError, match='Invalid JSON Schema'):
        validate_context({'type': 'not-a-json-type'}, {})
