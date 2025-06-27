==============================
rulea - Syntax and Usage

Overview:

rulea is a rule-based language that clearly defines "who can do what."
With Python-like syntax, access or operation conditions are written in external .rulea files,
which can then be evaluated from within an application.

Basic Rule File Structure:

rule <rule_name>:  
    when: <condition_expression>  
    reason: "<reason if denied>"  
  
The when: section accepts both Python expressions and if statements.  
  
Multi-line conditions are supported.  
  
  
Examples:  
  
rule edit:  
    when: user == owner and status != "locked"  
    reason: "Only the owner can edit unlocked items"  
  
rule delete:  
    when:  
        if role == "admin":  
            True  
        elif user == owner:  
            status != "archived"  
        else:  
            False  
    reason: "Only admins or the owner (if not archived) can delete"  
  
Parameters are passed in externally as a context and are evaluated as variables.  
  
  
Using in Python:  
  
from rulea import RuleEngine  
  
engine = RuleEngine("access.rulea")  
ok, reason = engine.check("edit", {  
    "user": "alice",  
    "owner": "alice",  
    "status": "active"  
})  
  
if ok:  
    print("Allowed")  
else:  
    print("Denied:", reason)  
  
Using in CLI:  
  
rulea access.rulea edit \  
  --context '{"user": "alice", "owner": "bob", "status": "locked"}'  
  
Exit Codes:  
  
0 = Rule passed (allowed)  
  
1 = Rule failed (denied)  
  
  
Notes:  
  
when: supports expressions and if statements  
  
reason: is returned when the rule is denied  
  
Conditions are evaluated in a safe Python environment  
  
.rulea files must be saved in UTF-8 encoding

