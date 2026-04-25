// Classic-text view (§6.2 of the Sextant plan).
//
// Side-by-side OR unified text-diff with semantic overlay. Each operation
// contributes a colour to the gutter strip on the lines where its
// before/after snippet appears. Hovering a line shows a tooltip naming
// the operation. Folding controls hide reformat / comment-only blobs.
//
// The diff is reconstructed from each operation's before/after snippet
// (the full file body isn't on the wire — only what each classifier
// chose to surface). That's deliberate: the goal of the classic view in
// 1C is "this blob is just a reformat — skip" labelling at a glance,
// not byte-perfect re-rendering of the file. A future iteration can
// fetch a full text-diff endpoint when the user wants more.

import { h, Fragment } from "https://esm.sh/preact@10.22.0";
import { useState, useMemo } from "https://esm.sh/preact@10.22.0/hooks";

const HIDEABLE_KINDS = new Set([
  "reformat", "lint-fix", "comment-only", "docstring-only", "reorder-imports",
]);

export function ClassicTextView({ diff }) {
  const [layout, setLayout] = useState("unified");   // "unified" | "side-by-side"
  const [hideTrivial, setHideTrivial] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState(0);

  if (!diff) return h("div", { class: "empty" }, "No diff loaded.");
  if (diff.error) return h("div", { class: "error" }, diff.error);

  const ops = diff.operations || [];
  const files = diff.files || [];

  const groups = useMemo(() => {
    const m = new Map();
    ops.forEach((op, i) => {
      if (hideTrivial && HIDEABLE_KINDS.has(op.kind)) return;
      if (!m.has(op.file)) m.set(op.file, []);
      m.get(op.file).push({ ...op, _idx: i });
    });
    return m;
  }, [ops, hideTrivial]);

  const fileOrder = useMemo(() => {
    const order = [];
    const seen = new Set();
    for (const [file, fops] of groups.entries()) {
      const maxRisk = Math.max(...fops.map(o => (o.risk?.score) || 0));
      order.push({ file, ops: fops, maxRisk });
      seen.add(file);
    }
    order.sort((a, b) => b.maxRisk - a.maxRisk || a.file.localeCompare(b.file));
    for (const f of files) {
      const path = f.path_after || f.path_before;
      if (path && !seen.has(path)) order.push({ file: path, ops: [], maxRisk: 0 });
    }
    return order;
  }, [groups, files]);

  const total = ops.length;
  const visible = Array.from(groups.values()).reduce((a, b) => a + b.length, 0);

  return h("div", { class: "classic-layout" },
    h("div", { class: "classic-files-pane" },
      h("div", { class: "classic-controls" },
        h("button", {
          class: `toggle-btn ${layout === "unified" ? "active" : ""}`,
          onClick: () => setLayout("unified"),
        }, "Unified"),
        h("button", {
          class: `toggle-btn ${layout === "side-by-side" ? "active" : ""}`,
          onClick: () => setLayout("side-by-side"),
        }, "Side-by-side"),
        h("label", null,
          h("input", {
            type: "checkbox",
            checked: hideTrivial,
            onChange: (ev) => setHideTrivial(ev.target.checked),
          }),
          "fold reformat / comment-only / import-reorder",
        ),
        h("span", { class: "muted", style: "margin-left:auto" },
          `${visible}/${total} operation${total === 1 ? "" : "s"} shown`,
        ),
      ),
      fileOrder.length === 0 && h("div", { class: "empty" }, "No files in this diff."),
      fileOrder.map((g) => h(ClassicFile, {
        key: g.file,
        file: g.file,
        ops: g.ops,
        layout,
        selectedIdx,
        onSelect: setSelectedIdx,
      })),
    ),
    h(ClassicSidePanel, {
      ops: Array.from(groups.values()).flat(),
      selectedIdx,
      onSelect: setSelectedIdx,
    }),
  );
}

function ClassicFile({ file, ops, layout, selectedIdx, onSelect }) {
  const blocks = useMemo(() => buildBlocks(ops), [ops]);

  return h("div", { class: "classic-file" },
    h("div", { class: "classic-file-head" },
      h("span", null, file),
      h("div", { class: "badges" },
        ops.map(op => h("span", {
          key: op._idx,
          class: `badge kind-${op.kind} ${op._idx === selectedIdx ? "selected" : ""}`,
          title: op.summary,
          onClick: () => onSelect(op._idx),
        }, op.kind)),
      ),
    ),
    ops.length === 0 && h("div", { class: "muted", style: "padding:8px 12px;font-size:11px" },
      "(no operations to show — folded by filter)"),
    layout === "side-by-side"
      ? h(SideBySideDiff, { blocks, selectedIdx, onSelect })
      : h(UnifiedDiff, { blocks, selectedIdx, onSelect }),
  );
}

function buildBlocks(ops) {
  const blocks = [];
  for (const op of ops) {
    const before = (op.before || "").split("\n");
    const after  = (op.after  || "").split("\n");
    blocks.push({
      kind: op.kind,
      summary: op.summary,
      idx: op._idx,
      before: op.before ? before : [],
      after:  op.after  ? after  : [],
    });
  }
  return blocks;
}

function UnifiedDiff({ blocks, selectedIdx, onSelect }) {
  return h("div", { class: "classic-diff" },
    blocks.map((b) => h(Fragment, { key: b.idx },
      h("div", {
        class: `diff-line hunk kind-${b.kind} ${b.idx === selectedIdx ? "selected" : ""}`,
        onClick: () => onSelect(b.idx),
      }, `@@ ${b.kind}: ${b.summary} @@`),
      b.before.map((line, i) => h("div", {
        class: `diff-line del kind-${b.kind}`,
        key: `bef-${b.idx}-${i}`,
        "data-op": b.kind,
        title: `${b.kind}: ${b.summary}`,
        onClick: () => onSelect(b.idx),
      },
        h("span", { class: "gutter" }),
        h("span", { class: "lineno" }, ""),
        h("span", { class: "body" }, line),
      )),
      b.after.map((line, i) => h("div", {
        class: `diff-line add kind-${b.kind}`,
        key: `aft-${b.idx}-${i}`,
        "data-op": b.kind,
        title: `${b.kind}: ${b.summary}`,
        onClick: () => onSelect(b.idx),
      },
        h("span", { class: "gutter" }),
        h("span", { class: "lineno" }, ""),
        h("span", { class: "body" }, line),
      )),
    )),
  );
}

function SideBySideDiff({ blocks, selectedIdx, onSelect }) {
  return h("div", { class: "classic-diff classic-side-by-side" },
    h("div", { class: "classic-pane" },
      blocks.map((b) => h(Fragment, { key: b.idx },
        h("div", {
          class: `diff-line hunk kind-${b.kind} ${b.idx === selectedIdx ? "selected" : ""}`,
          onClick: () => onSelect(b.idx),
        }, `@@ ${b.kind} (before) @@`),
        b.before.length > 0 ? b.before.map((line, i) => h("div", {
          class: `diff-line del kind-${b.kind}`,
          key: `s-bef-${b.idx}-${i}`,
          "data-op": b.kind,
          title: `${b.kind}: ${b.summary}`,
          onClick: () => onSelect(b.idx),
        },
          h("span", { class: "gutter" }),
          h("span", { class: "lineno" }, ""),
          h("span", { class: "body" }, line),
        )) : h("div", { class: "diff-line ctx", key: `bef-empty-${b.idx}` },
          h("span", { class: "gutter" }),
          h("span", { class: "lineno" }, ""),
          h("span", { class: "body", style: "color:var(--fg-muted);font-style:italic" },
            "(no before snippet)"),
        ),
      )),
    ),
    h("div", { class: "classic-pane" },
      blocks.map((b) => h(Fragment, { key: b.idx },
        h("div", {
          class: `diff-line hunk kind-${b.kind} ${b.idx === selectedIdx ? "selected" : ""}`,
          onClick: () => onSelect(b.idx),
        }, `@@ ${b.kind} (after) @@`),
        b.after.length > 0 ? b.after.map((line, i) => h("div", {
          class: `diff-line add kind-${b.kind}`,
          key: `s-aft-${b.idx}-${i}`,
          "data-op": b.kind,
          title: `${b.kind}: ${b.summary}`,
          onClick: () => onSelect(b.idx),
        },
          h("span", { class: "gutter" }),
          h("span", { class: "lineno" }, ""),
          h("span", { class: "body" }, line),
        )) : h("div", { class: "diff-line ctx", key: `aft-empty-${b.idx}` },
          h("span", { class: "gutter" }),
          h("span", { class: "lineno" }, ""),
          h("span", { class: "body", style: "color:var(--fg-muted);font-style:italic" },
            "(no after snippet)"),
        ),
      )),
    ),
  );
}

function ClassicSidePanel({ ops, selectedIdx, onSelect }) {
  return h("div", { class: "classic-side-pane" },
    h("h3", null, "Operations"),
    ops.length === 0 && h("div", { class: "muted", style: "padding:8px" },
      "No operations match the current filter."),
    ops.map((op) => h("div", {
      key: op._idx,
      class: `side-op-row kind-${op.kind} ${op._idx === selectedIdx ? "selected" : ""}`,
      onClick: () => {
        onSelect(op._idx);
        const target = document.querySelector(
          `.diff-line.hunk.kind-${op.kind}`
        );
        if (target) target.scrollIntoView({ block: "center", behavior: "smooth" });
      },
    },
      h("span", { class: "kind" }, op.kind),
      h("span", { class: "summary" }, op.summary),
    )),
  );
}
