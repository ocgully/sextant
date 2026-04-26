/* diffsextant_discuss.js — phase 1E

The "Discuss this diff" toolbar button. Designed as a small, isolated
DOM addition so it can be merged into the 1C view layer without
touching 1C's diff/operations/timeline view files.

Usage from 1C's main bundle:

    import { mountDiscussButton } from "/static/diffsextant_discuss.js";
    mountDiscussButton(document.querySelector("#toolbar"), {
        getRange: () => ({ ref1: state.ref1, ref2: state.ref2 }),
    });

The button POSTs to `/api/discuss`, which the server wires to
`diffsextant.llm.discuss.discuss`. The response includes the bundle
path; we render a small toast linking to it (so the user can `cd`
there or open it from their editor).
*/

const STYLE_ID = "diffsextant-discuss-style";

function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = `
        .diffsextant-discuss-btn {
            cursor: pointer;
            padding: 4px 10px;
            border: 1px solid currentColor;
            border-radius: 4px;
            background: transparent;
            font: inherit;
        }
        .diffsextant-discuss-btn:disabled { opacity: 0.5; cursor: wait; }
        .diffsextant-discuss-toast {
            position: fixed;
            right: 16px;
            bottom: 16px;
            max-width: 480px;
            padding: 10px 14px;
            border: 1px solid currentColor;
            border-radius: 6px;
            background: var(--bg, #fff);
            font: 13px/1.4 sans-serif;
            box-shadow: 0 2px 6px rgba(0,0,0,0.15);
            z-index: 9999;
        }
        .diffsextant-discuss-toast code { word-break: break-all; }
        .diffsextant-discuss-toast .close {
            float: right; cursor: pointer;
            margin-left: 8px;
        }
    `;
    document.head.appendChild(s);
}

function showToast(message, opts = {}) {
    const node = document.createElement("div");
    node.className = "diffsextant-discuss-toast";
    node.innerHTML = message;
    const close = document.createElement("span");
    close.className = "close";
    close.textContent = "x";
    close.addEventListener("click", () => node.remove());
    node.appendChild(close);
    document.body.appendChild(node);
    if (!opts.persistent) {
        setTimeout(() => node.remove(), 8000);
    }
}

/**
 * Mount a "Discuss this diff" button into the given container.
 *
 * @param {HTMLElement} container - target element (typically the toolbar)
 * @param {object} opts
 * @param {() => {ref1:string, ref2:string, agent?:string}} opts.getRange
 *   Callback that returns the current diff range. Mandatory.
 * @param {string} [opts.label]   - button text (default "Discuss this diff")
 * @param {string} [opts.endpoint] - override `/api/discuss` for tests
 */
export function mountDiscussButton(container, opts = {}) {
    if (!container) {
        console.warn("[diffsextant-discuss] no container provided");
        return null;
    }
    if (typeof opts.getRange !== "function") {
        console.warn("[diffsextant-discuss] getRange callback is required");
        return null;
    }
    injectStyle();

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "diffsextant-discuss-btn";
    btn.textContent = opts.label || "Discuss this diff";
    btn.title =
        "Build a DiffSextant conversation bundle and trigger the user's agent runner. " +
        "Equivalent to `diffsextant discuss <ref1> <ref2>`.";

    btn.addEventListener("click", async () => {
        const range = opts.getRange();
        if (!range || !range.ref1 || !range.ref2) {
            showToast("No diff range selected.");
            return;
        }
        btn.disabled = true;
        const original = btn.textContent;
        btn.textContent = "Building bundle...";
        try {
            const endpoint = opts.endpoint || "/api/discuss";
            const resp = await fetch(endpoint, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ref1: range.ref1,
                    ref2: range.ref2,
                    agent: range.agent || null,
                }),
            });
            if (!resp.ok) {
                const text = await resp.text();
                showToast(`Discuss failed: ${resp.status} ${text}`,
                          { persistent: true });
                return;
            }
            const payload = await resp.json();
            const bundleDir = payload.bundle && payload.bundle.bundle_dir;
            const runner = (payload.runner && payload.runner.runner) || "(none)";
            showToast(
                `Bundle ready at <code>${bundleDir || "?"}</code><br>` +
                `Runner: ${runner}`,
                { persistent: true }
            );
        } catch (e) {
            showToast(`Discuss request errored: ${e}`, { persistent: true });
        } finally {
            btn.disabled = false;
            btn.textContent = original;
        }
    });

    container.appendChild(btn);
    return btn;
}

// Convenience: auto-mount when a `[data-diffsextant-toolbar]` element is
// present and `window.__diffsextantState` exposes a getRange function.
// This lets minimal HTML pages wire the button without ESM. The legacy
// `[data-sextant-toolbar]` selector and `window.__sextantState` are still
// honoured for one cycle so pages built before the rename keep working.
if (typeof window !== "undefined") {
    document.addEventListener("DOMContentLoaded", () => {
        const tb =
            document.querySelector("[data-diffsextant-toolbar]") ||
            document.querySelector("[data-sextant-toolbar]");
        const state = window.__diffsextantState || window.__sextantState;
        if (tb && state && typeof state.getRange === "function") {
            mountDiscussButton(tb, { getRange: state.getRange });
        }
    });
}
