"""Per-operation classifier unit tests.

Fixtures are inlined here (before/after strings) rather than shipped as
separate files — each test is self-contained and reads better next to
its assertion.
"""
from __future__ import annotations

import pytest

from sextant.ops.base import FileChange, OperationKind
from sextant.ops.rename import RenameSymbolClassifier
from sextant.ops.extract import ExtractFunctionClassifier
from sextant.ops.move import MoveFileClassifier
from sextant.ops.reformat import ReformatClassifier, LintFixClassifier
from sextant.ops.comment_only import CommentOnlyClassifier, DocstringOnlyClassifier
from sextant.ops.reorder import ReorderStatementsClassifier
from sextant.ops.invert_condition import InvertConditionClassifier
from sextant.ops.imports import (
    AddImportClassifier, RemoveImportClassifier, ReorderImportsClassifier,
)
from sextant.ops.change_signature import ChangeSignatureClassifier
from sextant.ops.tests import AddTestClassifier, RemoveTestClassifier
from sextant.parse import ts_available


TS_REQUIRED = pytest.mark.skipif(not ts_available(), reason="tree-sitter not installed")


def _change(before, after, path="lib.py"):
    from sextant.parse import detect_language
    return FileChange(
        path_before=path, path_after=path,
        body_before=before, body_after=after,
        language=detect_language(path),
    )


# --- rename-symbol ---


@TS_REQUIRED
def test_rename_symbol_python_function():
    before = "def get_user_id(conn):\n    return conn.execute('SELECT user_id')\n"
    after = "def get_account_id(conn):\n    return conn.execute('SELECT user_id')\n"
    ops = RenameSymbolClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.RENAME_SYMBOL
    assert ops[0].evidence["old_name"] == "get_user_id"
    assert ops[0].evidence["new_name"] == "get_account_id"


@TS_REQUIRED
def test_rename_symbol_identical_returns_nothing():
    src = "def foo(x): return x\n"
    ops = RenameSymbolClassifier().classify(_change(src, src), None)
    assert ops == []


def test_rename_symbol_text_fallback_when_no_language():
    before = "user_id = 1\nfoo(user_id)\nreturn user_id\n"
    after = "account_id = 1\nfoo(account_id)\nreturn account_id\n"
    change = FileChange(path_before="x.xyz", path_after="x.xyz",
                        body_before=before, body_after=after, language=None)
    ops = RenameSymbolClassifier().classify(change, None)
    assert len(ops) == 1
    assert ops[0].evidence["old_name"] == "user_id"


# --- extract-function ---


@TS_REQUIRED
def test_extract_function_python():
    before = """\
def submit_order(order):
    if order.total <= 0:
        raise ValueError('bad total')
    if not order.items:
        raise ValueError('empty')
    return save(order)
"""
    after = """\
def validate_order(order):
    if order.total <= 0:
        raise ValueError('bad total')
    if not order.items:
        raise ValueError('empty')

def submit_order(order):
    validate_order(order)
    return save(order)
"""
    ops = ExtractFunctionClassifier().classify(_change(before, after), None)
    kinds = [op.kind for op in ops]
    assert OperationKind.EXTRACT_FUNCTION in kinds


# --- move-file ---


def test_move_file_identical_body():
    change = FileChange(
        path_before="old/path.py",
        path_after="new/path.py",
        body_before="def foo(): return 1\n",
        body_after="def foo(): return 1\n",
        language="python",
    )
    ops = MoveFileClassifier().classify(change, None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.MOVE_FILE
    assert ops[0].confidence > 0.9


def test_move_file_too_divergent_rejects():
    change = FileChange(
        path_before="old/path.py",
        path_after="new/path.py",
        body_before="def foo(): return 1\n" * 3,
        body_after="totally different content with no overlap\n" * 10,
        language="python",
    )
    ops = MoveFileClassifier().classify(change, None)
    assert ops == []


# --- reformat / lint-fix ---


def test_reformat_python():
    before = "x = 1\n\n\ndef foo( x , y ):\n  return x+y\n"
    after = "x = 1\n\ndef foo(x, y):\n    return x + y\n"
    ops = ReformatClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.REFORMAT


def test_reformat_rejects_token_change():
    before = "def foo(x): return x"
    after = "def foo(x): return y"
    ops = ReformatClassifier().classify(_change(before, after), None)
    assert ops == []


# --- comment-only / docstring-only ---


def test_comment_only_python():
    before = "def foo(x):\n    # old comment\n    return x + 1\n"
    after = "def foo(x):\n    # new comment describing the behavior\n    return x + 1\n"
    ops = CommentOnlyClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.COMMENT_ONLY


def test_docstring_only_python():
    before = 'def foo(x):\n    """old"""\n    return x\n'
    after = 'def foo(x):\n    """new docstring"""\n    return x\n'
    ops = DocstringOnlyClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.DOCSTRING_ONLY


# --- reorder-statements ---


def test_reorder_statements_python():
    before = "def a():\n    return 1\n\ndef b():\n    return 2\n\ndef c():\n    return 3\n"
    after = "def c():\n    return 3\n\ndef a():\n    return 1\n\ndef b():\n    return 2\n"
    ops = ReorderStatementsClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.REORDER_STATEMENTS


# --- invert-condition ---


def test_invert_condition_python():
    before = "def foo(x):\n    if x == 0:\n        return 'a'\n    return 'b'\n"
    after = "def foo(x):\n    if x != 0:\n        return 'a'\n    return 'b'\n"
    ops = InvertConditionClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.INVERT_CONDITION


# --- imports ---


def test_add_import_python():
    before = "def foo(): pass\n"
    after = "import logging\n\ndef foo(): pass\n"
    ops = AddImportClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.ADD_IMPORT
    assert "import logging" in ops[0].evidence["added"][0]


def test_remove_import_python():
    before = "import os\nimport sys\n\ndef foo(): pass\n"
    after = "import os\n\ndef foo(): pass\n"
    ops = RemoveImportClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.REMOVE_IMPORT


def test_reorder_imports_python():
    before = "import sys\nimport os\nimport json\n"
    after = "import json\nimport os\nimport sys\n"
    ops = ReorderImportsClassifier().classify(_change(before, after), None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.REORDER_IMPORTS


# --- change-signature ---


@TS_REQUIRED
def test_change_signature_python():
    before = "def foo(x): return x\n"
    after = "def foo(x, y=1): return x + y\n"
    ops = ChangeSignatureClassifier().classify(_change(before, after), None)
    kinds = [op.kind for op in ops]
    assert OperationKind.CHANGE_SIGNATURE in kinds


# --- tests ops ---


def test_add_test():
    change = FileChange(
        path_before="tests/test_lib.py", path_after="tests/test_lib.py",
        body_before="def test_a():\n    pass\n",
        body_after="def test_a():\n    pass\n\ndef test_b():\n    pass\n",
        language="python",
    )
    ops = AddTestClassifier().classify(change, None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.ADD_TEST
    assert "test_b" in ops[0].evidence["added"]


def test_remove_test():
    change = FileChange(
        path_before="tests/test_lib.py", path_after="tests/test_lib.py",
        body_before="def test_a():\n    pass\n\ndef test_b():\n    pass\n",
        body_after="def test_a():\n    pass\n",
        language="python",
    )
    ops = RemoveTestClassifier().classify(change, None)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.REMOVE_TEST


# --- lint-fix requires commit msg ---


class FakeCtx:
    def __init__(self, msg):
        self.commit_messages = [{"sha": "x", "subject": msg, "body": msg}]
        self.bias_flags = {}
    def prior_for(self, kind):
        return 0.0
    def prior_description(self, kind):
        return ""


def test_lint_fix_fires_with_commit_msg_signature():
    before = "x = 1\ndef foo( x , y ): return x+y\n"
    after = "x = 1\n\n\ndef foo(x, y):\n    return x + y\n"
    ctx = FakeCtx("style: apply black")
    ops = LintFixClassifier().classify(_change(before, after), ctx)
    assert len(ops) == 1
    assert ops[0].kind == OperationKind.LINT_FIX


def test_lint_fix_no_fire_without_signature():
    before = "x = 1\ndef foo( x , y ): return x+y\n"
    after = "x = 1\n\ndef foo(x, y):\n    return x + y\n"
    ctx = FakeCtx("refactor: cleanup")
    ops = LintFixClassifier().classify(_change(before, after), ctx)
    assert ops == []
