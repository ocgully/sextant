// Sextant web UI — Preact + esm.sh, zero build.
//
// Three views share one diff payload (fetched once per range and reused):
//   - Operations  (default)        #/  or #/commit/<sha>
//   - Classic-text                  #/classic  or #/classic/commit/<sha>
//   - Timeline                      #/timeline  or #/timeline/<a..b>
//
// All state lives in URL hash so deep-links + reloads are stable.

import { h, render, Fragment } from "https://esm.sh/preact@10.22.0";
import { useState, useEffect, useMemo, useCallback } from "https://esm.sh/preact@10.22.0/hooks";

import { OperationsView } from "/static/view_operations.js";
import { ClassicTextView } from "/static/view_classic.js";
import { TimelineView } from "/static/view_timeline.js";

// ---------------------------------------------------------------------------
// Hash router
// ---------------------------------------------------------------------------
//
// Routes:
//   #/                         -> ops view, current diff (HEAD~1..HEAD)
//   #/commit/<sha>             -> ops view, single commit
//   #/range/<a>..<b>           -> ops view, custom range
//   #/classic                  -> classic-text view, current diff
//   #/classic/commit/<sha>     -> classic-text view, single commit
//   #/classic/range/<a>..<b>   -> classic-text view, custom range
//   #/timeline                 -> timeline (defaults to last 20 commits on HEAD)
//   #/timeline/<a>..<b>        -> timeline for explicit range

function parseHash(hash) {
  const raw = (hash || "").replace(/^#/, "") || "/";
  const segs = raw.split("/").filter(Boolean);
  let mode = "ops";
  let rest = segs.slice();
  if (segs[0] === "classic") { mode = "classic"; rest = segs.slice(1); }
  else if (segs[0] === "timeline") { mode = "timeline"; rest = segs.slice(1); }

  if (rest.length === 0) return { mode, kind: "current" };
  if (rest[0] === "commit" && rest[1]) {
    return { mode, kind: "commit", sha: decodeURIComponent(rest[1]) };
  }
  if (rest[0] === "range" && rest[1]) {
    return { mode, kind: "range", range: decodeURIComponent(rest[1]) };
  }
  if (mode === "timeline" && rest[0]) {
    return { mode, kind: "range", range: decodeURIComponent(rest[0]) };
  }
  return { mode, kind: "current" };
}

function setHashMode(currentRoute, newMode) {
  const tail = (() => {
    if (currentRoute.kind === "commit") return `/commit/${encodeURIComponent(currentRoute.sha)}`;
    if (currentRoute.kind === "range") return `/range/${encodeURIComponent(currentRoute.range)}`;
    return "/";
  })();
  if (newMode === "timeline") {
    if (currentRoute.kind === "range") {
      location.hash = `#/timeline/${encodeURIComponent(currentRoute.range)}`;
    } else {
      location.hash = "#/timeline";
    }
    return;
  }
  location.hash = newMode === "ops" ? `#${tail}` : `#/${newMode}${tail === "/" ? "" : tail}`;
}

function useRoute() {
  const [route, setRoute] = useState(() => parseHash(location.hash));
  useEffect(() => {
    const onChange = () => setRoute(parseHash(location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

// ---------------------------------------------------------------------------
// Diff fetch — one fetch per (kind,sha,range) tuple. Cached on the App.
// ---------------------------------------------------------------------------

async function fetchDiff(route) {
  if (route.kind === "current") {
    const r = await fetch("/api/diff/current");
    if (!r.ok) throw new Error(`/api/diff/current -> ${r.status}`);
    return await r.json();
  }
  if (route.kind === "commit") {
    const r = await fetch(`/api/explain?commit=${encodeURIComponent(route.sha)}`);
    if (!r.ok) throw new Error(`/api/explain -> ${r.status}`);
    return await r.json();
  }
  if (route.kind === "range") {
    const [a, b] = route.range.split("..");
    if (!a || !b) throw new Error(`bad range: ${route.range}`);
    const r = await fetch(
      `/api/diff?ref1=${encodeURIComponent(a)}&ref2=${encodeURIComponent(b)}`
    );
    if (!r.ok) throw new Error(`/api/diff -> ${r.status}`);
    return await r.json();
  }
  throw new Error(`unknown route kind: ${route.kind}`);
}

async function fetchTimeline(rangeOrEmpty) {
  const range = rangeOrEmpty || "HEAD~20..HEAD";
  const r = await fetch(`/api/timeline?range=${encodeURIComponent(range)}`);
  if (!r.ok) throw new Error(`/api/timeline -> ${r.status}`);
  return await r.json();
}

async function fetchMeta() {
  const r = await fetch("/api/meta");
  if (!r.ok) throw new Error(`/api/meta -> ${r.status}`);
  return await r.json();
}

// ---------------------------------------------------------------------------
// Root
// ---------------------------------------------------------------------------

function App() {
  const route = useRoute();
  const [diff, setDiff] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [meta, setMeta] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    fetchMeta().then(setMeta).catch(() => {});
  }, []);

  useEffect(() => {
    const tabs = document.querySelectorAll("nav.tabs .tab");
    tabs.forEach(t => {
      const m = t.getAttribute("data-mode");
      t.classList.toggle("active", m === route.mode);
    });
  }, [route.mode]);

  useEffect(() => {
    const b = document.getElementById("refresh");
    if (!b) return;
    const onClick = () => setRefreshTick(x => x + 1);
    b.addEventListener("click", onClick);
    return () => b.removeEventListener("click", onClick);
  }, []);

  useEffect(() => {
    if (!meta) return;
    const root = document.getElementById("project-root");
    if (root && meta.project_root) {
      const parts = meta.project_root.replaceAll("\\", "/").split("/").filter(Boolean);
      root.textContent = parts.slice(-2).join("/");
      root.title = meta.project_root;
    }
    const v = document.getElementById("sextant-version");
    if (v && meta.sextant_version) v.textContent = "v" + meta.sextant_version;
  }, [meta]);

  useEffect(() => {
    const el = document.getElementById("range-label");
    if (!el) return;
    if (route.mode === "timeline") {
      el.textContent = route.kind === "range" ? route.range : "HEAD~20..HEAD";
    } else if (route.kind === "commit") {
      el.textContent = route.sha.slice(0, 8);
    } else if (route.kind === "range") {
      el.textContent = route.range;
    } else {
      el.textContent = "HEAD~1..HEAD";
    }
  }, [route]);

  useEffect(() => {
    if (route.mode === "timeline") return;
    setLoading(true); setError(null);
    fetchDiff(route)
      .then((d) => { setDiff(d); setLoading(false); })
      .catch((e) => { setError(String(e)); setLoading(false); });
  }, [route.mode, route.kind, route.sha, route.range, refreshTick]);

  useEffect(() => {
    if (route.mode !== "timeline") return;
    setLoading(true); setError(null);
    fetchTimeline(route.kind === "range" ? route.range : "")
      .then((t) => { setTimeline(t); setLoading(false); })
      .catch((e) => { setError(String(e)); setLoading(false); });
  }, [route.mode, route.kind, route.range, refreshTick]);

  useEffect(() => {
    const tabs = document.querySelectorAll("nav.tabs .tab");
    const onClick = (ev) => {
      ev.preventDefault();
      const m = ev.currentTarget.getAttribute("data-mode");
      setHashMode(route, m);
    };
    tabs.forEach(t => t.addEventListener("click", onClick));
    return () => tabs.forEach(t => t.removeEventListener("click", onClick));
  }, [route]);

  if (error) {
    return h("div", { class: "error" },
      "Error: ", error,
      h("div", { style: "margin-top:6px;font-size:11px;color:var(--fg-muted)" },
        "(check that the working directory is a git repo with at least 2 commits)"));
  }

  if (loading && !diff && !timeline) {
    return h("div", { class: "empty" }, "Loading...");
  }

  if (route.mode === "timeline") {
    return h(TimelineView, {
      timeline,
      onCommitClick: (sha) => { location.hash = `#/commit/${encodeURIComponent(sha)}`; },
    });
  }
  if (route.mode === "classic") {
    return h(ClassicTextView, { diff });
  }
  return h(OperationsView, { diff });
}

render(h(App, null), document.getElementById("app"));
