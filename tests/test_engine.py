import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from rulea import RuleEngine, Result, PolicyError
from rulea.cli import main


def engine(condition, extra="", **kwargs):
    return RuleEngine.from_string("rule test:\n    when: " + condition + "\n" + extra, **kwargs)


def test_legacy_check():
    e = engine('user == owner', '    reason: "Owner only"\n')
    assert e.check('test', {'user': 'a', 'owner': 'a'}) == (True, None)
    assert e.check('test', {'user': 'a', 'owner': 'b'}) == (False, 'Owner only')
    assert e.decide('missing', {}).result is Result.NOT_APPLICABLE


@pytest.mark.parametrize('expression,expected', [
    ('a >= b', False), ('a <= b', True), ('a < b < c', True),
    ('a == b', False), ('a != b', True), ('c > b > a', True),
    ('a in [1, 2]', True), ('a not in [1, 2]', False),
    ('not (a > b)', True), ('False and missing', False), ('True or missing', True),
])
def test_operators(expression, expected):
    d = engine(expression).decide('test', {'a': 1, 'b': 2, 'c': 3})
    assert d.allowed is expected
    assert d.result is (Result.ALLOW if expected else Result.DENY)
    assert d.trace


@pytest.mark.parametrize('expression', [
    '__import__("os")', 'user.delete()', 'lambda: True', '[x for x in []]',
    '(x := True)', 'user.__class__', 'a + b', 'a ** b', 'allow(name)',
    'allow("x", bad=True)', '1', 'True or dangerous()', 'a is b',
])
def test_unsafe_rejected_at_load(expression):
    with pytest.raises(PolicyError):
        engine(expression)


def test_schema():
    src = 'schema:\n    user.role: string\nrule test:\n    when: user.role == "admin"\n'
    e = RuleEngine.from_string(src)
    assert e.decide('test', {'user': {'role': 'admin'}}).allowed
    assert e.decide('test', {'user': {'role': 1}}).result is Result.ERROR
    assert e.decide('test', {}).result is Result.ERROR
    with pytest.raises(PolicyError):
        RuleEngine.from_string(src.replace('when: user.role', 'when: user.roll'))
    with pytest.raises(PolicyError):
        RuleEngine.from_string(src.replace('== "admin"', '== 1'))


def test_plain_facts_only():
    class Evil:
        def __eq__(self, other):
            raise AssertionError('Must never execute')
    assert engine('a == b').decide('test', {'a': Evil(), 'b': 1}).result is Result.ERROR
    class BadDict(dict):
        def items(self):
            raise AssertionError('Must never execute')
    assert engine('True').decide('test', BadDict()).result is Result.ERROR
    assert engine('True').decide('test', {'a': float('nan')}).result is Result.ERROR


def test_composition_and_trace():
    e = RuleEngine('examples/documents.rulea')
    context = {'user': {'id': 100}, 'resource': {'owner': 100, 'locked': False, 'status': 'reviewed'}}
    d = e.decide('documents.publish', context)
    assert d.allowed and d.policy_version == '42'
    assert d.decisions[0].rule == 'documents.editable'
    assert d.decisions[0].decisions[0].rule == 'documents.owner'
    assert d.to_dict() == e.decide('documents.publish', context).to_dict()
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(x == d for x in pool.map(lambda _: e.decide('documents.publish', context), range(30)))


def test_composition_error_does_not_turn_into_allow():
    e = RuleEngine.from_string('rule a:\n    when: missing\nrule b:\n    when: not allow("a")\n')
    assert e.decide('b', {}).result is Result.ERROR


@pytest.mark.parametrize('source', [
    'rule a:\n    when: True\nrule a:\n    when: False',
    'rule a:\n    when: allow("missing")',
    'rule a:\n    when: allow("b")\nrule b:\n    when: allow("a")',
    'rule a:\n    when: True\n    action: send_email()',
    'rule a:\n    when: True\n    extends: b',
    'rule a:\n    when: True\n    enabled: yes',
    'unexpected garbage',
])
def test_invalid_policy(source):
    with pytest.raises(PolicyError):
        RuleEngine.from_string(source)


@pytest.mark.parametrize('strategy,result', [
    ('deny_overrides', Result.DENY), ('allow_overrides', Result.ALLOW),
    ('priority', Result.DENY), ('first_match', Result.ALLOW),
])
def test_strategies(strategy, result):
    src = ('rule yes:\n    when: True\nrule no:\n    when: True\n    effect: DENY\n    priority: 10\n'
           'ruleset all:\n    rules: yes, no\n    strategy: '+strategy+'\n    default: DENY\n')
    d = RuleEngine.from_string(src).decide('all', {})
    assert d.result is result
    assert strategy in d.reason


def test_default_disabled_and_error():
    src = 'rule a:\n    when: False\nruleset all:\n    rules: a\n    strategy: deny_overrides\n    default: DENY\n'
    assert RuleEngine.from_string(src).decide('all', {}).result is Result.DENY
    assert RuleEngine.from_string(src.replace('False', 'missing')).decide('all', {}).result is Result.ERROR
    assert engine('True', '    enabled: false\n').decide('test', {}).result is Result.NOT_APPLICABLE


def test_modules():
    src = 'import owners\nrule test:\n    when: allow("common.owner")\n'
    module = 'namespace common\nrule owner:\n    when: True\n'
    assert RuleEngine.from_string(src, modules={'owners': module}).decide('test', {}).allowed
    with pytest.raises(PolicyError):
        RuleEngine.from_string(src)
    with pytest.raises(PolicyError):
        RuleEngine.from_string(src, modules={'owners': 'import owners\n'})
    a = RuleEngine.from_string(src, modules={'owners': module})
    b = RuleEngine.from_string(src, modules={'owners': module.replace('True', 'False')})
    assert a.policy_hash != b.policy_hash


def test_events():
    events = []
    e = engine('missing', on_event=events.append)
    e.decide('test', {})
    assert [e['event'] for e in events] == ['policy_loaded', 'rule_evaluated', 'evaluation_failed', 'decision_produced']
    def broken(event):
        raise RuntimeError('observer failed')
    assert engine('True', on_event=broken).decide('test', {}).allowed


def test_cli(tmp_path, capsys):
    assert main(['check', 'examples/documents.rulea']) == 0
    assert main(['lint', 'examples/documents.rulea']) == 0
    assert main(['test', 'examples/documents.rulea', 'examples/documents.cases.json']) == 0
    assert main(['explain', 'examples/documents.rulea', 'documents.edit']) == 2
    assert main(['benchmark', 'examples/access.rulea', 'missing', '--iterations', '2']) == 0
    assert main(['fmt', 'examples/documents.rulea']) == 0
    bad = tmp_path / 'bad.rulea'
    bad.write_text('rule a:\n    when: dangerous()\n')
    assert main(['check', str(bad)]) == 2


def test_winner_reason_retains_deny_and_error():
    src = ('rule a:\n    when: True\n    effect: DENY\n'
           'ruleset all:\n    rules: a\n    strategy: deny_overrides\n    default: ALLOW\n')
    d = RuleEngine.from_string(src).decide('all', {})
    assert d.result is Result.DENY
    assert d.reason == 'deny_overrides: a'
    d = RuleEngine.from_string(src.replace('True', 'missing')).decide('all', {})
    assert d.result is Result.ERROR
    assert d.reason == 'deny_overrides: a'


def test_policy_scales_and_rejects_cycles():
    source = '\n'.join('rule r{}:\n    when: True'.format(i) for i in range(1000))
    assert RuleEngine.from_string(source).decide('r999', {}).allowed
    with pytest.raises(PolicyError):
        engine('not ' * 100 + 'True')


def test_cli_failing_cases_and_format(tmp_path):
    path = tmp_path / 'test.rulea'
    path.write_text('rule a:\n  when: True  \n')
    assert main(['fmt', str(path), '--write']) == 0
    assert path.read_text() == 'rule a:\n    when: True\n'
    assert main(['explain', str(path), 'a']) == 0
    assert main(['explain', str(path), 'missing']) == 1
    cases = tmp_path / 'cases.json'
    cases.write_text('[{"rule":"a","context":{},"result":"DENY"}]')
    assert main(['test', str(path), str(cases)]) == 1
