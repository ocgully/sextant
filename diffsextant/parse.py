"""Tree-sitter wrapper. Per-language grammar loading is lazy + cached.

Phase 1A languages: python, typescript, javascript, rust, go, markdown.
Missing grammars degrade to `language=None`; downstream classifiers then
fall through to text-level heuristics (comments, imports, reformat).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

# Tree-sitter core is a hard runtime dep; grammars are optional extras.
try:  # pragma: no cover - env-dependent
    import tree_sitter as _ts
    _TS_AVAILABLE = True
except Exception:  # pragma: no cover
    _ts = None
    _TS_AVAILABLE = False


EXT_TO_LANG = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".md": "markdown",
    ".markdown": "markdown",
}


def detect_language(path: Optional[str]) -> Optional[str]:
    """Map a file path to a tree-sitter language name, or None."""
    if not path:
        return None
    suffix = Path(path).suffix.lower()
    return EXT_TO_LANG.get(suffix)


@dataclass
class ParseResult:
    """Wrapper around a tree-sitter parse. `tree is None` when the grammar
    couldn't be loaded (missing extra), when `source` is empty, or when
    tree-sitter itself isn't installed.
    """
    language: Optional[str]
    source: bytes
    tree: Any = None
    error_count: int = 0
    error_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.tree is not None and self.error_count == 0

    @property
    def parseable(self) -> bool:
        """Parsed without catastrophic failure; may still have ERROR nodes."""
        return self.tree is not None

    @property
    def error_ratio(self) -> float:
        if not self.source:
            return 0.0
        return self.error_bytes / len(self.source)


@lru_cache(maxsize=16)
def _load_language(lang_name: str):
    """Load a tree-sitter Language object for `lang_name`. Returns None
    when the extra isn't installed (or tree-sitter core is missing).
    """
    if not _TS_AVAILABLE:
        return None
    try:
        if lang_name == "python":
            import tree_sitter_python as mod
            return _ts.Language(mod.language())
        if lang_name == "typescript":
            import tree_sitter_typescript as mod
            return _ts.Language(mod.language_typescript())
        if lang_name == "tsx":
            import tree_sitter_typescript as mod
            return _ts.Language(mod.language_tsx())
        if lang_name == "javascript":
            import tree_sitter_javascript as mod
            return _ts.Language(mod.language())
        if lang_name == "rust":
            import tree_sitter_rust as mod
            return _ts.Language(mod.language())
        if lang_name == "go":
            import tree_sitter_go as mod
            return _ts.Language(mod.language())
        if lang_name == "markdown":
            import tree_sitter_markdown as mod  # type: ignore
            # markdown grammar is a split language; block parser is the
            # primary surface we need for heading/structure matchers.
            try:
                return _ts.Language(mod.language())
            except AttributeError:
                return _ts.Language(mod.language_block())  # type: ignore
    except Exception:
        return None
    return None


def parse_source(source: bytes | str, language: Optional[str]) -> ParseResult:
    """Parse `source` in `language`. Never raises on bad input — returns
    a ParseResult with error counts populated instead. That lets the
    malformed-text detector act on parse failure without special casing.
    """
    if isinstance(source, str):
        source_bytes = source.encode("utf-8", errors="replace")
    else:
        source_bytes = source

    if not language or not _TS_AVAILABLE:
        return ParseResult(language=language, source=source_bytes, tree=None)

    lang = _load_language(language)
    if lang is None:
        return ParseResult(language=language, source=source_bytes, tree=None)

    parser = _ts.Parser(lang)
    try:
        tree = parser.parse(source_bytes)
    except Exception:
        return ParseResult(language=language, source=source_bytes, tree=None)

    err_count, err_bytes = _count_errors(tree.root_node)
    return ParseResult(
        language=language,
        source=source_bytes,
        tree=tree,
        error_count=err_count,
        error_bytes=err_bytes,
    )


def _count_errors(node) -> tuple[int, int]:
    """Count ERROR / MISSING nodes + their covered byte span."""
    stack = [node]
    n = 0
    b = 0
    while stack:
        cur = stack.pop()
        if cur.type == "ERROR" or getattr(cur, "is_missing", False):
            n += 1
            b += max(0, cur.end_byte - cur.start_byte)
            # don't descend into ERROR — error bytes shouldn't double-count
            continue
        stack.extend(cur.children)
    return n, b


def walk(node):
    """Yield every descendant of `node` (including node itself), pre-order."""
    stack = [node]
    while stack:
        cur = stack.pop()
        yield cur
        # push in reverse so left-to-right order is preserved by pop()
        for child in reversed(cur.children):
            stack.append(child)


def find_nodes(node, type_name: str):
    """All descendants with `.type == type_name`."""
    return [n for n in walk(node) if n.type == type_name]


def node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def ts_available() -> bool:
    return _TS_AVAILABLE
