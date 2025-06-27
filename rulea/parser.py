def parse_rule_file(path: str):
    rules = {}
    current_rule = None
    current_block = None
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("rule "):
                rule_name = line.split()[1].rstrip(":")
                current_rule = {"when": "", "reason": "", "imports": []}
                rules[rule_name] = current_rule
            elif line.startswith("when:"):
                current_block = "when"
                current_rule["when"] = line[len("when:"):].strip()
            elif line.startswith("reason:"):
                current_block = "reason"
                current_rule["reason"] = line[len("reason:"):].strip()
            elif line.startswith("import:"):
                current_rule["imports"] = [x.strip() for x in line[len("import:"):].split(",")]
            else:
                if current_block:
                    current_rule[current_block] += "\n" + line
    return rules