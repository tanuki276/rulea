# rulea

**rulea is a small, declarative authorization policy language for Python.**

Write access rules in readable `.rulea` files and evaluate them from your application without executing policy code.

## Why rulea?

- **Readable:** policies look like ordinary boolean statements.
- **Safe by design:** rulea parses Python syntax but does **not** execute Python.
- **Fail closed:** malformed policies, missing variables, unsupported values, and evaluator failures deny access.
- **Auditable:** policy files are text, can be code-reviewed, versioned, and deployed independently of application code.
- **Deterministic:** policies have no imports, function calls, attribute access, I/O, or side effects.

> Security note: rulea is a policy evaluator, not a complete enterprise IAM product. Production deployments should still authenticate users, authorize access to the correct tenant/resource, protect policy files, and enforce change approval in CI/CD.

## Syntax

A rule contains a name, a condition, and an explanation for denial:

```text
rule edit:
    when: user["id"] == resource["owner_id"] and resource["status"] != "locked"
    reason: "Only the owner can edit an unlocked resource"
    description: "Owner-only edit policy"
    tags: edit, ownership
    priority: 10
    enabled: true
```

Supported fields:

| Field | Required | Meaning |
|---|---:|---|
| `when` | yes | Boolean expression |
| `reason` | no | Safe, human-readable denial reason |
| `description` | no | Documentation for operators |
| `tags` | no | Comma-separated policy metadata |
| `priority` | no | Integer from 0 to 1000 |
| `enabled` | no | `true` or `false` |

### Expressions

The expression language intentionally supports only:

- variables: `user`, `resource`, `role`
- JSON-like literals: strings, numbers, booleans, `null`
- dictionary/list access: `resource["owner_id"]`
- comparisons: `==`, `!=`, `>`, `>=`, `<`, `<=`, `in`, `not in`
- boolean operators: `and`, `or`, `not`
- parentheses

Python statements, `if` blocks, imports, function calls, attribute access (`user.is_admin`), comprehensions, lambdas, arithmetic, and slicing are rejected.

For complex authorization logic, prefer several named rules rather than deeply nested expressions. This keeps reviews and audits understandable.

## Python

```python
from rulea import RuleEngine

engine = RuleEngine("access.rulea")
allowed, reason = engine.check("edit", {
    "user": {"id": "alice"},
    "resource": {"owner_id": "alice", "status": "active"},
})

if allowed:
    edit_resource()
else:
    print(reason)
```

## CLI

```bash
rulea access.rulea edit \
  --context '{"user":{"id":"alice"},"resource":{"owner_id":"alice","status":"active"}}'
```

Exit status `0` means allowed; `1` means denied.

## Security model

The evaluator uses Python's `ast` module only as a parser. It walks an explicit allow-list of AST node types and interprets those nodes itself. No `eval()` or `exec()` is used.

Additional limits defend against accidental or adversarial resource exhaustion:

- expression length: 4,096 characters
- AST nodes: 256
- context nesting depth: 16
- collection size: 1,024 items
- mapping keys: 1,024 per object

Policy evaluation accepts JSON-like context values only. Evaluation errors intentionally return a generic denial rather than exposing internal exception details to an API caller.

## Enterprise deployment guidance

For larger organizations, treat policies as controlled production artifacts:

1. Store `.rulea` files in version control.
2. Require pull-request review and CODEOWNERS approval for authorization changes.
3. Validate policies in CI before deployment.
4. Pin the rulea package version and use reproducible builds.
5. Keep authentication and tenant/resource identity outside the policy engine.
6. Log policy name/version and allow/deny outcome, but do not log sensitive context by default.
7. Deploy immutable, signed/versioned policy bundles where your platform supports it.
8. Add contract tests for every security-critical policy.

rulea deliberately does not execute side effects from policy files. Application code performs the authorized operation after `check()` returns `True`.

## License

MIT
