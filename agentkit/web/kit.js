// Shared front-end helpers: DOM builder, API + event stream, formatters,
// an SVG line chart, the workflow strip and the trace list.

export function h(tag, attrs, ...kids) {
  const svgTags = ["svg", "path", "line", "rect", "circle", "g", "text", "polyline", "polygon", "defs", "clipPath"];
  const el = svgTags.includes(tag)
    ? document.createElementNS("http://www.w3.org/2000/svg", tag)
    : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

export async function api(path, body) {
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

// Follow a run's event stream. Stored events replay first, then live ones.
export function follow(runId, onEvent, onEnd) {
  const src = new EventSource(`/api/runs/${runId}/events`);
  let ended = false;
  src.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    onEvent(ev);
    if (ev.type === "run_end") { ended = true; src.close(); onEnd && onEnd(ev.payload); }
  };
  src.onerror = () => { src.close(); if (!ended) { ended = true; onEnd && onEnd({ status: "closed" }); } };
  return () => src.close();
}

export const fmt = {
  num(v, d = 2) { return v == null || isNaN(v) ? "–" : Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); },
  int(v) { return v == null ? "–" : Math.round(v).toLocaleString("en-US"); },
  pct(v, d = 1) { return v == null || isNaN(v) ? "–" : (v * 100).toFixed(d) + "%"; },
  signed(v, d = 2) { return v == null || isNaN(v) ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d); },
  signedPct(v, d = 1) { return v == null || isNaN(v) ? "–" : (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v * 100).toFixed(d) + "%"; },
  usd(v) {
    if (v == null || isNaN(v)) return "–";
    const a = Math.abs(v), s = v < 0 ? "−" : "";
    if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
    if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
    if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}k`;
    return `${s}$${a.toFixed(a < 10 ? 2 : 0)}`;
  },
  addr(a) { return a ? `${a.slice(0, 6)}…${a.slice(-4)}` : "–"; },
  ms(v) { return v == null ? "" : v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`; },
  ago(ts) {
    const s = Date.now() / 1000 - ts;
    if (s < 90) return "just now";
    if (s < 5400) return `${Math.round(s / 60)} min ago`;
    if (s < 129600) return `${Math.round(s / 3600)} h ago`;
    return `${Math.round(s / 86400)} d ago`;
  },
  clock(ts) { return new Date(ts * 1000).toLocaleTimeString("en-GB", { hour12: false }); },
};

// Line chart. series: [{name, points:[[x,y],...], color, dash, width}],
// bands: [{x0, x1, label, cls}] shaded x-ranges, opts.yFmt formats axis labels.
export function lineChart(el, { series, bands = [], height = 220, yFmt = (v) => fmt.num(v, 2), xFmt = null, zero = null }) {
  const draw = () => {
    el.replaceChildren();
    const W = Math.max(el.clientWidth, 240), H = height, pad = { l: 46, r: 10, t: 10, b: xFmt ? 22 : 8 };
    const pts = series.flatMap((s) => s.points);
    if (!pts.length) { el.append(h("div", { class: "kit-empty" }, "No data yet")); return; }
    let x0 = Math.min(...pts.map((p) => p[0])), x1 = Math.max(...pts.map((p) => p[0]));
    let y0 = Math.min(...pts.map((p) => p[1])), y1 = Math.max(...pts.map((p) => p[1]));
    if (zero != null) { y0 = Math.min(y0, zero); y1 = Math.max(y1, zero); }
    if (x1 === x0) x1 = x0 + 1;
    const span = (y1 - y0) || Math.abs(y1) || 1; y0 -= span * 0.06; y1 += span * 0.06;
    const X = (x) => pad.l + ((x - x0) / (x1 - x0)) * (W - pad.l - pad.r);
    const Y = (y) => pad.t + (1 - (y - y0) / (y1 - y0)) * (H - pad.t - pad.b);
    const svg = h("svg", { class: "kit-chart", width: W, height: H, viewBox: `0 0 ${W} ${H}` });
    for (const b of bands) {
      const bx0 = X(Math.max(b.x0, x0)), bx1 = X(Math.min(b.x1, x1));
      if (bx1 <= bx0) continue;
      svg.append(h("rect", { class: `kit-band ${b.cls || ""}`, x: bx0, y: pad.t, width: bx1 - bx0, height: H - pad.t - pad.b }));
      if (b.label) svg.append(h("text", { class: "kit-band-label", x: bx0 + 6, y: pad.t + 12 }, b.label));
    }
    for (let i = 0; i <= 3; i++) {
      const v = y0 + ((y1 - y0) * i) / 3, y = Y(v);
      svg.append(h("line", { class: "kit-grid", x1: pad.l, x2: W - pad.r, y1: y, y2: y }));
      svg.append(h("text", { class: "kit-axis", x: pad.l - 6, y: y + 3, "text-anchor": "end" }, yFmt(v)));
    }
    if (zero != null) svg.append(h("line", { class: "kit-zero", x1: pad.l, x2: W - pad.r, y1: Y(zero), y2: Y(zero) }));
    if (xFmt) for (let i = 0; i <= 4; i++) {
      const v = x0 + ((x1 - x0) * i) / 4;
      svg.append(h("text", { class: "kit-axis", x: X(v), y: H - 6, "text-anchor": i === 0 ? "start" : i === 4 ? "end" : "middle" }, xFmt(v)));
    }
    for (const s of series) {
      if (!s.points.length) continue;
      const d = s.points.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join("");
      svg.append(h("path", { class: "kit-line", d, stroke: s.color, "stroke-width": s.width || 1.5, "stroke-dasharray": s.dash || null }));
    }
    const cursor = h("line", { class: "kit-cursor", y1: pad.t, y2: H - pad.b, visibility: "hidden" });
    const tip = h("div", { class: "kit-tip", hidden: true });
    svg.append(cursor);
    svg.addEventListener("mousemove", (e) => {
      const r = svg.getBoundingClientRect(), xv = x0 + ((e.clientX - r.left - pad.l) / (W - pad.l - pad.r)) * (x1 - x0);
      const rows = series.filter((s) => s.points.length).map((s) => {
        const p = s.points.reduce((a, b) => (Math.abs(b[0] - xv) < Math.abs(a[0] - xv) ? b : a));
        return { s, p };
      });
      if (!rows.length) return;
      cursor.setAttribute("x1", X(rows[0].p[0])); cursor.setAttribute("x2", X(rows[0].p[0])); cursor.setAttribute("visibility", "visible");
      tip.hidden = false;
      tip.replaceChildren(
        xFmt ? h("div", { class: "kit-tip-x" }, xFmt(rows[0].p[0])) : null,
        ...rows.map(({ s, p }) => h("div", {}, h("i", { style: { background: s.color } }), `${s.name} `, h("b", {}, yFmt(p[1])))));
      tip.style.left = Math.min(e.clientX - r.left + 12, W - 170) + "px";
      tip.style.top = "8px";
    });
    svg.addEventListener("mouseleave", () => { cursor.setAttribute("visibility", "hidden"); tip.hidden = true; });
    el.append(svg, tip);
  };
  el.classList.add("kit-chart-wrap");
  draw();
  if (!el._ro) { el._ro = new ResizeObserver(() => el._draw && el._draw()); el._ro.observe(el); }
  el._draw = draw;
}

// Workflow strip: the agent's state graph, with live node status and visit counts.
export function flowStrip(el, graph, status = {}) {
  const { active = null, visits = {} } = status;
  const routes = {};
  for (const e of graph.edges) if (e.label) (routes[e.from] ||= []).push(e);
  el.classList.add("kit-flow");
  el.replaceChildren(...graph.nodes.map((n, i) => {
    const count = visits[n.id] || 0;
    const state = n.id === active ? "active" : count ? "done" : "idle";
    return h("div", { class: `kit-node ${state}`, "data-kind": n.kind, title: `${n.kind} node` },
      h("span", { class: "kit-node-idx" }, String(i + 1).padStart(2, "0")),
      h("span", { class: "kit-node-label" }, n.label),
      count > 1 ? h("span", { class: "kit-node-count" }, `×${count}`) : null,
      routes[n.id] ? h("span", { class: "kit-node-routes" }, routes[n.id].map((r) =>
        `${r.label} → ${r.to === "__end__" ? "end" : (graph.nodes.find((x) => x.id === r.to) || {}).label || r.to}`).join("  ·  ")) : null);
  }));
}

// Trace list from run events. `describe(ev)` may return extra detail nodes.
export function traceList(el, events, describe = () => null) {
  el.classList.add("kit-trace");
  const rows = [];
  for (const ev of events) {
    const p = ev.payload;
    if (ev.type === "node_end") {
      rows.push(h("div", { class: "kit-trace-row", "data-kind": p.kind },
        h("span", { class: "kit-trace-time" }, fmt.clock(ev.ts)),
        h("span", { class: "kit-trace-node" }, p.label),
        h("span", { class: "kit-trace-note" }, p.note || "", p.route ? h("em", {}, ` → ${p.route}`) : null),
        h("span", { class: "kit-trace-ms" }, fmt.ms(p.ms))));
    } else if (ev.type === "llm") {
      rows.push(h("div", { class: "kit-trace-row sub", "data-kind": "llm" },
        h("span", { class: "kit-trace-time" }, ""),
        h("span", { class: "kit-trace-node" }, p.source === "baseline" ? "baseline policy" : "model call"),
        h("span", { class: "kit-trace-note" }, `${p.tag}`, p.error ? h("em", { class: "bad" }, `  ${p.error}`) : null),
        h("span", { class: "kit-trace-ms" }, fmt.ms(p.ms))));
    } else if (ev.type === "budget") {
      rows.push(h("div", { class: "kit-trace-row warn" }, h("span", { class: "kit-trace-time" }, fmt.clock(ev.ts)),
        h("span", { class: "kit-trace-node" }, "budget"), h("span", { class: "kit-trace-note" }, p.reason), h("span", {})));
    } else if (ev.type === "run_end" && p.status === "error") {
      rows.push(h("div", { class: "kit-trace-row warn" }, h("span", { class: "kit-trace-time" }, fmt.clock(ev.ts)),
        h("span", { class: "kit-trace-node" }, "error"), h("span", { class: "kit-trace-note" }, p.error), h("span", {})));
    } else {
      const extra = describe(ev);
      if (extra) rows.push(extra);
    }
  }
  el.replaceChildren(...(rows.length ? rows : [h("div", { class: "kit-empty" }, "No trace yet")]));
  el.scrollTop = el.scrollHeight;
}

// Fold a run's events into {active, visits} for flowStrip.
export function flowStatus(events) {
  const visits = {}; let active = null;
  for (const ev of events) {
    if (ev.type === "node_start") active = ev.payload.node;
    if (ev.type === "node_end") { visits[ev.payload.node] = (visits[ev.payload.node] || 0) + 1; active = null; }
    if (ev.type === "run_end") active = null;
  }
  return { active, visits };
}
