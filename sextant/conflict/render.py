"""Text rendering for the CLI inspector.

Layout per region (matches phase-1D plan §C):

    [Conflict #N — risk: MEDIUM — classified: CONCURRENT-RENAME]
      Base   (main @ abc123): <one-line summary>
      Ours   (feat/auth)     : renamed `user_id` -> `account_id`
      Theirs (feat/billing)  : renamed `user_id` -> `owner_id`

      Intent signals:
      - ours: ...
      - theirs: ...

      Suggested resolutions:
        [k]       Keep both — split usage
        [u]       Unify to `account_id`
        [u-other] Unify to `owner_id`
        [a]       Abort to base
        [m]       Manual edit
"""
from __future__ import annotations

from io import StringIO
from typing import Optional

from sextant.conflict.types import ConflictFile, ConflictRegion


def _short_sha(sha: Optional[str]) -> str:
    if not sha:
        return "?"
    return sha[:7]


def _one_line(s: str, max_len: int = 60) -> str:
    if not s:
        return "(empty)"
    first = s.splitlines()[0] if s.splitlines() else ""
    if len(first) > max_len:
        return first[: max_len - 1] + "..."
    return first


def render_text(cf: ConflictFile) -> str:
    out = StringIO()
    out.write(f"sextant: {cf.path}\n")

    if not cf.parse_ok:
        out.write(f"  warning: {cf.parse_error}\n")
        if not cf.regions:
            out.write("  (no recognised conflict regions)\n")
            return out.getvalue()

    if not cf.regions:
        out.write("  no conflict markers found.\n")
        return out.getvalue()

    prov = cf.provenance
    if prov.state:
        out.write(
            f"  state: {prov.state}  "
            f"ours: {prov.ours_branch or '?'} @ {_short_sha(prov.ours_sha)}  "
            f"theirs: {prov.theirs_branch or '?'} @ {_short_sha(prov.theirs_sha)}\n"
        )
    out.write(f"  regions: {len(cf.regions)}\n\n")

    for region in cf.regions:
        out.write(_render_region(region, prov))
        out.write("\n")
    return out.getvalue()


def _render_region(region: ConflictRegion, prov) -> str:
    out = StringIO()
    risk = region.risk_bucket().upper()
    kind = region.kind.value.upper()
    out.write(
        f"[Conflict #{region.index} — risk: {risk} — classified: {kind}]\n"
    )

    if region.base is not None:
        base_line = (
            f"  Base   (merge-base @ {_short_sha(prov.base_sha)}): "
            f"{_one_line(region.base)}\n"
        )
        out.write(base_line)
    ours_branch = prov.ours_branch or region.ours_label or "ours"
    theirs_branch = prov.theirs_branch or region.theirs_label or "theirs"
    out.write(f"  Ours   ({ours_branch}): {_one_line(region.ours)}\n")
    out.write(f"  Theirs ({theirs_branch}): {_one_line(region.theirs)}\n")
    out.write(f"\n  rationale: {region.rationale}\n")
    out.write(f"  confidence: {region.confidence:.2f}\n")
    if region.intent_signals:
        out.write("\n  Intent signals:\n")
        for sig in region.intent_signals:
            out.write(f"    - {sig}\n")
    if region.suggestions:
        out.write("\n  Suggested resolutions:\n")
        for sug in region.suggestions:
            label = sug.label
            if sug.detail:
                label = f"{label} — {sug.detail}"
            out.write(f"    [{sug.key:<8}] {label}\n")
    out.write(
        f"\n  (lines {region.line_start}-{region.line_end})\n"
    )
    return out.getvalue()
