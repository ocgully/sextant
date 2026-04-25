"""Malformed-text detection (§3C)."""
from __future__ import annotations

from diffsextant.ops.malformed import detect, MalformedClassifier
from diffsextant.ops.base import FileChange, OperationKind


def test_detect_merge_conflict_markers():
    src = """\
<<<<<<< HEAD
def foo(): return 1
=======
def foo(): return 2
>>>>>>> other
"""
    sig = detect(src, language="python")
    assert sig is not None
    assert "merge-conflict-markers" in sig["signals"]


def test_detect_clean_python_returns_none():
    sig = detect("def foo(): return 1\n", language="python")
    assert sig is None


def test_detect_mixed_line_endings():
    sig = detect("x = 1\r\ny = 2\n", language="python")
    assert sig is not None
    assert "mixed-line-endings" in sig["signals"]


def test_detect_binary_content():
    sig = detect("ok\x00binary-bytes", language="python")
    assert sig is not None
    assert "binary-content" in sig["signals"]


def test_classifier_emits_malformed_op():
    change = FileChange(
        path_before="broken.py", path_after="broken.py",
        body_before="",
        body_after="<<<<<<< HEAD\na\n=======\nb\n>>>>>>> other\n",
        language="python",
    )
    ops = MalformedClassifier().classify(change, None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.MALFORMED
    assert ops[0].confidence >= 0.9
