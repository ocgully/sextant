"""Design / anti-pattern detectors."""
from __future__ import annotations

import pytest

from sextant.ops.base import FileChange, OperationKind
from sextant.patterns.strategy import StrategyPatternClassifier
from sextant.patterns.god_class import GodClassClassifier
from sextant.patterns.shotgun_surgery import detect_shotgun_surgery
from sextant.parse import ts_available


TS_REQUIRED = pytest.mark.skipif(not ts_available(), reason="tree-sitter not installed")


def _change(before, after, path="lib.py"):
    from sextant.parse import detect_language
    return FileChange(
        path_before=path, path_after=path,
        body_before=before, body_after=after,
        language=detect_language(path),
    )


def test_strategy_pattern_intro_python():
    before = """\
def handle(kind, x):
    if kind == 'a':
        return a(x)
    elif kind == 'b':
        return b(x)
    elif kind == 'c':
        return c(x)
    elif kind == 'd':
        return d(x)
    else:
        return default(x)
"""
    after = """\
HANDLERS = {'a': a, 'b': b, 'c': c, 'd': d}

def handle(kind, x):
    return HANDLERS.get(kind, default)(x)
"""
    ops = StrategyPatternClassifier().classify(_change(before, after), None)
    assert any(op.kind == OperationKind.STRATEGY_PATTERN_INTRO for op in ops)


@TS_REQUIRED
def test_god_class_forming_fires_on_large_growth():
    # build a class with ~22 methods (20+ threshold)
    methods = "\n".join(f"    def method_{i}(self): return {i}" for i in range(22))
    after = f"class BigService:\n{methods}\n"
    before = "class BigService:\n    def method_0(self): return 0\n"
    ops = GodClassClassifier().classify(_change(before, after), None)
    assert any(op.kind == OperationKind.GOD_CLASS_FORMING for op in ops)


def test_shotgun_surgery_across_many_files():
    changes = []
    for i in range(6):
        changes.append(FileChange(
            path_before=f"module{i}/thing.py",
            path_after=f"module{i}/thing.py",
            body_before=f"SHARED_IDENT = 1\nother_{i} = {i}\n",
            body_after=f"RENAMED_IDENT = 1\nother_{i} = {i}\n",
            language="python",
        ))
    ops = detect_shotgun_surgery(changes, None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.SHOTGUN_SURGERY
    assert ops[0].evidence["file_count"] == 6
