"""tree-sitter wrapper: language detection + parse error handling."""
from __future__ import annotations

import pytest

from sextant.parse import detect_language, parse_source, ts_available


def test_detect_language_common_extensions():
    assert detect_language("foo.py") == "python"
    assert detect_language("foo.ts") == "typescript"
    assert detect_language("foo.tsx") == "tsx"
    assert detect_language("foo.js") == "javascript"
    assert detect_language("foo.rs") == "rust"
    assert detect_language("foo.go") == "go"
    assert detect_language("README.md") == "markdown"
    assert detect_language("unknown.xyz") is None
    assert detect_language(None) is None


@pytest.mark.skipif(not ts_available(), reason="tree-sitter not installed")
def test_parse_python_ok():
    result = parse_source(b"def foo(x, y): return x + y", "python")
    assert result.tree is not None
    assert result.error_count == 0


@pytest.mark.skipif(not ts_available(), reason="tree-sitter not installed")
def test_parse_malformed_produces_errors():
    # Missing body after `:` is a parse error in Python
    result = parse_source(b"def foo(x,", "python")
    # tree-sitter always returns SOME tree, but error_count should be > 0
    assert result.tree is not None
    assert result.error_count > 0


def test_parse_empty_source():
    r = parse_source(b"", "python")
    assert r.error_count == 0  # nothing to err on
    # ok because no source to analyze


def test_parse_unknown_language_returns_result_with_no_tree():
    r = parse_source(b"int main() {}", None)
    assert r.tree is None
