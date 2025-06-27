from rulea.engine import RuleEngine

def test_edit():
    engine = RuleEngine("examples/access.rulea")
    ok, reason = engine.check("edit", {
        "user": "alice",
        "owner": "alice",
        "status": "active"
    })
    assert ok

def test_delete_fail():
    engine = RuleEngine("examples/access.rulea")
    ok, reason = engine.check("delete", {
        "user": "bob",
        "owner": "bob",
        "status": "archived",
        "role": "user"
    })
    assert not ok
