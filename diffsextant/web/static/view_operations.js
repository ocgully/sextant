// Operations view (default).
//
// Layout: two-pane split.
//   Left  = list of operations grouped by file, ordered by max risk.
//   Right = detail pane for the currently-selected op (before/after,
//           risk signals, evidence, narrative).
//
// Risk-graph React Flow visualization is deferred to phase 1D.

import { h, Fragment } from "https://esm.sh/preact@10.22.0";
import { useState, useMemo, useCallback } from "https://esm.sh/preact@10.22.0/hooks";

const KIND_NARRATIVE = {
  "rename-symbol":      "A symbol was renamed. DiffSextant matches identifier-occurrence sets across before/after to detect this.",
  "extract-function":   "A block of code was extracted into a new function. The body of the new function appears verbatim in the old code.",
  "inline-function":    "A function was inlined into its callers; the body of the old function appears verbatim at each call site.",
  "move-symbol":        "A symbol moved between files (often paired with import changes).",
  "move-file":          "A whole file moved or was renamed without substantive content changes.",
  "change-signature":   "A function's parameter list / return type / kw-args changed.",
  "reformat":           "Whitespace / line-breaks only; the AST is unchanged.",
  "lint-fix":           "Style normalization that matches a known formatter's output.",
  "comment-only":       "Only inline comments changed — no executable text.",
  "docstring-only":     "Only docstrings changed.",
  "reorder-statements": "Statements were reordered without otherwise changing them.",
  "reorder-imports":    "Imports were reordered (typically by an isort-like tool).",
  "add-import":         "A new import was added.",
  "remove-import":      "An import was removed.",
  "invert-condition":   "An if-condition was negated (and its branches swapped, typically).",
  "add-test":           "A new test was added.",
  "remove-test":        "An existing test was removed.",
  "rename-test":        "A test was renamed.",
  "plain-edit":         "A change DiffSextant could not classify into a structural operation.",
  "malformed":          "The file failed parse / contains malformed text — operation classification was suppressed.",
  "strategy-pattern-intro": "A strategy / dispatch pattern was introduced (multiple subclasses + a polymorphic call site).",
  "god-class-forming":      "A class is growing beyond a healthy size threshold.",
  "shotgun-surgery":        "The same conceptual change spread across many files.",
};

function riskBucket(score) {
  if (score == null) return "none";
  if (score >= 0.7) return "high";
  if (score >= 0.4) return "medium";
  return "low";
}

function fileLabel(file, files) {
  const f = (files || []).find(x =>
    (x.path_after === file) || (x.path_before === file && x.path_after == null)
  );
  if (!f) return { label: file, badges: [] };
  const badges = [];
  if (f.is_new) badges.push("new");
  if (f.is_deleted) badges.push("deleted");
  if (f.is_renamed) badges.push(`renamed from ${f.path_before}`);
  return {
    label: f.path_after || f.path_before || file,
    badges,
    language: f.language,
  };
}

export function OperationsView({ diff }) {
  const [selectedIdx, setSelectedIdx] = useState(0);

  if (!diff) return h("div", { class: "empty" }, "No diff loaded.");
  if (diff.error) return h("div", { class: "error" }, diff.error);

  const ops = diff.operations || [];
  if (ops.length === 0) {
    return h("div", { class: "empty" },
      "No classified operations in this diff.",
      h("div", { class: "muted", style: "margin-top:6px" },
        `${(diff.files || []).length} file(s) touched`));
  }

  const groups = useMemo(() => {
    const m = new Map();
    ops.forEach((op, i) => {
      if (!m.has(op.file)) m.set(op.file, []);
      m.get(op.file).push({ ...op, _idx: i });
    });
    return Array.from(m.entries())
      .map(([file, fops]) => ({
        file,
        ops: fops,
        maxRisk: Math.max(...fops.map(o => (o.risk?.score) || 0)),
      }))
      .sort((a, b) => b.maxRisk - a.maxRisk || a.file.localeCompare(b.file));
  }, [ops]);

  const summary = useMemo(() => {
    const kinds = {};
    let high = 0, medium = 0, low = 0;
    for (const op of ops) {
      kinds[op.kind] = (kinds[op.kind] || 0) + 1;
      const b = riskBucket(op.risk?.score);
      if (b === "high") high++;
      else if (b === "medium") medium++;
      else if (b === "low") low++;
    }
    return { kinds, high, medium, low };
  }, [ops]);

  const selected = ops[selectedIdx] || ops[0];
  const select = useCallback((idx) => setSelectedIdx(idx), []);

  return h("div", { class: "ops-layout" },
    h("div", { class: "ops-list-pane" },
      h("div", { class: "ops-summary" },
        h("span", { class: "pill" }, `${ops.length} op${ops.length === 1 ? "" : "s"}`),
        summary.high   > 0 && h("span", { class: "pill risk-high"   }, `${summary.high} high`),
        summary.medium > 0 && h("span", { class: "pill risk-medium" }, `${summary.medium} medium`),
        summary.low    > 0 && h("span", { class: "pill risk-low"    }, `${summary.low} low`),
      ),
      groups.map((g) => {
        const fl = fileLabel(g.file, diff.files);
        return h("div", { class: "ops-file-group", key: g.file },
          h("div", { class: "ops-file-head" },
            h("span", { class: "file-path" }, fl.label),
            fl.language && h("span", { class: "file-meta" }, fl.language),
            fl.badges.map(b => h("span", { class: "file-meta", key: b }, `[${b}]`)),
          ),
          g.ops.map(op => {
            const rb = riskBucket(op.risk?.score);
            const isSel = op._idx === selectedIdx;
            return h("div", {
              class: `op-row kind-${op.kind} ${isSel ? "selected" : ""}`,
              key: op._idx,
              onClick: () => select(op._idx),
            },
              h("span", { class: "op-kind" }, op.kind),
              h("span", { class: "op-summary" }, op.summary),
              op.risk && h("span", {
                class: `op-risk-pill risk-${rb}`,
                title: `risk score ${(op.risk.score || 0).toFixed(2)}`,
              }, rb),
              h("span", { class: "op-conf" }, `${(op.confidence || 0).toFixed(2)}`),
            );
          }),
        );
      }),
    ),
    h(OperationDetail, { op: selected }),
  );
}

function OperationDetail({ op }) {
  if (!op) return h("div", { class: "ops-detail-pane" },
    h("div", { class: "detail-empty" }, "Select an operation."));

  return h("div", { class: `ops-detail-pane kind-${op.kind}` },
    h("div", { class: "detail-head" },
      h("span", { class: "detail-kind" }, op.kind),
      h("span", { class: "detail-summary" }, op.summary),
    ),
    h("dl", { class: "risk-grid", style: "margin-top:6px" },
      h("dt", null, "file"),
      h("dd", null, op.file),
      h("dt", null, "confidence"),
      h("dd", null, `${(op.confidence || 0).toFixed(2)} (${op.confidence_bucket || "?"})`),
      op.risk && h(Fragment, null,
        h("dt", null, "risk score"),
        h("dd", null, (op.risk.score || 0).toFixed(2)),
        h("dt", null, "risk bucket"),
        h("dd", null, op.risk.bucket || riskBucket(op.risk.score)),
      ),
    ),
    h("div", { class: "detail-section" },
      h("h3", null, "what this operation means"),
      h("div", { class: "detail-narrative" },
        KIND_NARRATIVE[op.kind] || "An unclassified change in this file."),
    ),
    (op.before || op.after) && h("div", { class: "detail-section" },
      h("h3", null, "before / after"),
      h("div", { class: "detail-snippets" },
        h("div", null,
          h("div", { class: "detail-snippet-label" }, "before"),
          h("div", { class: "detail-snippet before" }, op.before || "(empty)")),
        h("div", null,
          h("div", { class: "detail-snippet-label" }, "after"),
          h("div", { class: "detail-snippet after" }, op.after || "(empty)")),
      ),
    ),
    op.risk && op.risk.signals && Object.keys(op.risk.signals).length > 0 && h("div",
      { class: "detail-section" },
      h("h3", null, "risk signals"),
      h("dl", { class: "risk-grid" },
        Object.entries(op.risk.signals).flatMap(([k, v]) => [
          h("dt", { key: `dt-${k}` }, k),
          h("dd", { key: `dd-${k}` }, formatSignal(v)),
        ]),
      ),
    ),
    op.evidence && Object.keys(op.evidence).length > 0 && h("div", { class: "detail-section" },
      h("h3", null, "evidence"),
      h("div", { class: "detail-evidence" }, JSON.stringify(op.evidence, null, 2)),
    ),
    op.related_files && op.related_files.length > 0 && h("div", { class: "detail-section" },
      h("h3", null, "related files"),
      h("ul", { class: "detail-related" },
        op.related_files.map((f) => h("li", { key: f }, f))),
    ),
  );
}

function formatSignal(v) {
  if (typeof v === "number") return v.toFixed(2);
  if (typeof v === "object" && v !== null) return JSON.stringify(v);
  return String(v);
}
