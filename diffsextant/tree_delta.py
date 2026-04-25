"""Simplified Gumtree-style driver.

Full Gumtree would match AST sub-trees across before/after by hash and
distance. For phase 1A we take a lighter approach: the per-file
Classifier pipeline inspects both ASTs and emits Operations. Cross-file
classifiers run afterwards. The output is a structured DiffResult.

A later sub-phase can replace the per-classifier normalization loops
with a true Gumtree mapping to lift accuracy on close-but-not-identical
bodies (merged extracts, partial inlines).
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from diffsextant.git_context import GitContext, collect as collect_git_context
from diffsextant.ops.base import Classifier, FileChange, Operation, OperationKind
from diffsextant.parse import detect_language


# ---------------------------------------------------------------------------
# classifier registry
# ---------------------------------------------------------------------------


def _per_file_classifiers() -> List[Classifier]:
    """Ordered list: cheap/strong short-circuit first, weak last.
    Malformed ALWAYS runs first — it short-circuits the pipeline.
    """
    from diffsextant.ops.malformed import MalformedClassifier
    from diffsextant.ops.rename import RenameSymbolClassifier
    from diffsextant.ops.extract import ExtractFunctionClassifier
    from diffsextant.ops.move import MoveFileClassifier
    from diffsextant.ops.reformat import LintFixClassifier, ReformatClassifier
    from diffsextant.ops.comment_only import CommentOnlyClassifier, DocstringOnlyClassifier
    from diffsextant.ops.reorder import ReorderStatementsClassifier
    from diffsextant.ops.invert_condition import InvertConditionClassifier
    from diffsextant.ops.imports import (
        AddImportClassifier, RemoveImportClassifier, ReorderImportsClassifier,
    )
    from diffsextant.ops.change_signature import ChangeSignatureClassifier
    from diffsextant.ops.tests import AddTestClassifier, RemoveTestClassifier
    from diffsextant.patterns.strategy import StrategyPatternClassifier
    from diffsextant.patterns.god_class import GodClassClassifier

    return [
        # Must-run-first: malformed short-circuits normal classification.
        MalformedClassifier(),
        # Whole-file operations
        MoveFileClassifier(),
        # Strong, deterministic signals
        LintFixClassifier(),
        ReformatClassifier(),
        CommentOnlyClassifier(),
        DocstringOnlyClassifier(),
        ReorderImportsClassifier(),
        AddImportClassifier(),
        RemoveImportClassifier(),
        ReorderStatementsClassifier(),
        # AST-driven structural
        RenameSymbolClassifier(),
        ChangeSignatureClassifier(),
        ExtractFunctionClassifier(),
        InvertConditionClassifier(),
        # Tests
        AddTestClassifier(),
        RemoveTestClassifier(),
        # Patterns (expensive, run last)
        StrategyPatternClassifier(),
        GodClassClassifier(),
    ]


# ---------------------------------------------------------------------------
# public result type
# ---------------------------------------------------------------------------


@dataclass
class DiffResult:
    operations: List[Operation] = field(default_factory=list)
    changes: List[FileChange] = field(default_factory=list)
    git_context: Optional[GitContext] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operations": [op.to_dict() for op in self.operations],
            "files": [
                {
                    "path_before": c.path_before,
                    "path_after": c.path_after,
                    "language": c.language,
                    "is_new": c.is_new,
                    "is_deleted": c.is_deleted,
                    "is_renamed": c.is_renamed,
                }
                for c in self.changes
            ],
            "git_context": self.git_context.to_dict() if self.git_context else None,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# git diff -> list of FileChange
# ---------------------------------------------------------------------------


def _run_git(args, cwd: Path) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout


def _file_at_rev(cwd: Path, rev: str, path: str) -> str:
    out = _run_git(["show", f"{rev}:{path}"], cwd)
    return out if out is not None else ""


def collect_changes(cwd: Path, ref1: str, ref2: str,
                    files: Optional[List[str]] = None) -> List[FileChange]:
    """Enumerate files in `ref1..ref2` and load before/after bodies.
    Respects git's rename detection via `--find-renames`.
    """
    args = ["diff", "--name-status", "--find-renames", f"{ref1}", f"{ref2}"]
    if files:
        args.append("--")
        args.extend(files)
    out = _run_git(args, cwd)
    if out is None:
        return []

    changes: List[FileChange] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        status = parts[0]
        if status.startswith("R"):
            # Rxxx\t<old>\t<new>
            if len(parts) < 3:
                continue
            before_path, after_path = parts[1], parts[2]
            before_body = _file_at_rev(cwd, ref1, before_path)
            after_body = _file_at_rev(cwd, ref2, after_path)
        elif status == "A":
            if len(parts) < 2:
                continue
            before_path, after_path = None, parts[1]
            before_body = ""
            after_body = _file_at_rev(cwd, ref2, after_path)
        elif status == "D":
            if len(parts) < 2:
                continue
            before_path, after_path = parts[1], None
            before_body = _file_at_rev(cwd, ref1, before_path)
            after_body = ""
        else:
            if len(parts) < 2:
                continue
            before_path = after_path = parts[1]
            before_body = _file_at_rev(cwd, ref1, before_path)
            after_body = _file_at_rev(cwd, ref2, after_path)

        lang = detect_language(after_path or before_path)
        changes.append(FileChange(
            path_before=before_path,
            path_after=after_path,
            body_before=before_body,
            body_after=after_body,
            language=lang,
        ))
    return changes


# ---------------------------------------------------------------------------
# top-level driver
# ---------------------------------------------------------------------------


def classify_diff(ref1: str, ref2: str, cwd: Optional[Path] = None,
                  files: Optional[List[str]] = None,
                  git_ctx: Optional[GitContext] = None) -> DiffResult:
    """Entry point used by the CLI + embedders.

    Steps:
    1. Collect git-context (branch / commit msgs / pick-state).
    2. Enumerate FileChanges for the diff range.
    3. Run per-file classifiers. Malformed short-circuits the other
       classifiers on that file.
    4. Run cross-file classifiers (move-symbol, shotgun-surgery).
    5. Emit plain-edit for any file with changes that produced no ops.
    """
    cwd = cwd or Path.cwd()
    if git_ctx is None:
        git_ctx = collect_git_context(cwd, ref1=ref1, ref2=ref2)

    changes = collect_changes(cwd, ref1, ref2, files)
    classifiers = _per_file_classifiers()

    all_ops: List[Operation] = []
    warnings: List[str] = []

    for change in changes:
        if change.body_before == change.body_after and not change.is_renamed:
            continue
        file_ops: List[Operation] = []
        # Run malformed first explicitly — short-circuits everything else.
        malformed_hit = False
        for cls in classifiers:
            try:
                ops = cls.classify(change, git_ctx)
            except Exception as e:
                warnings.append(
                    f"classifier {cls.__class__.__name__} failed on "
                    f"{change.path}: {e}"
                )
                continue
            for op in ops:
                if op.confidence < cls.min_confidence:
                    continue
                file_ops.append(op)
                if op.kind == OperationKind.MALFORMED:
                    malformed_hit = True
            if malformed_hit:
                break
        if not file_ops:
            # Nothing classified — emit a plain-edit placeholder
            file_ops.append(Operation(
                kind=OperationKind.PLAIN_EDIT,
                file=change.path,
                confidence=0.50,
                summary=f"unclassified text change in `{change.path}`",
                evidence={
                    "before_bytes": len(change.body_before),
                    "after_bytes": len(change.body_after),
                },
            ))
        all_ops.extend(file_ops)

    # Cross-file classifiers
    from diffsextant.ops.move import detect_move_symbols
    from diffsextant.patterns.shotgun_surgery import detect_shotgun_surgery
    try:
        all_ops.extend(detect_move_symbols(changes, git_ctx))
    except Exception as e:
        warnings.append(f"move-symbol cross-file detector failed: {e}")
    try:
        all_ops.extend(detect_shotgun_surgery(changes, git_ctx))
    except Exception as e:
        warnings.append(f"shotgun-surgery detector failed: {e}")

    # Sort: higher confidence first; malformed pinned to the top
    def sort_key(op: Operation):
        mal = 0 if op.kind == OperationKind.MALFORMED else 1
        return (mal, -op.confidence, op.file)
    all_ops.sort(key=sort_key)

    return DiffResult(
        operations=all_ops,
        changes=changes,
        git_context=git_ctx,
        warnings=warnings,
    )
