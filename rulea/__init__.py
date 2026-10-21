"""Readable rules. Predictable decisions."""
from .engine import RuleEngine
from .model import Decision, Result, Trace, PolicyError, ENGINE_VERSION
from .parser import parse_rule_file

__version__ = ENGINE_VERSION
__all__ = ["RuleEngine", "Decision", "Result", "Trace", "PolicyError", "parse_rule_file"]
