"""Deterministic, database-free policy quality tools.

Analysis is deliberately conservative: unknown conditions are never reported as
unreachable, and entry points must be explicit before reporting unused rules.
"""
import ast
import difflib
from collections import Counter
from dataclasses import asdict, dataclass

from .engine import RuleEngine
from .model import PolicyError
from .parser import parse_policy


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: str
    message: str
    rule: str | None = None

    def to_dict(self):
        return asdict(self)


def lint(source, *, modules=None, entrypoints=None):
    diagnostics = []
    try:
        policy = parse_policy(source)
        engine = RuleEngine.from_string(source, modules=modules)
    except (PolicyError, RecursionError) as exc:
        message = str(exc)
        codes = {
            'Duplicate': 'duplicate_rule', 'Unknown rule reference': 'unknown_reference',
            'Unknown schema field': 'schema_unknown_field',
            'Incompatible comparison types': 'type_mismatch',
        }
        code = next((code for marker, code in codes.items() if marker in message), 'invalid_policy')
        return [Diagnostic(code, 'ERROR', message)]
    for name, rule in engine._rules.items():
        # Engine supplies a default reason; inspect the source declaration instead.
        local = name.removeprefix(policy['namespace'] + '.') if policy['namespace'] else name
        if local in policy['rules'] and 'reason' not in policy['rules'][local]:
            if not any(d.rule == name and d.code == 'missing_reason' for d in diagnostics):
                diagnostics.append(Diagnostic('missing_reason', 'WARNING', 'Specify an explicit reason', name))
        tree = rule['tree']
        if isinstance(tree, ast.Constant) and type(tree.value) is bool:
            diagnostics.append(Diagnostic('always_true' if tree.value else 'always_false',
                                          'WARNING', 'Condition is a boolean constant', name))
        if not rule['enabled']:
            diagnostics.append(Diagnostic('unreachable_condition', 'INFO', 'Rule is disabled', name))
    for name, group in engine._sets.items():
        if group['strategy'] not in ('first_match', 'priority'):
            continue
        members = group['members']
        if group['strategy'] == 'priority':
            members = sorted(members, key=lambda n: -engine._rules[n]['priority'])
        shadowed = False
        for member in members:
            rule = engine._rules[member]
            if shadowed:
                diagnostics.append(Diagnostic('shadowed_rule', 'WARNING', 'Always shadowed in ' + name, member))
            tree = rule['tree']
            if rule['enabled'] and isinstance(tree, ast.Constant) and tree.value is True:
                shadowed = True
    if entrypoints is not None:
        used = set()
        pending = list(entrypoints)
        while pending:
            name = pending.pop()
            if name in used:
                continue
            used.add(name)
            if name in engine._sets:
                pending.extend(engine._sets[name]['members'])
            elif name in engine._rules:
                pending.extend(engine._rules[name]['refs'].values())
            else:
                diagnostics.append(Diagnostic('unknown_reference', 'ERROR', 'Unknown entrypoint: ' + name))
        diagnostics.extend(Diagnostic('unused_rule', 'INFO', 'Not reachable from declared entrypoints', n)
                           for n in engine._rules if n not in used)
    return diagnostics


def validate_context(schema, context):
    """JSON Schema 2020-12 without remote reference resolution or I/O."""
    from jsonschema import Draft202012Validator
    def check(value):
        if isinstance(value, dict):
            if '$ref' in value and not value['$ref'].startswith('#'):
                raise PolicyError('Only local JSON Schema references are allowed')
            if '$dynamicRef' in value and not value['$dynamicRef'].startswith('#'):
                raise PolicyError('Only local JSON Schema references are allowed')
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)
    check(schema)
    Draft202012Validator.check_schema(schema)
    return [dict(path=list(e.absolute_path), message=e.message)
            for e in sorted(Draft202012Validator(schema).iter_errors(context), key=lambda e: str(e.absolute_path))]


def _flatten(decision):
    yield decision
    for child in decision['decisions']:
        yield from _flatten(child)


def run_suite(source, cases, *, modules=None, schema=None):
    engine = RuleEngine.from_string(source, modules=modules)
    if not isinstance(cases, list) or not cases:
        raise ValueError('Cases must be a nonempty array')
    results = []
    for index, case in enumerate(cases):
        expected = case.get('expect', {'result': case.get('result')})
        if not expected or set(expected) - {'result', 'reason', 'trace_contains', 'decision_count', 'children'}:
            raise ValueError('Unknown or empty assertion')
        errors = []
        if schema is not None:
            errors.extend(e['message'] for e in validate_context(schema, case['context']))
        actual = engine.decide(case['rule'], case['context']).to_dict()
        nodes = list(_flatten(actual))
        for field in ('result', 'reason'):
            if field in expected and expected[field] != actual[field]:
                errors.append(field + ' did not match')
        for expression in expected.get('trace_contains', []):
            if not any(expression in t['expression'] for n in nodes for t in n['trace']):
                errors.append('Missing trace: ' + expression)
        if 'decision_count' in expected and len(nodes) != expected['decision_count']:
            errors.append('decision_count did not match (includes root)')
        for child in expected.get('children', []):
            if not any(all(n.get(k) == v for k, v in child.items()) for n in nodes[1:]):
                errors.append('Child decision did not match')
        results.append(dict(name=case.get('name', str(index + 1)), passed=not errors,
                            errors=errors, decision=actual))
    return dict(total=len(results), passed=sum(r['passed'] for r in results), cases=results)


def semantic_diff(before, after):
    """Declaration and field changes; no speculative interpretation of expressions."""
    old, new = parse_policy(before), parse_policy(after)
    changes = []
    for section in ('rules', 'rulesets', 'schema'):
        left, right = old[section], new[section]
        for name in sorted(left.keys() | right.keys()):
            qualified = lambda p: p['namespace'] + '.' + name if p['namespace'] else name
            if name not in left or name not in right:
                changes.append(dict(kind='added' if name not in left else 'removed', section=section,
                                    name=qualified(new if name not in left else old)))
            elif left[name] != right[name]:
                if isinstance(left[name], dict):
                    for field in sorted(left[name].keys() | right[name].keys()):
                        if left[name].get(field) != right[name].get(field):
                            changes.append(dict(kind='changed', section=section, name=qualified(new),
                                                field=field, before=left[name].get(field), after=right[name].get(field)))
                else:
                    changes.append(dict(kind='changed', section=section, name=name,
                                        before=left[name], after=right[name]))
    for field in ('namespace', 'imports'):
        if old[field] != new[field]:
            changes.append(dict(kind='changed', section='policy', name=field, before=old[field], after=new[field]))
    return dict(source=''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                                  fromfile='before', tofile='after')), semantic=changes)


def behavioral_diff(before, after, cases):
    left, right = RuleEngine.from_string(before), RuleEngine.from_string(after)
    transitions, changed = Counter(), []
    total = 0
    for index, case in enumerate(cases):
        total += 1
        old = left.decide(case['rule'], case['context']).to_dict()
        new = right.decide(case['rule'], case['context']).to_dict()
        # Behavioral equality includes reason and children, excludes version/hash metadata.
        def behavior(d):
            return (d['result'], d['reason'], tuple(behavior(c) for c in d['decisions']))
        if behavior(old) != behavior(new):
            transitions[old['result'] + ' -> ' + new['result']] += 1
            changed.append(dict(index=index, before=old, after=new))
    return dict(evaluated=total, unchanged=total-len(changed), changed=len(changed),
                changed_percent=100 * len(changed) / total if total else 0,
                transitions=dict(transitions), changes=changed)
