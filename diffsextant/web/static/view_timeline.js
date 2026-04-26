// Timeline view (§6.4 of the DiffSextant plan).
//
// Horizontal track of commits. Each commit card shows:
//   - short SHA + subject + author + ISO timestamp
//   - per-kind chips (e.g. 3x rename-symbol, 1x extract-function)
//   - a thin risk bar (max risk score across the commit's ops)
// Clicking a commit jumps the URL hash to #/commit/<sha>, which the App
// router resolves into the Operations view for that commit.

import { h, Fragment } from "https://esm.sh/preact@10.22.0";
import { useState, useMemo } from "https://esm.sh/preact@10.22.0/hooks";

function riskBucketFromScore(s) {
  if (s == null) return "low";
  if (s >= 0.7) return "high";
  if (s >= 0.4) return "medium";
  return "low";
}

export function TimelineView({ timeline, onCommitClick }) {
  const [rangeInput, setRangeInput] = useState(timeline?.range || "HEAD~20..HEAD");
  const [selectedSha, setSelectedSha] = useState(null);

  if (!timeline) return h("div", { class: "empty" }, "Loading timeline...");
  if (timeline.error) return h("div", { class: "error" }, timeline.error);

  const commits = timeline.commits || [];

  const summary = useMemo(() => {
    const kinds = {};
    let totalOps = 0;
    let maxRisk = 0;
    for (const c of commits) {
      totalOps += (c.op_count || 0);
      maxRisk = Math.max(maxRisk, c.max_risk_score || 0);
      for (const [k, v] of Object.entries(c.kind_counts || {})) {
        kinds[k] = (kinds[k] || 0) + v;
      }
    }
    return { totalOps, maxRisk, kinds };
  }, [commits]);

  const selected = commits.find(c => c.sha === selectedSha) || commits[commits.length - 1];

  const apply = () => {
    const v = rangeInput.trim();
    if (!v) location.hash = "#/timeline";
    else location.hash = `#/timeline/${encodeURIComponent(v)}`;
  };

  return h("div", { class: "timeline-layout" },
    h("div", { class: "timeline-controls" },
      h("span", { class: "muted" }, "range:"),
      h("input", {
        type: "text",
        value: rangeInput,
        onInput: (ev) => setRangeInput(ev.target.value),
        onKeyDown: (ev) => { if (ev.key === "Enter") apply(); },
        placeholder: "HEAD~20..HEAD",
      }),
      h("button", { onClick: apply }, "Apply"),
      h("span", { class: "muted", style: "margin-left:auto" },
        `${commits.length} commit${commits.length === 1 ? "" : "s"}` +
        `, ${summary.totalOps} op${summary.totalOps === 1 ? "" : "s"}` +
        `, max risk ${summary.maxRisk.toFixed(2)}`),
    ),
    commits.length === 0
      ? h("div", { class: "empty" }, "No commits in this range.")
      : h("div", { class: "timeline-track" },
          commits.map(c => h(CommitCard, {
            key: c.sha,
            commit: c,
            isSelected: c.sha === (selected && selected.sha),
            onSelect: () => setSelectedSha(c.sha),
            onDrillDown: () => onCommitClick(c.sha),
          })),
        ),
    selected && h(CommitDetail, {
      commit: selected,
      onDrillDown: () => onCommitClick(selected.sha),
    }),
  );
}

function CommitCard({ commit, isSelected, onSelect, onDrillDown }) {
  const bucket = riskBucketFromScore(commit.max_risk_score);
  const widthPct = Math.round(Math.min(1, commit.max_risk_score || 0) * 100);
  return h("div", {
    class: `tl-commit ${isSelected ? "selected" : ""}`,
    onClick: onSelect,
    onDblClick: onDrillDown,
    title: "Click to preview, double-click to drill into this commit",
  },
    h("div", { class: "tl-sha" }, commit.short_sha || (commit.sha || "").slice(0, 8)),
    h("div", { class: "tl-subject", title: commit.subject || "" }, commit.subject || ""),
    h("div", { class: "tl-meta" },
      `${commit.op_count || 0} op${(commit.op_count || 0) === 1 ? "" : "s"}` +
      ` · ${(commit.files_touched || []).length} file${(commit.files_touched || []).length === 1 ? "" : "s"}`),
    h("div", { class: "tl-kinds" },
      Object.entries(commit.kind_counts || {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([k, v]) => h("span", {
          class: `tl-kind kind-${k}`,
          key: k,
          title: `${v} × ${k}`,
        }, `${v}× ${k}`)),
    ),
    h("div", { class: `tl-risk-bar risk-${bucket}` },
      h("span", { style: `width:${widthPct}%` })),
  );
}

function CommitDetail({ commit, onDrillDown }) {
  return h("div", { class: "tl-detail" },
    h("div", { class: "tl-detail-subject" }, commit.subject || "(no subject)"),
    h("div", { class: "tl-detail-meta" },
      `${commit.short_sha} · ${commit.author_name || "?"} · ${commit.timestamp || ""}`,
    ),
    h("button", { class: "toggle-btn", onClick: onDrillDown,
      style: "background:var(--bg-3);color:var(--fg);border:1px solid var(--border);border-radius:4px;padding:3px 10px;cursor:pointer;font-size:11px" },
      "Open Operations view for this commit"),
    Object.keys(commit.kind_counts || {}).length > 0 && h("div", null,
      h("h3", null, "operation breakdown"),
      h("div", { class: "tl-kinds" },
        Object.entries(commit.kind_counts).map(([k, v]) =>
          h("span", { class: `tl-kind kind-${k}`, key: k }, `${v}× ${k}`)),
      ),
    ),
    (commit.files_touched || []).length > 0 && h("div", null,
      h("h3", null, "files touched"),
      h("ul", { class: "tl-detail-files" },
        commit.files_touched.map(f => h("li", { key: f }, f))),
    ),
    (commit.warnings || []).length > 0 && h("div", null,
      h("h3", null, "warnings"),
      h("ul", { class: "tl-detail-files" },
        commit.warnings.map((w, i) => h("li", { key: i, style: "color:var(--warn)" }, w))),
    ),
  );
}
