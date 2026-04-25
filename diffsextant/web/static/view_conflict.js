// view_conflict.js — phase 1D conflict view.
//
// Three-panel classified conflict UI: base / ours / theirs, region-by-
// region. Each region shows kind + risk + suggestions; clicking a
// suggestion sends the chosen resolution body to the server, which
// applies it to the file and re-fetches the parsed picture.
//
// Plug-in contract (designed to play nicely with 1C's app.js router):
//   * exports `ConflictView({ path, onResolved })`
//   * fetches `/api/conflict/<path>` for the parsed + classified picture
//   * POSTs to `/api/conflict/<path>/resolve` with
//     `{ region_index, suggestion_key }` to apply a suggestion
//
// If 1C lands first, app.js can import this file and route to it via
// `?view=conflict&path=…`. If 1D lands first, this file is the only
// view present and renders standalone via `index.html`.

import { h, Fragment } from "https://esm.sh/preact@10.22.0";
import { useState, useEffect, useCallback } from "https://esm.sh/preact@10.22.0/hooks";


export function ConflictView({ path, onResolved }) {
  const [picture, setPicture] = useState(null);
  const [error, setError] = useState(null);
  const [busyKey, setBusyKey] = useState(null);  // "<region_idx>:<sug_key>"

  const fetchPicture = useCallback(async () => {
    setError(null);
    try {
      const url = `/api/conflict/${encodeURIComponent(path)}`;
      const res = await fetch(url);
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status}: ${txt}`);
      }
      const data = await res.json();
      setPicture(data);
    } catch (e) {
      setError(String(e.message || e));
    }
  }, [path]);

  useEffect(() => { fetchPicture(); }, [fetchPicture]);

  const applySuggestion = useCallback(async (regionIndex, suggestionKey) => {
    const tag = `${regionIndex}:${suggestionKey}`;
    setBusyKey(tag);
    try {
      const url = `/api/conflict/${encodeURIComponent(path)}/resolve`;
      const res = await fetch(url, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          region_index: regionIndex,
          suggestion_key: suggestionKey,
        }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status}: ${txt}`);
      }
      const data = await res.json();
      // Re-fetch — file may have shrunk to fewer regions
      await fetchPicture();
      if (onResolved) onResolved(data);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setBusyKey(null);
    }
  }, [path, fetchPicture, onResolved]);

  if (error) {
    return h("div", { class: "conflict-view error" },
      h("h3", null, "Conflict view"),
      h("div", { class: "error-msg" }, error),
      h("button", { onClick: fetchPicture }, "Retry"),
    );
  }
  if (!picture) {
    return h("div", { class: "conflict-view loading" }, "Loading…");
  }
  if (!picture.regions || picture.regions.length === 0) {
    return h("div", { class: "conflict-view empty" },
      h("h3", null, picture.path || path),
      h("div", null, "No conflict regions found in this file."),
      !picture.parse_ok && h("div", { class: "error-msg" },
        `Parse error: ${picture.parse_error}`),
    );
  }

  const prov = picture.provenance || {};

  return h("div", { class: "conflict-view" },
    h("header", { class: "conflict-header" },
      h("h3", null, picture.path || path),
      prov.state && h("div", { class: "muted" },
        `state: ${prov.state}`,
        prov.ours_branch ? ` — ours: ${prov.ours_branch} @ ${(prov.ours_sha || "?").slice(0, 7)}` : "",
        prov.theirs_branch ? ` — theirs: ${prov.theirs_branch} @ ${(prov.theirs_sha || "?").slice(0, 7)}` : "",
      ),
    ),
    picture.regions.map((region, i) => h(ConflictRegion, {
      key: i,
      region,
      provenance: prov,
      busyKey,
      onApply: (suggestionKey) => applySuggestion(region.index, suggestionKey),
    })),
  );
}


function ConflictRegion({ region, provenance, busyKey, onApply }) {
  const risk = (region.risk || "unknown").toUpperCase();
  const kind = (region.kind || "unknown").toUpperCase();

  return h("div", {
    class: `conflict-region risk-${region.risk || "unknown"} kind-${region.kind}`,
  },
    h("div", { class: "conflict-region-head" },
      h("span", { class: "region-num" }, `#${region.index}`),
      h("span", { class: "kind-badge" }, kind),
      h("span", { class: `risk-badge risk-${region.risk}` }, `risk: ${risk}`),
      h("span", { class: "muted" }, `lines ${region.line_start}-${region.line_end}`),
    ),
    region.rationale && h("div", { class: "rationale" }, region.rationale),
    h("div", { class: "panels" },
      region.base !== null && region.base !== undefined && h(Panel, {
        title: "Base",
        subtitle: provenance.base_sha ? `merge-base @ ${provenance.base_sha.slice(0, 7)}` : "merge-base",
        body: region.base,
        cls: "panel-base",
      }),
      h(Panel, {
        title: "Ours",
        subtitle: provenance.ours_branch || region.ours_label || "ours",
        body: region.ours,
        cls: "panel-ours",
      }),
      h(Panel, {
        title: "Theirs",
        subtitle: provenance.theirs_branch || region.theirs_label || "theirs",
        body: region.theirs,
        cls: "panel-theirs",
      }),
    ),
    region.intent_signals && region.intent_signals.length > 0 && h("div", { class: "intent" },
      h("h4", null, "Intent signals"),
      h("ul", null, region.intent_signals.map((sig, i) =>
        h("li", { key: i }, sig)
      )),
    ),
    region.suggestions && region.suggestions.length > 0 && h("div", { class: "suggestions" },
      h("h4", null, "Suggested resolutions"),
      h("div", { class: "suggestion-list" },
        region.suggestions.map((s) => {
          const tag = `${region.index}:${s.key}`;
          const busy = busyKey === tag;
          return h("button", {
            key: s.key,
            class: `suggestion ${s.auto_apply ? "auto" : "manual"}`,
            disabled: busy || !s.auto_apply,
            onClick: () => s.auto_apply && onApply(s.key),
            title: s.detail || s.label,
          },
            h("span", { class: "suggestion-key" }, `[${s.key}]`),
            h("span", { class: "suggestion-label" }, s.label),
            s.detail && h("span", { class: "suggestion-detail" }, s.detail),
            busy && h("span", { class: "spinner" }, "…"),
          );
        }),
      ),
    ),
  );
}


function Panel({ title, subtitle, body, cls }) {
  const text = (body === null || body === undefined) ? "" : body;
  return h("div", { class: `panel ${cls}` },
    h("div", { class: "panel-head" },
      h("strong", null, title),
      h("span", { class: "muted" }, subtitle),
    ),
    h("pre", { class: "panel-body" }, text || h("em", null, "(empty)")),
  );
}


// Default export so app.js can `import('view_conflict.js').then(m => m.default)`.
export default ConflictView;
