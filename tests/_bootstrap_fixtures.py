"""One-shot fixture-corpus generator.

Run from the repo root:

    python tests/_bootstrap_fixtures.py

It writes every fixture's `before/`, `after/`, README.md, and (where
applicable) commit-message.txt + decision-rationale.md to disk under
tests/fixtures/. expected.json is left for the snapshot runner to fill
on first run via DIFFSEXTANT_UPDATE_SNAPSHOTS=1.

This script is part of the test corpus (it documents how the fixtures
were built) but it's not invoked by pytest.
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# fixture spec dataclass-lite
# ---------------------------------------------------------------------------


def write_fixture(category: str, name: str, *,
                  before: Dict[str, str],
                  after: Dict[str, str],
                  readme: str,
                  commit_message: Optional[str] = None,
                  decision_rationale: Optional[str] = None) -> None:
    """Write a fixture to tests/fixtures/<category>/<name>/."""
    fixture_dir = ROOT / category / name
    (fixture_dir / "before").mkdir(parents=True, exist_ok=True)
    (fixture_dir / "after").mkdir(parents=True, exist_ok=True)
    for fname, body in before.items():
        target = fixture_dir / "before" / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    for fname, body in after.items():
        target = fixture_dir / "after" / fname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    (fixture_dir / "README.md").write_text(dedent(readme).strip() + "\n",
                                           encoding="utf-8")
    if commit_message:
        (fixture_dir / "commit-message.txt").write_text(
            commit_message.strip() + "\n", encoding="utf-8")
    if decision_rationale:
        (fixture_dir / "decision-rationale.md").write_text(
            dedent(decision_rationale).strip() + "\n", encoding="utf-8")


# ===========================================================================
# HAPPY PATH — Python (5)
# ===========================================================================


def py_rename_function():
    write_fixture(
        "happy-path", "python-rename-function",
        before={"lib.py": (
            "def get_user_id(conn):\n"
            "    return conn.execute('SELECT user_id')\n"
            "\n"
            "def fetch(conn):\n"
            "    return get_user_id(conn)\n"
        )},
        after={"lib.py": (
            "def get_account_id(conn):\n"
            "    return conn.execute('SELECT user_id')\n"
            "\n"
            "def fetch(conn):\n"
            "    return get_account_id(conn)\n"
        )},
        commit_message="refactor: rename get_user_id to get_account_id",
        readme="""
            # python-rename-function

            Rename a Python function from `get_user_id` -> `get_account_id`. The
            function body is unchanged; only the defining identifier and its
            in-file call sites flip.

            Expected: `rename-symbol` operation with high confidence (> 0.9).
            Commit-message keyword "rename" provides a small confidence prior.
        """,
    )


def py_extract_function():
    write_fixture(
        "happy-path", "python-extract-function",
        before={"lib.py": (
            "def submit_order(order):\n"
            "    if order.total <= 0:\n"
            "        raise ValueError('bad total')\n"
            "    if not order.items:\n"
            "        raise ValueError('empty')\n"
            "    return save(order)\n"
        )},
        after={"lib.py": (
            "def validate_order(order):\n"
            "    if order.total <= 0:\n"
            "        raise ValueError('bad total')\n"
            "    if not order.items:\n"
            "        raise ValueError('empty')\n"
            "\n"
            "def submit_order(order):\n"
            "    validate_order(order)\n"
            "    return save(order)\n"
        )},
        commit_message="refactor: extract validate_order helper",
        readme="""
            # python-extract-function

            Validation block lifted out of `submit_order` into a new helper
            `validate_order`. The original function shrinks; the new function
            has a body identical to the lifted block.

            Expected: `extract-function` operation. May co-emit other ops as the
            structural shape changes (e.g. add-method); the snapshot pins
            current behavior.
        """,
    )


def py_reformat():
    write_fixture(
        "happy-path", "python-reformat",
        before={"lib.py": (
            "x = 1\n"
            "\n"
            "\n"
            "def foo( x , y ):\n"
            "  return x+y\n"
        )},
        after={"lib.py": (
            "x = 1\n"
            "\n"
            "def foo(x, y):\n"
            "    return x + y\n"
        )},
        commit_message="style: reformat foo",
        readme="""
            # python-reformat

            Whitespace + spacing normalisation only — token sequence
            (identifiers, literals) is identical before/after.

            Expected: `reformat` operation, high confidence. Should NOT emit
            rename/edit ops since no token changed.
        """,
    )


def py_add_import():
    write_fixture(
        "happy-path", "python-add-import",
        before={"lib.py": (
            "def foo():\n"
            "    return 42\n"
        )},
        after={"lib.py": (
            "import logging\n"
            "\n"
            "def foo():\n"
            "    return 42\n"
        )},
        commit_message="add logging import",
        readme="""
            # python-add-import

            A bare `import logging` line added to a Python file with no other
            edits.

            Expected: `add-import` operation with high confidence (~0.93).
        """,
    )


def py_comment_only():
    write_fixture(
        "happy-path", "python-comment-only",
        before={"lib.py": (
            "def foo(x):\n"
            "    # old comment\n"
            "    return x + 1\n"
        )},
        after={"lib.py": (
            "def foo(x):\n"
            "    # new comment describing the behavior\n"
            "    return x + 1\n"
        )},
        commit_message="docs: clarify comment in foo",
        readme="""
            # python-comment-only

            A `#` comment line is rewritten; no code tokens change.

            Expected: `comment-only` operation. The reformat classifier should
            NOT fire because the comment text itself is part of the source.
        """,
    )


# ===========================================================================
# HAPPY PATH — TypeScript (5)
# ===========================================================================


def ts_rename_function():
    write_fixture(
        "happy-path", "ts-rename-function",
        before={"lib.ts": (
            "export function getUserId(conn: any): string {\n"
            "    return conn.execute('SELECT user_id');\n"
            "}\n"
            "\n"
            "export function fetch(conn: any) {\n"
            "    return getUserId(conn);\n"
            "}\n"
        )},
        after={"lib.ts": (
            "export function getAccountId(conn: any): string {\n"
            "    return conn.execute('SELECT user_id');\n"
            "}\n"
            "\n"
            "export function fetch(conn: any) {\n"
            "    return getAccountId(conn);\n"
            "}\n"
        )},
        commit_message="refactor: rename getUserId to getAccountId",
        readme="""
            # ts-rename-function

            Rename an exported TypeScript function. Tree-sitter typescript
            grammar drives the AST-matched detection.

            Expected: `rename-symbol` operation, high confidence.
        """,
    )


def ts_extract_function():
    write_fixture(
        "happy-path", "ts-extract-function",
        before={"lib.ts": (
            "function submitOrder(order: any) {\n"
            "    if (order.total <= 0) throw new Error('bad total');\n"
            "    if (!order.items) throw new Error('empty');\n"
            "    return save(order);\n"
            "}\n"
        )},
        after={"lib.ts": (
            "function validateOrder(order: any) {\n"
            "    if (order.total <= 0) throw new Error('bad total');\n"
            "    if (!order.items) throw new Error('empty');\n"
            "}\n"
            "\n"
            "function submitOrder(order: any) {\n"
            "    validateOrder(order);\n"
            "    return save(order);\n"
            "}\n"
        )},
        commit_message="refactor: extract validateOrder helper",
        readme="""
            # ts-extract-function

            Validation block lifted into `validateOrder`. Same shape as the
            python-extract-function fixture but in TypeScript.

            Expected: `extract-function` operation.
        """,
    )


def ts_reformat():
    write_fixture(
        "happy-path", "ts-reformat",
        before={"lib.ts": (
            "function foo( x:number,y:number ){\n"
            "return x+y\n"
            "}\n"
        )},
        after={"lib.ts": (
            "function foo(x: number, y: number) {\n"
            "    return x + y;\n"
        # NOTE: prettier-style formatting often adds trailing semicolons +
        # restructures braces. Keep the token set identical (no new tokens).
            "}\n"
        )},
        commit_message="style: prettier",
        readme="""
            # ts-reformat

            Whitespace + spacing reformat. Tokens (identifiers, literals,
            keywords) unchanged.

            Expected: `reformat` operation. With "prettier" in the commit
            message, lint-fix may also fire; current behavior is pinned by the
            snapshot.
        """,
    )


def ts_add_import():
    write_fixture(
        "happy-path", "ts-add-import",
        before={"lib.ts": (
            "export function foo() {\n"
            "    return 42;\n"
            "}\n"
        )},
        after={"lib.ts": (
            "import { debug } from 'debug';\n"
            "\n"
            "export function foo() {\n"
            "    return 42;\n"
            "}\n"
        )},
        commit_message="chore: add debug import",
        readme="""
            # ts-add-import

            Add a single ES module import to a TypeScript file.

            Expected: `add-import` operation with high confidence.
        """,
    )


def ts_comment_only():
    write_fixture(
        "happy-path", "ts-comment-only",
        before={"lib.ts": (
            "function foo(x: number) {\n"
            "    // old comment\n"
            "    return x + 1;\n"
            "}\n"
        )},
        after={"lib.ts": (
            "function foo(x: number) {\n"
            "    // new comment describing the behavior\n"
            "    return x + 1;\n"
            "}\n"
        )},
        commit_message="docs: clarify comment in foo",
        readme="""
            # ts-comment-only

            Single-line `//` comment edited; code tokens unchanged.

            Expected: `comment-only` operation.
        """,
    )


# ===========================================================================
# HAPPY PATH — Rust (5)
# ===========================================================================


def rust_rename_fn():
    write_fixture(
        "happy-path", "rust-rename-fn",
        before={"lib.rs": (
            "pub fn get_user_id(conn: &Conn) -> String {\n"
            "    conn.execute(\"SELECT user_id\")\n"
            "}\n"
            "\n"
            "pub fn fetch(conn: &Conn) -> String {\n"
            "    get_user_id(conn)\n"
            "}\n"
        )},
        after={"lib.rs": (
            "pub fn get_account_id(conn: &Conn) -> String {\n"
            "    conn.execute(\"SELECT user_id\")\n"
            "}\n"
            "\n"
            "pub fn fetch(conn: &Conn) -> String {\n"
            "    get_account_id(conn)\n"
            "}\n"
        )},
        commit_message="refactor: rename get_user_id to get_account_id",
        readme="""
            # rust-rename-fn

            Rename a pub fn from `get_user_id` to `get_account_id`. Rust
            tree-sitter `function_item` drives the match.

            Expected: `rename-symbol` operation, high confidence.
        """,
    )


def rust_extract_fn():
    write_fixture(
        "happy-path", "rust-extract-fn",
        before={"lib.rs": (
            "pub fn submit_order(order: &Order) -> Result<()> {\n"
            "    if order.total <= 0 { return Err(\"bad total\".into()); }\n"
            "    if order.items.is_empty() { return Err(\"empty\".into()); }\n"
            "    save(order)\n"
            "}\n"
        )},
        after={"lib.rs": (
            "pub fn validate_order(order: &Order) -> Result<()> {\n"
            "    if order.total <= 0 { return Err(\"bad total\".into()); }\n"
            "    if order.items.is_empty() { return Err(\"empty\".into()); }\n"
            "    Ok(())\n"
            "}\n"
            "\n"
            "pub fn submit_order(order: &Order) -> Result<()> {\n"
            "    validate_order(order)?;\n"
            "    save(order)\n"
            "}\n"
        )},
        commit_message="refactor: extract validate_order helper",
        readme="""
            # rust-extract-fn

            Validation block lifted from `submit_order` into a new
            `validate_order`. Rust counterpart to py / ts extract.

            Expected: `extract-function` plus possibly an `add-method`.
        """,
    )


def rust_reformat():
    write_fixture(
        "happy-path", "rust-reformat",
        before={"lib.rs": (
            "fn foo(x:i32,y:i32)->i32{\n"
            "x+y\n"
            "}\n"
        )},
        after={"lib.rs": (
            "fn foo(x: i32, y: i32) -> i32 {\n"
            "    x + y\n"
            "}\n"
        )},
        commit_message="style: rustfmt",
        readme="""
            # rust-reformat

            rustfmt-style whitespace + spacing normalisation. No tokens added
            or removed.

            Expected: `reformat` operation; lint-fix may also fire because
            "rustfmt" is in the commit message.
        """,
    )


def rust_add_use():
    write_fixture(
        "happy-path", "rust-add-use",
        before={"lib.rs": (
            "pub fn foo() -> i32 {\n"
            "    42\n"
            "}\n"
        )},
        after={"lib.rs": (
            "use std::collections::HashMap;\n"
            "\n"
            "pub fn foo() -> i32 {\n"
            "    42\n"
            "}\n"
        )},
        commit_message="chore: import HashMap",
        readme="""
            # rust-add-use

            Add a `use std::collections::HashMap;` line to a Rust file.

            Expected: `add-import` operation; Rust uses `use` matched by the
            same import classifier.
        """,
    )


def rust_comment_only():
    write_fixture(
        "happy-path", "rust-comment-only",
        before={"lib.rs": (
            "fn foo(x: i32) -> i32 {\n"
            "    // old comment\n"
            "    x + 1\n"
            "}\n"
        )},
        after={"lib.rs": (
            "fn foo(x: i32) -> i32 {\n"
            "    // new comment describing the behavior\n"
            "    x + 1\n"
            "}\n"
        )},
        commit_message="docs: clarify comment in foo",
        readme="""
            # rust-comment-only

            Single-line `//` comment edited; code tokens unchanged.

            Expected: `comment-only` operation.
        """,
    )


# ===========================================================================
# HAPPY PATH — Go (5)
# ===========================================================================


def go_rename_func():
    write_fixture(
        "happy-path", "go-rename-func",
        before={"lib.go": (
            "package lib\n"
            "\n"
            "func GetUserID(conn *Conn) string {\n"
            "    return conn.Execute(\"SELECT user_id\")\n"
            "}\n"
            "\n"
            "func Fetch(conn *Conn) string {\n"
            "    return GetUserID(conn)\n"
            "}\n"
        )},
        after={"lib.go": (
            "package lib\n"
            "\n"
            "func GetAccountID(conn *Conn) string {\n"
            "    return conn.Execute(\"SELECT user_id\")\n"
            "}\n"
            "\n"
            "func Fetch(conn *Conn) string {\n"
            "    return GetAccountID(conn)\n"
            "}\n"
        )},
        commit_message="refactor: rename GetUserID to GetAccountID",
        readme="""
            # go-rename-func

            Rename an exported Go func.

            Expected: `rename-symbol` operation.
        """,
    )


def go_extract_func():
    write_fixture(
        "happy-path", "go-extract-func",
        before={"lib.go": (
            "package lib\n"
            "\n"
            "func SubmitOrder(order *Order) error {\n"
            "    if order.Total <= 0 {\n"
            "        return errors.New(\"bad total\")\n"
            "    }\n"
            "    if len(order.Items) == 0 {\n"
            "        return errors.New(\"empty\")\n"
            "    }\n"
            "    return Save(order)\n"
            "}\n"
        )},
        after={"lib.go": (
            "package lib\n"
            "\n"
            "func ValidateOrder(order *Order) error {\n"
            "    if order.Total <= 0 {\n"
            "        return errors.New(\"bad total\")\n"
            "    }\n"
            "    if len(order.Items) == 0 {\n"
            "        return errors.New(\"empty\")\n"
            "    }\n"
            "    return nil\n"
            "}\n"
            "\n"
            "func SubmitOrder(order *Order) error {\n"
            "    if err := ValidateOrder(order); err != nil { return err }\n"
            "    return Save(order)\n"
            "}\n"
        )},
        commit_message="refactor: extract ValidateOrder helper",
        readme="""
            # go-extract-func

            Validation block lifted from `SubmitOrder` into `ValidateOrder`.

            Expected: `extract-function` operation.
        """,
    )


def go_reformat():
    write_fixture(
        "happy-path", "go-reformat",
        before={"lib.go": (
            "package lib\n"
            "\n"
            "func Foo(x int,y int)int{\n"
            "return x+y\n"
            "}\n"
        )},
        after={"lib.go": (
            "package lib\n"
            "\n"
            "func Foo(x int, y int) int {\n"
            "    return x + y\n"
            "}\n"
        )},
        commit_message="style: gofmt",
        readme="""
            # go-reformat

            gofmt-style whitespace normalisation. Token sequence identical.

            Expected: `reformat` (and possibly `lint-fix` since "gofmt" is in
            the commit message).
        """,
    )


def go_add_import():
    write_fixture(
        "happy-path", "go-add-import",
        before={"lib.go": (
            "package lib\n"
            "\n"
            "func Foo() int {\n"
            "    return 42\n"
            "}\n"
        )},
        after={"lib.go": (
            "package lib\n"
            "\n"
            "import \"log\"\n"
            "\n"
            "func Foo() int {\n"
            "    return 42\n"
            "}\n"
        )},
        commit_message="chore: import log",
        readme="""
            # go-add-import

            Add a single `import "log"` line.

            Expected: `add-import` operation.
        """,
    )


def go_comment_only():
    write_fixture(
        "happy-path", "go-comment-only",
        before={"lib.go": (
            "package lib\n"
            "\n"
            "func Foo(x int) int {\n"
            "    // old comment\n"
            "    return x + 1\n"
            "}\n"
        )},
        after={"lib.go": (
            "package lib\n"
            "\n"
            "func Foo(x int) int {\n"
            "    // new comment describing the behavior\n"
            "    return x + 1\n"
            "}\n"
        )},
        commit_message="docs: clarify comment in Foo",
        readme="""
            # go-comment-only

            Single-line `//` comment edited.

            Expected: `comment-only` operation.
        """,
    )


# ===========================================================================
# HAPPY PATH — Markdown (5)
# ===========================================================================


def md_rename_heading():
    write_fixture(
        "happy-path", "markdown-rename-heading",
        before={"doc.md": (
            "# Old Heading\n"
            "\n"
            "Some body text under the heading.\n"
        )},
        after={"doc.md": (
            "# New Heading\n"
            "\n"
            "Some body text under the heading.\n"
        )},
        commit_message="docs: rename heading",
        readme="""
            # markdown-rename-heading

            A markdown H1 is renamed; body text unchanged.

            Markdown grammar is optional; without it, classifiers fall through
            to text-level heuristics. Expected: `rename-symbol` (text fallback)
            OR `plain-edit` placeholder. Snapshot pins current behavior.
        """,
    )


def md_add_section():
    write_fixture(
        "happy-path", "markdown-add-section",
        before={"doc.md": (
            "# Title\n"
            "\n"
            "Intro paragraph.\n"
        )},
        after={"doc.md": (
            "# Title\n"
            "\n"
            "Intro paragraph.\n"
            "\n"
            "## New Section\n"
            "\n"
            "Body of the new section.\n"
        )},
        commit_message="docs: add new section",
        readme="""
            # markdown-add-section

            A new H2 section is appended.

            Expected: a `plain-edit` placeholder (no markdown-aware classifier
            fires today). Snapshot pins this so any future markdown classifier
            shows up as drift.
        """,
    )


def md_reformat():
    write_fixture(
        "happy-path", "markdown-reformat",
        before={"doc.md": (
            "#   Title\n"
            "\n"
            "Intro    paragraph    with    extra spaces.\n"
        )},
        after={"doc.md": (
            "# Title\n"
            "\n"
            "Intro paragraph with extra spaces.\n"
        )},
        commit_message="docs: tidy whitespace",
        readme="""
            # markdown-reformat

            Whitespace-only tidy of a markdown file. Token sequence (words and
            punctuation) is preserved.

            Expected: `reformat` operation.
        """,
    )


def md_comment_only():
    # Markdown HTML comments
    write_fixture(
        "happy-path", "markdown-comment-only",
        before={"doc.md": (
            "# Title\n"
            "\n"
            "<!-- old hidden comment -->\n"
            "\n"
            "Body.\n"
        )},
        after={"doc.md": (
            "# Title\n"
            "\n"
            "<!-- new hidden comment with more detail -->\n"
            "\n"
            "Body.\n"
        )},
        commit_message="docs: update html comment",
        readme="""
            # markdown-comment-only

            An HTML-style markdown comment block is edited; visible content
            unchanged.

            No language-aware comment classifier fires for markdown today; the
            snapshot pins the actual behavior (likely `plain-edit`).
        """,
    )


def md_link_update():
    write_fixture(
        "happy-path", "markdown-link-update",
        before={"doc.md": (
            "# Title\n"
            "\n"
            "See [the docs](https://old.example.com/docs) for more.\n"
        )},
        after={"doc.md": (
            "# Title\n"
            "\n"
            "See [the docs](https://new.example.com/docs) for more.\n"
        )},
        commit_message="docs: update doc URL",
        readme="""
            # markdown-link-update

            A markdown link target is updated; surrounding text unchanged.

            Expected: a `plain-edit` placeholder OR a text-level rename fallback
            (the URL host is the only changed token). Snapshot pins behavior.
        """,
    )


# ===========================================================================
# MULTI-OP (5)
# ===========================================================================


def multi_py_rename_and_add_import():
    write_fixture(
        "multi-op", "python-rename-and-add-import",
        before={"lib.py": (
            "def get_user_id(conn):\n"
            "    return conn.execute('SELECT user_id')\n"
        )},
        after={"lib.py": (
            "import logging\n"
            "\n"
            "def get_account_id(conn):\n"
            "    logging.info('fetching')\n"
            "    return conn.execute('SELECT user_id')\n"
        )},
        commit_message="refactor: rename + add logging",
        readme="""
            # python-rename-and-add-import

            Two interleaved operations: function rename `get_user_id` ->
            `get_account_id` AND a new `import logging` plus a logging call.

            Expected: at least `add-import` and one of
            {`rename-symbol`, `change-signature`, `plain-edit`}. Snapshot pins
            actual behavior — the rename detector requires body-similarity, and
            the added log line may push it to a fallback category.
        """,
    )


def multi_py_add_import_and_rename():
    write_fixture(
        "multi-op", "python-add-import-and-rename",
        before={"lib.py": (
            "def get_user_id(conn):\n"
            "    return conn.execute('SELECT user_id')\n"
            "\n"
            "def fetch(conn):\n"
            "    return get_user_id(conn)\n"
        )},
        after={"lib.py": (
            "import logging\n"
            "\n"
            "def get_account_id(conn):\n"
            "    return conn.execute('SELECT user_id')\n"
            "\n"
            "def fetch(conn):\n"
            "    return get_account_id(conn)\n"
        )},
        commit_message="refactor: rename get_user_id to get_account_id + add logging import",
        readme="""
            # python-add-import-and-rename

            Two clean operations in one diff: a new `import logging` AND a
            function rename from `get_user_id` to `get_account_id`. Body of
            the renamed function is unchanged.

            Expected: `add-import` AND `rename-symbol` (2 ops).
        """,
    )


def multi_py_remove_import_and_rename():
    write_fixture(
        "multi-op", "python-remove-import-and-rename",
        before={"lib.py": (
            "import os\n"
            "import sys\n"
            "\n"
            "def compute(x):\n"
            "    return x * 2 + sys.maxsize\n"
        )},
        after={"lib.py": (
            "import sys\n"
            "\n"
            "def calculate(x):\n"
            "    return x * 2 + sys.maxsize\n"
        )},
        commit_message="refactor: rename compute to calculate, remove unused import",
        readme="""
            # python-remove-import-and-rename

            Unused `import os` removed AND `compute` renamed to `calculate`.

            Expected: `remove-import` AND `rename-symbol` (2 ops).
        """,
    )


def multi_py_move_file_and_rename_symbol():
    write_fixture(
        "multi-op", "python-move-file-and-rename-symbol",
        before={"old/lib.py": (
            "def get_user_id(conn):\n"
            "    return conn.execute('SELECT user_id')\n"
        )},
        after={"new/lib.py": (
            "def get_account_id(conn):\n"
            "    return conn.execute('SELECT user_id')\n"
        )},
        commit_message="refactor: move + rename",
        readme="""
            # python-move-file-and-rename-symbol

            File moves from `old/lib.py` to `new/lib.py` AND the function is
            renamed simultaneously.

            Expected: `move-file` (path change with body-similarity high enough)
            plus a `rename-symbol`. Confidence on move-file may be lower than a
            pure-move because the body diverges.
        """,
    )


def multi_ts_rename_class_and_update_callers():
    write_fixture(
        "multi-op", "ts-rename-class-and-update-callers",
        before={
            "user.ts": (
                "export class UserStore {\n"
                "    fetch(): string { return 'u'; }\n"
                "}\n"
            ),
            "app.ts": (
                "import { UserStore } from './user';\n"
                "\n"
                "const s = new UserStore();\n"
                "s.fetch();\n"
            ),
        },
        after={
            "user.ts": (
                "export class AccountStore {\n"
                "    fetch(): string { return 'u'; }\n"
                "}\n"
            ),
            "app.ts": (
                "import { AccountStore } from './user';\n"
                "\n"
                "const s = new AccountStore();\n"
                "s.fetch();\n"
            ),
        },
        commit_message="refactor: rename UserStore to AccountStore",
        readme="""
            # ts-rename-class-and-update-callers

            Class rename touches two files: the definition site and the
            importing caller. Cross-file consistency is exercised here.

            Expected: at least one `rename-symbol` (in user.ts), and the caller
            file produces a rename or plain-edit per DiffSextant's per-file
            classifier loop.
        """,
    )


# NOTE: an earlier `markdown-rename-heading-and-add-section` fixture was
# removed because markdown has no AST-aware classifier in v0.1.0 — the diff
# collapsed to a single `plain-edit`, failing the multi-op-emits-2+-ops
# meta-test. When a markdown classifier lands, restore that fixture.


def multi_py_two_files_two_ops():
    """Two-file diff: each file produces its own op cleanly."""
    write_fixture(
        "multi-op", "python-two-files-rename-and-import",
        before={
            "store.py": (
                "def fetch_user(uid):\n"
                "    return {'id': uid}\n"
            ),
            "app.py": (
                "from store import fetch_user\n"
                "\n"
                "def run():\n"
                "    return fetch_user(1)\n"
            ),
        },
        after={
            "store.py": (
                "def fetch_account(uid):\n"
                "    return {'id': uid}\n"
            ),
            "app.py": (
                "import logging\n"
                "from store import fetch_account\n"
                "\n"
                "def run():\n"
                "    logging.info('run')\n"
                "    return fetch_account(1)\n"
            ),
        },
        commit_message="refactor: rename fetch_user -> fetch_account, add logging",
        readme="""
            # python-two-files-rename-and-import

            Two-file diff. `store.py` produces a `rename-symbol`. `app.py`
            produces an `add-import` (logging) plus another classifier on the
            updated import line.

            Expected: at least 2 distinct ops across the two files.
        """,
    )


# ===========================================================================
# AMBIGUOUS (5)
# ===========================================================================


def amb_rename_vs_signature_change():
    write_fixture(
        "ambiguous", "rename-vs-signature-change",
        before={"lib.py": (
            "def foo(x):\n"
            "    return x + 1\n"
        )},
        after={"lib.py": (
            "def bar(x, y=0):\n"
            "    return x + y + 1\n"
        )},
        commit_message="refactor: extend foo to bar with y param",
        readme="""
            # rename-vs-signature-change

            The function name flipped (foo -> bar) AND the signature gained a
            new defaulted parameter (y=0). A naive matcher could emit two ops
            (rename + change-signature) or a single composite.

            Expected: see decision-rationale.md.
        """,
        decision_rationale="""
            # Why this fixture's expected output is what it is

            When name AND signature both change, DiffSextant currently emits
            BOTH a `rename-symbol` and a `change-signature` op (two ops). The
            rename detector is structural-position-based (same function order,
            different name) so it still fires. The change-signature detector
            picks up the new parameter independently.

            **Pin rationale:** keeping both ops is the safe default — it
            surfaces all the meaningful information. A future "composite"
            classifier could collapse them into one `change-signature` (where
            rename is incidental), but that requires a heuristic for "is the
            rename driven by the signature change?". Until that exists, two
            distinct ops give the user / agent the most information.

            If the policy changes (collapse to one), this fixture's
            expected.json will fail and the failure tells you the rule
            changed — which is exactly the point.
        """,
    )


def amb_extract_vs_rename():
    write_fixture(
        "ambiguous", "extract-vs-rename",
        before={"lib.py": (
            "def submit_order(order):\n"
            "    if order.total <= 0:\n"
            "        raise ValueError('bad')\n"
            "    return save(order)\n"
        )},
        after={"lib.py": (
            "def validate(order):\n"
            "    if order.total <= 0:\n"
            "        raise ValueError('bad')\n"
            "\n"
            "def submit_order(order):\n"
            "    validate(order)\n"
            "    return save(order)\n"
        )},
        commit_message="refactor: extract validation",
        readme="""
            # extract-vs-rename

            A new function `validate` appears alongside the original
            `submit_order` (which now calls it). Naively this could be read as
            "rename submit_order to validate" because submit_order's body
            shrinks dramatically.

            Expected: extract-function should win — see decision-rationale.md.
        """,
        decision_rationale="""
            # Why extract-function should win, not rename

            DiffSextant's rename detector requires body-similarity above a
            threshold (~0.6 Jaccard on normalised tokens). After the
            "rename", submit_order's body is `validate(order); return
            save(order)` — bodies are NOT similar to the before, so the rename
            heuristic correctly declines.

            The extract-function classifier instead fires because:
              - A new function with NO previous match was added
              - Its body matches a contiguous block of the source
              - The original function gained a call-site to the new one

            **Pin rationale:** extract-function is the correct classification.
            Rename should NOT fire. If it does, that's drift — likely a
            similarity-threshold regression.
        """,
    )


def amb_reformat_vs_real_edit():
    write_fixture(
        "ambiguous", "reformat-vs-real-edit",
        before={"lib.py": (
            "def foo( x , y ):\n"
            "  return x+y\n"
        )},
        after={"lib.py": (
            "def foo(x, y):\n"
            "    return x + y + 1\n"
        )},
        commit_message="style: reformat foo (and tweak)",
        readme="""
            # reformat-vs-real-edit

            Whitespace was normalised AND a `+ 1` was added. Reformat must NOT
            fire because the token sequence changed.

            Expected: NOT `reformat`; should be `plain-edit` or `change-signature`
            depending on which classifier picks it up. See decision-rationale.md.
        """,
        decision_rationale="""
            # Why reformat must NOT fire here

            The reformat detector (diffsextant.ops.reformat.ReformatClassifier)
            requires the token sequence (identifiers + literals + numbers) to
            be IDENTICAL before/after. Adding `+ 1` introduces a new numeric
            literal `1`, breaking that invariant.

            **Pin rationale:** This fixture protects against a class of
            regression where a relaxed reformat detector starts emitting
            `reformat` for diffs that contain real semantic changes. Such a
            regression would be high-impact: reformat ops are suppressed by
            most consumers, so a misclassified semantic change becomes
            invisible.

            Expected current output: `plain-edit` (no other classifier
            recognises the shape).
        """,
    )


def amb_comment_only_vs_docstring_only():
    write_fixture(
        "ambiguous", "comment-only-vs-docstring-only",
        before={"lib.py": (
            "def foo(x):\n"
            "    \"\"\"old docstring\"\"\"\n"
            "    return x\n"
        )},
        after={"lib.py": (
            "def foo(x):\n"
            "    \"\"\"new and improved docstring\"\"\"\n"
            "    return x\n"
        )},
        commit_message="docs: improve foo docstring",
        readme="""
            # comment-only-vs-docstring-only

            Only the function docstring changed. Both `comment-only` and
            `docstring-only` classifiers could plausibly fire.

            Expected: `docstring-only` (specific) wins; `comment-only` may also
            fire if the underlying detector treats triple-quoted strings as
            comments. See decision-rationale.md.
        """,
        decision_rationale="""
            # Which wins: comment-only or docstring-only

            DiffSextant has two distinct classifiers — `docstring-only` is
            language-specific (Python triple-quoted strings as the FIRST
            statement of a function/class/module). `comment-only` is more
            general (#-style comments).

            **Pin rationale:** `docstring-only` is the correct classification
            for this case (the change is inside a docstring). The
            comment-only detector should NOT fire because a docstring is not a
            `#`-comment. Both could fire under a too-permissive detector — the
            snapshot pins the current correct behavior.

            Risk attached to docstring-only is lower than comment-only — both
            have minimal call-site impact, but documentation quality is the
            ONLY semantic effect.
        """,
    )


def amb_move_file_vs_split_file():
    write_fixture(
        "ambiguous", "move-file-vs-split-file",
        before={
            "lib.py": (
                "def alpha():\n"
                "    return 1\n"
                "\n"
                "def beta():\n"
                "    return 2\n"
            ),
        },
        after={
            "alpha.py": (
                "def alpha():\n"
                "    return 1\n"
            ),
            "beta.py": (
                "def beta():\n"
                "    return 2\n"
            ),
        },
        commit_message="refactor: split lib into alpha + beta",
        readme="""
            # move-file-vs-split-file

            One file split into two. A naive move-file detector could fire
            twice (or once with low confidence) because path-pairing is
            ambiguous.

            Expected: see decision-rationale.md. DiffSextant currently lacks a
            split-file classifier, so the diff likely surfaces as 1 deletion +
            2 additions = three plain-edit / move-file / add ops.
        """,
        decision_rationale="""
            # Why move-file should NOT fire here

            move-file requires near-identical body content between
            before-path and after-path. Here, neither alpha.py nor beta.py
            has a body matching the original lib.py — each contains only HALF
            of it. The move-file similarity check (>0.9 confidence) correctly
            declines.

            DiffSextant does not yet ship a `split-file` classifier (it's listed
            in OperationKind but no detector emits it). Result: lib.py shows
            up as a deletion (no after-body), and alpha.py + beta.py show up
            as additions, all categorised as `plain-edit`.

            **Pin rationale:** when a `split-file` classifier lands, this
            fixture's snapshot will fail — that failure tells you the new
            classifier is firing on the right shape.
        """,
    )


# ===========================================================================
# NEGATIVE (5)
# ===========================================================================


def neg_identical_no_change():
    write_fixture(
        "negative", "identical-no-change",
        before={"lib.py": (
            "def foo(x):\n"
            "    return x + 1\n"
        )},
        after={"lib.py": (
            "def foo(x):\n"
            "    return x + 1\n"
        )},
        commit_message="empty: identical content",
        readme="""
            # identical-no-change

            Before and after files are byte-identical. The diff is empty.

            Expected: zero operations. The driver must NOT emit a plain-edit
            placeholder for unchanged files.
        """,
    )


def neg_reformat_with_token_change_rejects_reformat():
    write_fixture(
        "negative", "reformat-with-token-change-rejects-reformat",
        before={"lib.py": (
            "def foo(x):\n"
            "    return x\n"
        )},
        after={"lib.py": (
            "def foo(x):\n"
            "    return y\n"
        )},
        commit_message="hack: change return value",
        readme="""
            # reformat-with-token-change-rejects-reformat

            The literal change `x` -> `y` in the return statement breaks the
            reformat invariant.

            Expected: NO `reformat` operation; some other classifier (or
            `plain-edit`) should fire instead.
        """,
    )


def neg_rename_with_body_change_becomes_edit():
    write_fixture(
        "negative", "rename-with-body-change-becomes-edit",
        before={"lib.py": (
            "def foo(x):\n"
            "    return x\n"
        )},
        after={"lib.py": (
            "def bar(x):\n"
            "    return x * 2 + log(x) + 17\n"
        )},
        commit_message="rewrite foo",
        readme="""
            # rename-with-body-change-becomes-edit

            Function name changed AND the body is materially different.
            Body-similarity Jaccard falls below 0.6 — rename detector should
            decline.

            Expected: NO `rename-symbol` op (or one only if similarity sneaks
            past). Likely a `plain-edit` placeholder.
        """,
    )


def neg_move_file_too_divergent_rejects():
    write_fixture(
        "negative", "move-file-too-divergent-rejects",
        before={"old/lib.py": (
            "def foo():\n"
            "    return 1\n"
            "\n"
            "def bar():\n"
            "    return 2\n"
        )},
        after={"new/lib.py": (
            "import os\n"
            "import sys\n"
            "\n"
            "def completely_different_function():\n"
            "    return os.environ['HOME'] + sys.path[0]\n"
            "\n"
            "class TotallyNew:\n"
            "    def method(self):\n"
            "        return 'nope'\n"
        )},
        commit_message="rewrite: replaces old/lib.py contents",
        readme="""
            # move-file-too-divergent-rejects

            Both the path AND the body changed dramatically — body-similarity
            below the move-file threshold.

            Expected: NO `move-file` operation. Could surface as deletion +
            addition (two plain-edits) or as some other shape.
        """,
    )


def neg_empty_file():
    write_fixture(
        "negative", "empty-file",
        before={"lib.py": ""},
        after={"lib.py": "def foo(): return 1\n"},
        commit_message="add lib.py",
        readme="""
            # empty-file

            File starts empty and gains content. This stresses the classifiers
            against zero-length input — none of the AST classifiers should
            crash.

            Expected: a `plain-edit` for the new content (or `add-method` if
            recognised). No exceptions in classifier output (warnings empty).
        """,
    )


# ===========================================================================
# REAL-WORLD (3) — sampled from this repo (diffsextant; historical
# commits captured under the pre-rename `sextant/` package layout) and
# AgentFactory
# ===========================================================================


def rw_small_rename_from_real_commit():
    """Inspired by typical Sextant-style "rename helper" commits."""
    write_fixture(
        "real-world", "small-rename-from-real-commit",
        before={"sextant/parse.py": (
            "def detect_lang(path):\n"
            "    suffix = path.rsplit('.', 1)[-1] if '.' in path else ''\n"
            "    return EXT_TO_LANG.get('.' + suffix.lower())\n"
            "\n"
            "def parse_src(source, language):\n"
            "    return _parse_impl(source, language)\n"
        )},
        after={"sextant/parse.py": (
            "def detect_language(path):\n"
            "    suffix = path.rsplit('.', 1)[-1] if '.' in path else ''\n"
            "    return EXT_TO_LANG.get('.' + suffix.lower())\n"
            "\n"
            "def parse_src(source, language):\n"
            "    return _parse_impl(source, language)\n"
        )},
        commit_message=(
            "refactor: rename detect_lang to detect_language\n"
            "\n"
            "Inspired by an actual Sextant commit during phase 1A. The helper\n"
            "was misnamed; this aligns with the `language=` field on FileChange."
        ),
        readme="""
            # small-rename-from-real-commit

            A 1-symbol rename of the `detect_lang` -> `detect_language` helper,
            patterned after a real Sextant commit during phase 1A. The shape
            (small surface area, single function, in-file callers updated) is
            the most common refactor in any codebase.

            Expected: `rename-symbol` operation, high confidence.
            Source: synthetic but representative of /c/git/sextant commits.
        """,
    )


def rw_extract_helper_from_real_commit():
    """Inspired by AgentFactory's `propagate.sh` -> `build-bundle.sh` extraction."""
    write_fixture(
        "real-world", "extract-helper-from-real-commit",
        before={"scripts/build.py": (
            "def build_bundle(project_root, marketplaces):\n"
            "    out_dir = project_root / '.claude' / 'agents'\n"
            "    out_dir.mkdir(parents=True, exist_ok=True)\n"
            "    seen = set()\n"
            "    for mp in marketplaces:\n"
            "        for agent_file in (mp / 'agents').glob('*.md'):\n"
            "            if agent_file.name in seen:\n"
            "                continue\n"
            "            seen.add(agent_file.name)\n"
            "            (out_dir / agent_file.name).write_text(agent_file.read_text())\n"
            "    return out_dir\n"
        )},
        after={"scripts/build.py": (
            "def _copy_agents(out_dir, marketplaces):\n"
            "    seen = set()\n"
            "    for mp in marketplaces:\n"
            "        for agent_file in (mp / 'agents').glob('*.md'):\n"
            "            if agent_file.name in seen:\n"
            "                continue\n"
            "            seen.add(agent_file.name)\n"
            "            (out_dir / agent_file.name).write_text(agent_file.read_text())\n"
            "\n"
            "def build_bundle(project_root, marketplaces):\n"
            "    out_dir = project_root / '.claude' / 'agents'\n"
            "    out_dir.mkdir(parents=True, exist_ok=True)\n"
            "    _copy_agents(out_dir, marketplaces)\n"
            "    return out_dir\n"
        )},
        commit_message=(
            "refactor: extract _copy_agents helper from build_bundle\n"
            "\n"
            "Patterned after an actual AgentFactory commit during the\n"
            "scripts/build-bundle.sh refactor. Inner copy loop was lifted into\n"
            "a private helper to make the public function read top-to-bottom."
        ),
        readme="""
            # extract-helper-from-real-commit

            Extract-function on a realistic file-tree-walking helper. Patterned
            after an AgentFactory `scripts/build-bundle.sh` refactor.

            Expected: `extract-function` operation, plus possibly
            `add-method`. Realistic refactor noise (whitespace tweaks, slight
            structural reshuffle) tests the extract detector against
            non-pristine inputs.
        """,
    )


def rw_add_feature_from_real_commit():
    """Inspired by hopewell's `hopewell resume` command addition."""
    write_fixture(
        "real-world", "add-feature-from-real-commit",
        before={"cli.py": (
            "import argparse\n"
            "\n"
            "def cmd_list(args):\n"
            "    print('listing nodes')\n"
            "    return 0\n"
            "\n"
            "def cmd_show(args):\n"
            "    print('showing node', args.id)\n"
            "    return 0\n"
            "\n"
            "def main():\n"
            "    p = argparse.ArgumentParser()\n"
            "    sub = p.add_subparsers(dest='cmd', required=True)\n"
            "    l = sub.add_parser('list')\n"
            "    l.set_defaults(func=cmd_list)\n"
            "    s = sub.add_parser('show')\n"
            "    s.add_argument('id')\n"
            "    s.set_defaults(func=cmd_show)\n"
            "    args = p.parse_args()\n"
            "    return args.func(args)\n"
        )},
        after={"cli.py": (
            "import argparse\n"
            "\n"
            "def cmd_list(args):\n"
            "    print('listing nodes')\n"
            "    return 0\n"
            "\n"
            "def cmd_show(args):\n"
            "    print('showing node', args.id)\n"
            "    return 0\n"
            "\n"
            "def cmd_resume(args):\n"
            "    print('active claims:', _load_claims())\n"
            "    print('ready queue (claim-aware):')\n"
            "    return 0\n"
            "\n"
            "def main():\n"
            "    p = argparse.ArgumentParser()\n"
            "    sub = p.add_subparsers(dest='cmd', required=True)\n"
            "    l = sub.add_parser('list')\n"
            "    l.set_defaults(func=cmd_list)\n"
            "    s = sub.add_parser('show')\n"
            "    s.add_argument('id')\n"
            "    s.set_defaults(func=cmd_show)\n"
            "    r = sub.add_parser('resume')\n"
            "    r.set_defaults(func=cmd_resume)\n"
            "    args = p.parse_args()\n"
            "    return args.func(args)\n"
        )},
        commit_message=(
            "feat: add `cli resume` subcommand\n"
            "\n"
            "Patterned after the hopewell `resume` subcommand. Adds a new\n"
            "command handler + wires it into the argparse subparser table."
        ),
        readme="""
            # add-feature-from-real-commit

            Adds a new `cmd_resume` function and threads it through the
            argparse subparser registration. Models the most common
            "add-feature" diff shape: one new function, two existing functions
            edited slightly to register it.

            Expected: at least an `add-method` or `extract-function` for the
            new handler. The argparse-registration block also gets edits.
            Realistic noise — multiple structural ops in a single PR.
        """,
    )


# ===========================================================================
# entry
# ===========================================================================


def main():
    # Happy path — Python
    py_rename_function()
    py_extract_function()
    py_reformat()
    py_add_import()
    py_comment_only()
    # Happy path — TypeScript
    ts_rename_function()
    ts_extract_function()
    ts_reformat()
    ts_add_import()
    ts_comment_only()
    # Happy path — Rust
    rust_rename_fn()
    rust_extract_fn()
    rust_reformat()
    rust_add_use()
    rust_comment_only()
    # Happy path — Go
    go_rename_func()
    go_extract_func()
    go_reformat()
    go_add_import()
    go_comment_only()
    # Happy path — Markdown
    md_rename_heading()
    md_add_section()
    md_reformat()
    md_comment_only()
    md_link_update()
    # Multi-op
    multi_py_rename_and_add_import()
    multi_py_add_import_and_rename()
    multi_py_remove_import_and_rename()
    multi_py_move_file_and_rename_symbol()
    multi_ts_rename_class_and_update_callers()
    multi_py_two_files_two_ops()
    # Ambiguous
    amb_rename_vs_signature_change()
    amb_extract_vs_rename()
    amb_reformat_vs_real_edit()
    amb_comment_only_vs_docstring_only()
    amb_move_file_vs_split_file()
    # Negative
    neg_identical_no_change()
    neg_reformat_with_token_change_rejects_reformat()
    neg_rename_with_body_change_becomes_edit()
    neg_move_file_too_divergent_rejects()
    neg_empty_file()
    # Real-world
    rw_small_rename_from_real_commit()
    rw_extract_helper_from_real_commit()
    rw_add_feature_from_real_commit()
    print(f"wrote fixtures under {ROOT}")


if __name__ == "__main__":
    main()
