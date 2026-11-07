"use strict";
(() => {
  const $ = (id) => document.getElementById(id),
    C = {
      a: "#87d9cb",
      b: "#e9987d",
      gold: "#e2ce86",
      violet: "#baa2e6",
      muted: "#7e8877",
    };
  let state = null,
    position = [-0.3, -0.3],
    tool = "query",
    selectedId = null,
    queue = Promise.resolve(),
    pollTimer = null,
    cycleActive = false,
    fieldBounds = null,
    hoverId = null,
    events = [],
    previousHash = null,
    projection = "layers",
    projectedNodes = [];
  const actions = { right: [1, 0], left: [-1, 0], up: [0, -1], down: [0, 1] };
  function error(e) {
    $("error").hidden = false;
    $("error").textContent = e.message || String(e);
  }
  function api(path, body) {
    const result = queue
      .catch(() => {})
      .then(async () => {
        const ctrl = new AbortController(),
          timeout = setTimeout(() => ctrl.abort(), 30000);
        try {
          const r = await fetch(path, {
            method: body === undefined ? "GET" : "POST",
            headers: { "Content-Type": "application/json" },
            body: body === undefined ? undefined : JSON.stringify(body),
            signal: ctrl.signal,
          });
          const v = await r.json();
          if (!r.ok)
            throw new Error(
              typeof v.error === "string"
                ? v.error
                : v.error?.message || "Operation failed",
            );
          $("connection").className = "good";
          $("connection").querySelector("span").textContent =
            "Connected · persistent memory";
          $("error").hidden = true;
          if (body !== undefined)
            events.push({ path, body, revision: v.revision, tick: v.tick });
          if (v.schema === "somna-live-v1") accept(v);
          return v;
        } finally {
          clearTimeout(timeout);
        }
      });
    queue = result;
    return result;
  }
  function safe(p) {
    p.catch((e) => {
      cycleActive = false;
      error(e);
    });
  }
  function context() {
    return $("context").value === "" ? null : Number($("context").value);
  }
  function cue() {
    return {
      position: position.slice(),
      mask: [$("know-x").checked, $("know-y").checked],
      context: context(),
      action: actions[$("action").value] || null,
      audit: $("audit").checked,
    };
  }
  function accept(v) {
    state = v;
    const a = v.archive,
      m = v.model,
      s = v.sleep,
      busy = !!s.busy;
    $("total").textContent = a.total.toLocaleString();
    $("hot").textContent = a.hot + " / " + a.capacity;
    $("cold").textContent = a.cold.toLocaleString();
    $("updates").textContent = m.trained_steps.toLocaleString();
    $("tick").textContent = v.tick.toLocaleString();
    $("loss-value").textContent = Number.isFinite(m.loss)
      ? m.loss.toFixed(5)
      : "—";
    $("selected-count").textContent = v.query
      ? v.query.selected_ids.length
      : "—";
    $("cold-work").textContent = v.work.cold_rows.toLocaleString();
    $("sleep-count").textContent =
      (s.trace?.length || 0) + " / " + (s.steps || 0) + " actual updates";
    $("sleep-progress-bar").style.width =
      (s.steps ? (100 * (s.trace?.length || 0)) / s.steps : 0) + "%";
    $("learning-status").textContent = busy
      ? "Learning from retrieved observations"
      : m.trained_steps
        ? "Model weights persisted"
        : "The model has not been updated.";
    $("checkpoint").textContent =
      "Checkpoint " +
      m.checkpoint_hash.slice(0, 16) +
      (s.initial_checkpoint_hash
        ? " · before " + s.initial_checkpoint_hash.slice(0, 16)
        : "") +
      ".";
    $("persistence").textContent =
      "Archive " +
      a.checksum.slice(0, 16) +
      " · " +
      a.total +
      " original versions retained. Active membership, recovery cursor and model weights are also persisted.";
    $("phase").textContent = busy
      ? "Offline update " + (s.trace?.length || 0) + " / " + s.steps
      : cycleActive
        ? "Memory cycle in progress"
        : v.query
          ? "Recall complete · evidence shown"
          : "Ready to explore";
    $("phase").parentElement.classList.toggle("busy", busy || cycleActive);
    for (const id of [
      "collect",
      "fade",
      "sleep",
      "sleep-secondary",
      "reset",
      "query-now",
      "restore",
      "correct",
      "rare-query",
      "partial-query",
    ])
      $(id).disabled = busy;
    $("cycle").disabled = busy || cycleActive;
    if (s.status === "error" && s.error) error(new Error(s.error));
    if (previousHash && previousHash !== m.checkpoint_hash)
      $("learning-status").textContent = busy
        ? "Weights changing from observed replay"
        : "Updated parameters saved to a durable checkpoint";
    previousHash = m.checkpoint_hash;
    if (m.invalidated_by_correction && !busy)
      $("learning-status").textContent =
        "A correction invalidated the previous model. Learn again from current evidence.";
    const readPosition = v.query?.cue.position || position;
    $("query-position").textContent =
      (v.query?.purpose === "observed-replay-training"
        ? "Replay cue ("
        : "Cue (") +
      readPosition.map((x) => x.toFixed(2)).join(", ") +
      ")";
    renderQueryMetrics();
    renderRecord();
    draw();
    if (busy) schedulePoll();
  }
  function schedulePoll() {
    clearTimeout(pollTimer);
    pollTimer = setTimeout(() => safe(api("/api/state")), 250);
  }
  function canvas(id) {
    const el = $(id),
      r = el.getBoundingClientRect(),
      dpr = Math.min(devicePixelRatio || 1, 2);
    if (
      el.width !== Math.round(r.width * dpr) ||
      el.height !== Math.round(r.height * dpr)
    ) {
      el.width = Math.round(r.width * dpr);
      el.height = Math.round(r.height * dpr);
    }
    const ctx = el.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);
    return { ctx, w: r.width, h: r.height };
  }
  function text(ctx, t, x, y, color = C.muted, size = 12) {
    ctx.fillStyle = color;
    ctx.font = size + "px Geist,sans-serif";
    ctx.fillText(t, x, y);
  }
  function arrow(ctx, x, y, nx, ny, color, alpha = 1) {
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.globalAlpha = alpha;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(nx, ny);
    ctx.stroke();
    const a = Math.atan2(ny - y, nx - x);
    ctx.beginPath();
    ctx.moveTo(nx, ny);
    ctx.lineTo(nx - 4 * Math.cos(a - 0.5), ny - 4 * Math.sin(a - 0.5));
    ctx.lineTo(nx - 4 * Math.cos(a + 0.5), ny - 4 * Math.sin(a + 0.5));
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;
  }
  function drawLayers() {
    const { ctx, w, h } = canvas("experience");
    if (!state) return;
    const scale = Math.min(w * 0.75, h * 0.94),
      cx = w / 2,
      cy = h * 0.69;
    fieldBounds = { scale, cx, cy };
    projectedNodes = [];
    const project = (x, y, c, z = 0) => ({
      x: cx + (x - y) * scale * 0.28,
      y: cy + (x + y) * scale * 0.13 - c * scale * 0.3 - z * scale,
    });
    for (const c of [1, 0]) {
      ctx.strokeStyle = c === 0 ? "#29413b" : "#4b332b";
      ctx.lineWidth = 1;
      for (let j = 0; j <= 6; j++) {
        const p = -1 + j / 3,
          a = project(p, -1, c),
          b = project(p, 1, c),
          d = project(-1, p, c),
          e = project(1, p, c);
        ctx.globalAlpha = j === 0 || j === 6 ? 0.8 : 0.32;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.moveTo(d.x, d.y);
        ctx.lineTo(e.x, e.y);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;
      const labelAt = project(-1, 1, c);
      text(
        ctx,
        c === 0 ? "WORLD A" : "WORLD B / RARE",
        labelAt.x - 4,
        labelAt.y + 20,
        c === 0 ? C.a : C.b,
      );
    }
    const q = state.query,
      selected = new Set(q?.selected_ids || []),
      weights = new Map((q?.ranked || []).map((r) => [r.id, r.weight]));
    const query = q?.cue || cue(),
      qc = query.context ?? 0,
      qp = project(query.position[0], query.position[1], qc, 0.03);
    // The span marks an omitted coordinate, not an uncertainty estimate.
    if (query.mask.some(Boolean) && !query.mask.every(Boolean)) {
      for (const c of query.context === null ? [1, 0] : [qc]) {
        const a = query.mask[0]
            ? project(query.position[0], -1, c)
            : project(-1, query.position[1], c),
          b = query.mask[0]
            ? project(query.position[0], 1, c)
            : project(1, query.position[1], c);
        ctx.strokeStyle = C.gold;
        ctx.setLineDash([4, 5]);
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }
    const nodes = state.nodes
      .slice()
      .sort((a, b) => b.context - a.context || a.x + a.y - b.x - b.y);
    for (const n of nodes) {
      const floor = project(n.x, n.y, n.context),
        p = project(n.x, n.y, n.context, 0.03 * Math.min(2, n.salience)),
        next = project(
          n.next_x,
          n.next_y,
          n.context,
          0.03 * Math.min(2, n.salience),
        );
      projectedNodes.push({ id: n.id, x: p.x, y: p.y });
      if (!n.current) {
        ctx.strokeStyle = "#545349";
        ctx.beginPath();
        ctx.moveTo(p.x - 2, p.y - 2);
        ctx.lineTo(p.x + 2, p.y + 2);
        ctx.moveTo(p.x - 2, p.y + 2);
        ctx.lineTo(p.x + 2, p.y - 2);
        ctx.stroke();
        continue;
      }
      const color = selected.has(n.id) ? C.gold : n.context === 0 ? C.a : C.b;
      ctx.strokeStyle = color;
      ctx.globalAlpha = n.hot ? 0.18 : 0.04;
      ctx.beginPath();
      ctx.moveTo(floor.x, floor.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      ctx.globalAlpha = 1;
      arrow(
        ctx,
        p.x,
        p.y,
        next.x,
        next.y,
        color,
        selected.has(n.id) ? 0.7 : n.hot ? 0.45 : 0.13,
      );
      ctx.globalAlpha = selected.has(n.id) ? 1 : n.hot ? 0.95 : 0.35;
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = n.hot ? 5 : 0;
      ctx.fillRect(
        p.x - 2,
        p.y - 2,
        selected.has(n.id) ? 5 : 3,
        selected.has(n.id) ? 5 : 3,
      );
      ctx.shadowBlur = 0;
      ctx.globalAlpha = 1;
      if (selected.has(n.id)) {
        ctx.strokeStyle = C.gold;
        ctx.globalAlpha = 0.12 + Math.min(0.5, (weights.get(n.id) || 0) * 2);
        ctx.beginPath();
        ctx.moveTo(qp.x, qp.y);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
        ctx.globalAlpha = 1;
      }
      if (n.id === selectedId || n.id === hoverId) {
        ctx.strokeStyle = "#fff";
        ctx.strokeRect(p.x - 6, p.y - 6, 12, 12);
      }
    }
    ctx.strokeStyle = "#eae9df";
    ctx.beginPath();
    ctx.arc(qp.x, qp.y, 8, 0, Math.PI * 2);
    ctx.moveTo(qp.x - 13, qp.y);
    ctx.lineTo(qp.x + 13, qp.y);
    ctx.moveTo(qp.x, qp.y - 13);
    ctx.lineTo(qp.x, qp.y + 13);
    ctx.stroke();
    if (q?.prediction) {
      const next = project(
        query.position[0] + q.prediction[0],
        query.position[1] + q.prediction[1],
        qc,
        0.03,
      );
      arrow(ctx, qp.x, qp.y, next.x, next.y, "#fff");
    }
    text(
      ctx,
      query.mask.every(Boolean) ? "SPATIAL CUE" : "PARTIAL CUE",
      qp.x + 16,
      qp.y - 8,
      "#eee9d6",
    );
    text(ctx, "CONTEXT PLANES · HEIGHT = ACTIVE SALIENCE", 24, 20);
    text(
      ctx,
      w < 480
        ? "Points: observations · Gold: selected evidence"
        : "Each point is one observed transition. Gold lines are the current read.",
      24,
      h - 12,
    );
  }
  function drawExperience() {
    if (projection === "layers") {
      drawLayers();
      return;
    }
    const { ctx, w, h } = canvas("experience");
    if (!state) return;
    const side = Math.min(w - 64, h - 48),
      x0 = (w - side) / 2,
      y0 = (h - side) / 2;
    fieldBounds = { x: x0, y: y0, side };
    const X = (x) => x0 + ((x + 1) / 2) * side,
      Y = (y) => y0 + ((y + 1) / 2) * side;
    ctx.strokeStyle = "#242a23";
    ctx.lineWidth = 1;
    for (let j = 0; j <= 8; j++) {
      const p = (j / 8) * side;
      ctx.beginPath();
      ctx.moveTo(x0 + p, y0);
      ctx.lineTo(x0 + p, y0 + side);
      ctx.moveTo(x0, y0 + p);
      ctx.lineTo(x0 + side, y0 + p);
      ctx.stroke();
    }
    text(ctx, "−1", x0 - 16, y0 + side + 16);
    text(ctx, "+1", x0 + side - 12, y0 + side + 16);
    text(ctx, "POSITION / OBSERVED TRANSITIONS", x0, y0 - 12);
    const q = state.query,
      read = new Set(q?.selected_ids || []),
      rank = new Map((q?.ranked || []).map((r) => [r.id, r.weight])),
      mask = q?.cue.mask || [$("know-x").checked, $("know-y").checked],
      readPosition = q?.cue.position || position;
    if (!mask[0] && mask[1]) {
      ctx.fillStyle = "rgba(226,206,134,.05)";
      ctx.fillRect(x0, Y(readPosition[1]) - 0.07 * side, side, 0.14 * side);
    }
    if (mask[0] && !mask[1]) {
      ctx.fillStyle = "rgba(226,206,134,.05)";
      ctx.fillRect(X(readPosition[0]) - 0.07 * side, y0, 0.14 * side, side);
    }
    for (const n of state.nodes) {
      const x = X(n.x),
        y = Y(n.y),
        color = n.context === 0 ? C.a : C.b;
      if (!n.current) {
        ctx.strokeStyle = "#41423c";
        ctx.beginPath();
        ctx.moveTo(x - 2, y - 2);
        ctx.lineTo(x + 2, y + 2);
        ctx.moveTo(x - 2, y + 2);
        ctx.lineTo(x + 2, y - 2);
        ctx.stroke();
        continue;
      }
      arrow(
        ctx,
        x,
        y,
        X(n.next_x),
        Y(n.next_y),
        read.has(n.id) ? C.gold : color,
        read.has(n.id) ? 0.7 : n.hot ? 0.32 : 0.09,
      );
      ctx.globalAlpha = n.hot ? Math.min(1, 0.45 + n.salience * 0.05) : 0.2;
      ctx.fillStyle = read.has(n.id) ? C.gold : n.hot ? color : "#7d8275";
      ctx.fillRect(x - 2, y - 2, 4, 4);
      ctx.globalAlpha = 1;
      if (read.has(n.id)) {
        ctx.strokeStyle = C.gold;
        ctx.beginPath();
        ctx.arc(x, y, 4 + Math.sqrt(rank.get(n.id) || 0) * 16, 0, Math.PI * 2);
        ctx.stroke();
      }
      if (n.id === selectedId || n.id === hoverId) {
        ctx.strokeStyle = "#fff";
        ctx.strokeRect(x - 6, y - 6, 12, 12);
      }
    }
    const qx = X(readPosition[0]),
      qy = Y(readPosition[1]);
    ctx.strokeStyle = "#eeeade";
    ctx.beginPath();
    ctx.arc(qx, qy, 8, 0, Math.PI * 2);
    ctx.moveTo(qx - 14, qy);
    ctx.lineTo(qx + 14, qy);
    ctx.moveTo(qx, qy - 14);
    ctx.lineTo(qx, qy + 14);
    ctx.stroke();
    if (q?.prediction) {
      const p = q.cue.position;
      arrow(
        ctx,
        X(p[0]),
        Y(p[1]),
        X(p[0] + q.prediction[0]),
        Y(p[1] + q.prediction[1]),
        "#fff",
      );
    }
    const last = state.sleep.trace?.at(-1);
    if (state.sleep.busy && last) {
      const ids = new Set(last.sources);
      for (const n of state.nodes)
        if (ids.has(n.id)) {
          ctx.strokeStyle = C.violet;
          ctx.strokeRect(X(n.x) - 5, Y(n.y) - 5, 10, 10);
        }
    }
  }
  function drawTree() {
    const { ctx, w, h } = canvas("tree");
    if (!state) return;
    const q = state.query;
    if (!q) {
      text(ctx, "Query the field to reveal selected branches.", 24, h / 2);
      $("routing-detail").textContent =
        "No current read. Query the field to inspect evidence.";
      return;
    }
    if (q.cold_route) {
      drawDualTree(ctx, w, h, q);
      return;
    }
    const levels = q.route.slice().sort((a, b) => b.level - a.level),
      left = 56,
      right = w - 24;
    levels.forEach((level, j) => {
      const y = 28 + j * 58,
        ids = level.candidates,
        sel = new Set(level.selected),
        cell = Math.min(20, (right - left) / Math.max(ids.length, 1));
      text(ctx, "L" + level.level, 24, y + 10);
      ids.forEach((id, k) => {
        ctx.fillStyle = sel.has(id) ? C.gold : "#373f34";
        ctx.fillRect(left + k * cell, y, Math.max(2, cell - 4), 10);
      });
      text(
        ctx,
        ids.length + " scored / " + sel.size + " expanded",
        left,
        y + 30,
      );
    });
    const bank = q.index_ids || [],
      sel = new Set(q.selected_ids),
      y = Math.max(144, levels.length * 58 + 24),
      cols = Math.max(8, Math.floor((right - 24) / 9));
    for (let j = 0; j < bank.length; j++) {
      ctx.fillStyle = sel.has(bank[j]) ? C.gold : "#333b31";
      ctx.fillRect(24 + (j % cols) * 9, y + Math.floor(j / cols) * 10, 5, 5);
    }
    $("routing-detail").textContent =
      q.selected_ids.length +
      " entries read from " +
      bank.length +
      " indexed observations. " +
      q.work.summary_dot_products +
      " summary dot products; " +
      q.work.cold_rows +
      " cold rows examined.";
  }
  function drawDualTree(ctx, w, h, q) {
    const halves = [
      {
        label: "DORMANT ARCHIVE",
        route: q.cold_route,
        ids: q.cold_index_ids || [],
        selected: q.cold_selected_ids || [],
        x: 16,
        color: C.violet,
      },
      {
        label: "FINAL READ BANK",
        route: q.route,
        ids: q.index_ids || [],
        selected: q.selected_ids,
        x: w / 2 + 8,
        color: C.gold,
      },
    ];
    for (const part of halves) {
      const width = w / 2 - 32;
      text(ctx, part.label, part.x, 16, part.color);
      const levels = part.route.slice().sort((a, b) => b.level - a.level);
      levels.forEach((level, j) => {
        const y = 40 + j * 52,
          selected = new Set(level.selected),
          cell = Math.min(
            12,
            (width - 24) / Math.max(1, level.candidates.length),
          );
        text(ctx, "L" + level.level, part.x, y + 9);
        level.candidates.forEach((id, k) => {
          ctx.fillStyle = selected.has(id) ? part.color : "#373d33";
          ctx.fillRect(part.x + 24 + k * cell, y, Math.max(1, cell - 2), 8);
        });
        text(
          ctx,
          level.candidates.length + " scored / " + selected.size + " kept",
          part.x,
          y + 28,
          C.muted,
          12,
        );
      });
      const selected = new Set(part.selected),
        y = Math.max(152, levels.length * 52 + 36),
        spacing = Math.max(
          1,
          Math.min(
            7,
            Math.floor(
              Math.sqrt(
                (width * Math.max(1, h - y - 8)) / Math.max(1, part.ids.length),
              ),
            ),
          ),
        ),
        cols = Math.max(8, Math.floor(width / spacing));
      for (let i = 0; i < part.ids.length; i++) {
        ctx.fillStyle = selected.has(part.ids[i]) ? part.color : "#333a31";
        ctx.fillRect(
          part.x + (i % cols) * spacing,
          y + Math.floor(i / cols) * spacing,
          Math.max(1, spacing - 2),
          Math.max(1, spacing - 2),
        );
      }
    }
    $("routing-detail").textContent =
      (q.cold_selected_ids || []).length +
      " candidates from the dormant hierarchy → " +
      q.selected_ids.length +
      " original entries in the final read. Working-set and cold-index scoring are charged separately.";
  }
  function drawImagination() {
    const { ctx, w, h } = canvas("imagination");
    if (!state) return;
    const side = Math.min(w - 64, h - 40),
      x0 = (w - side) / 2,
      y0 = (h - side) / 2,
      X = (x) => x0 + ((x + 1) / 2) * side,
      Y = (y) => y0 + ((y + 1) / 2) * side;
    ctx.strokeStyle = "#252b24";
    ctx.strokeRect(x0, y0, side, side);
    const contextId = state.sleep.context ?? 0;
    for (const n of state.nodes)
      if (n.current && n.context === contextId)
        arrow(
          ctx,
          X(n.x),
          Y(n.y),
          X(n.next_x),
          Y(n.next_y),
          contextId === 0 ? C.a : C.b,
          0.08,
        );
    const points = state.sleep.rollout || [];
    // Fixed target of the controlled task in MemoryEngine.rollout.
    const goal = [0.72, 0.72];
    ctx.strokeStyle = "#e8e3d2";
    ctx.beginPath();
    ctx.arc(X(goal[0]), Y(goal[1]), 5, 0, Math.PI * 2);
    ctx.stroke();
    text(ctx, "Fixed goal (+0.72, +0.72)", 24, 16, C.muted);
    for (let i = 1; i < points.length; i++) {
      const a = points[i - 1],
        b = points[i];
      ctx.setLineDash([4, 4]);
      arrow(ctx, X(a.x), Y(a.y), X(b.x), Y(b.y), C.violet, 0.9);
      ctx.setLineDash([]);
      ctx.strokeStyle = "rgba(186,162,230,.35)";
      ctx.beginPath();
      ctx.arc(
        X(b.x),
        Y(b.y),
        3 + Math.min(0.3, b.uncertainty) * side,
        0,
        Math.PI * 2,
      );
      ctx.stroke();
      ctx.fillStyle = C.violet;
      ctx.fillRect(X(b.x) - 2, Y(b.y) - 2, 4, 4);
    }
    if (points.length) {
      ctx.fillStyle = "#fff";
      ctx.fillRect(X(points[0].x) - 3, Y(points[0].y) - 3, 6, 6);
    }
    text(ctx, "MODEL PREDICTION / NOT OBSERVED EVIDENCE", 24, h - 12);
    $("rollout-status").textContent =
      state.sleep.rollout_status === "completed"
        ? "Learned trajectory · " +
          Math.max(0, points.length - 1) +
          " predicted steps · separate imagined provenance"
        : state.sleep.rollout_status ||
          "Train the model to form a supported prediction.";
  }
  function drawLoss() {
    const { ctx, w, h } = canvas("loss"),
      trace = state?.sleep.trace || [];
    if (trace.length < 2) {
      text(ctx, "Each point is a completed gradient update.", 0, h / 2);
      return;
    }
    const max = Math.max(...trace.map((d) => d.loss), 0.001) * 1.08;
    ctx.strokeStyle = "#343c31";
    ctx.beginPath();
    ctx.moveTo(32, 12);
    ctx.lineTo(32, h - 24);
    ctx.lineTo(w - 8, h - 24);
    ctx.stroke();
    ctx.strokeStyle = C.violet;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    trace.forEach((d, j) => {
      const x = 32 + (j / (trace.length - 1)) * (w - 48),
        y = h - 28 - (d.loss / max) * (h - 44);
      j ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.stroke();
    text(ctx, max.toFixed(3), 0, 16);
    text(ctx, "0", 16, h - 24);
    text(ctx, "1", 32, h - 6);
    text(ctx, String(trace.length), w - 24, h - 6);
  }
  function draw() {
    if (!state) return;
    drawExperience();
    drawTree();
    drawImagination();
    drawLoss();
  }
  function metric(dl, name, value) {
    const dt = document.createElement("dt"),
      dd = document.createElement("dd");
    dt.textContent = name;
    dd.textContent = value;
    dl.append(dt, dd);
  }
  function renderQueryMetrics() {
    const host = $("query-metrics"),
      q = state?.query;
    if (!q) {
      const p = document.createElement("p");
      p.textContent =
        "Query the field to compare the hierarchical read with separately charged dense audits.";
      host.replaceChildren(p);
      return;
    }
    const dl = document.createElement("dl");
    metric(dl, "Raw attention pairs", q.work.raw_pairs);
    metric(dl, "Summary dot products", q.work.summary_dot_products);
    metric(dl, "Cold rows examined", q.work.cold_rows);
    metric(dl, "Recovered observations", (q.recovered || []).length);
    if (q.cold_route) {
      metric(
        dl,
        "Dormant archive candidates",
        (q.cold_selected_ids || []).length,
      );
      if (q.cold_work) {
        metric(dl, "Cold-index raw pairs", q.cold_work.raw_pairs);
        metric(dl, "Cold-index summary dots", q.cold_work.summary_dot_products);
      }
    }
    if (q.dense_audit) {
      metric(
        dl,
        "Error vs same-bank dense",
        q.dense_audit.l2_error.toExponential(2),
      );
      metric(dl, "Extra dense audit pairs", q.dense_audit.extra_pairs);
      metric(
        dl,
        "Error vs full current archive",
        q.dense_audit.full_current_error.toExponential(2),
      );
      metric(
        dl,
        "Extra full-archive audit pairs",
        q.dense_audit.full_current_extra_pairs,
      );
    }
    host.replaceChildren(dl);
    const replay = q.purpose === "observed-replay-training";
    $("query-hint").textContent =
      (replay
        ? "Showing an actual replay read used for learning. Controls set your next manual query. "
        : "") +
      (q.cue.mask.every(Boolean)
        ? "Both position coordinates are available. Try removing X or Y to make several episodes compete."
        : "Position information is missing. A span marks an omitted axis; the reader combines what remains with context and action. The white arrow shows recalled displacement at the cursor, whose hidden coordinates are not used for search.");
  }
  function renderRecord() {
    const node = state?.nodes.find((n) => n.id === selectedId);
    $("record-card").hidden = !node;
    if (!node) return;
    $("record-title").textContent =
      "Observed #" + node.id + " / version " + node.version;
    $("record-detail").textContent =
      (node.current ? "Current" : "Superseded") +
      " · " +
      (node.hot ? "active" : "dormant") +
      " · world " +
      (node.context === 0 ? "A" : "B") +
      " · " +
      node.uses +
      " actual uses · salience " +
      node.salience.toFixed(3);
    if (document.activeElement !== $("correct-x"))
      $("correct-x").value = node.next_x.toFixed(3);
    if (document.activeElement !== $("correct-y"))
      $("correct-y").value = node.next_y.toFixed(3);
    $("restore").disabled = !node.current || node.hot || state.sleep.busy;
    $("correct").disabled = !node.current || state.sleep.busy;
  }
  function point(event) {
    if (!fieldBounds) return null;
    const r = $("experience").getBoundingClientRect();
    if (projection === "layers") {
      const b = fieldBounds,
        c = context() ?? 0,
        u = (event.clientX - r.left - b.cx) / (b.scale * 0.28),
        v =
          (event.clientY - r.top - b.cy + c * b.scale * 0.3) / (b.scale * 0.13),
        x = (u + v) / 2,
        y = (v - u) / 2;
      return Math.abs(x) <= 1 && Math.abs(y) <= 1 ? [x, y] : null;
    }
    const x = (event.clientX - r.left - fieldBounds.x) / fieldBounds.side,
      y = (event.clientY - r.top - fieldBounds.y) / fieldBounds.side;
    return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? [x * 2 - 1, y * 2 - 1] : null;
  }
  function nearest(p) {
    let best = null,
      d = Infinity;
    for (const n of state?.nodes || []) {
      const delta = (n.x - p[0]) ** 2 + (n.y - p[1]) ** 2;
      if (delta < d) {
        d = delta;
        best = n;
      }
    }
    return best;
  }
  function screenNode(event) {
    const r = $("experience").getBoundingClientRect(),
      x = event.clientX - r.left,
      y = event.clientY - r.top;
    let id = null,
      best = 324;
    for (const n of projectedNodes) {
      const d = (n.x - x) ** 2 + (n.y - y) ** 2;
      if (d < best) {
        best = d;
        id = n.id;
      }
    }
    return id;
  }
  $("experience").addEventListener("pointerdown", (event) => {
    if (state?.sleep.busy) return;
    if ((tool === "inspect" || event.shiftKey) && projection === "layers") {
      selectedId = screenNode(event);
      renderRecord();
      draw();
      return;
    }
    const p = point(event);
    if (!p) return;
    if (tool === "inspect" || event.shiftKey) {
      selectedId = nearest(p)?.id;
      renderRecord();
      draw();
    } else {
      position = p;
      safe(api("/api/query", cue()));
    }
  });
  $("experience").addEventListener("pointermove", (event) => {
    if (projection === "layers") hoverId = screenNode(event);
    else {
      const p = point(event);
      hoverId = p ? nearest(p)?.id : null;
    }
    drawExperience();
  });
  $("experience").addEventListener("pointerleave", () => {
    hoverId = null;
    drawExperience();
  });
  $("experience").addEventListener("keydown", (event) => {
    if (state?.sleep.busy) return;
    if (event.key === "Enter") {
      event.preventDefault();
      safe(api("/api/query", cue()));
    } else if (
      tool === "inspect" &&
      ["ArrowLeft", "ArrowRight"].includes(event.key)
    ) {
      event.preventDefault();
      const nodes = state?.nodes || [];
      const i = nodes.findIndex((n) => n.id === selectedId),
        next = Math.max(
          0,
          Math.min(nodes.length - 1, i + (event.key === "ArrowRight" ? 1 : -1)),
        );
      selectedId = nodes[next]?.id;
      renderRecord();
      draw();
    }
  });
  document.querySelectorAll("[data-tool]").forEach(
    (button) =>
      (button.onclick = () => {
        tool = button.dataset.tool;
        document
          .querySelectorAll("[data-tool]")
          .forEach((b) => b.classList.toggle("selected", b === button));
      }),
  );
  document.querySelectorAll("[data-projection]").forEach(
    (button) =>
      (button.onclick = () => {
        projection = button.dataset.projection;
        document
          .querySelectorAll("[data-projection]")
          .forEach((b) => b.classList.toggle("selected", b === button));
        draw();
      }),
  );
  $("query-now").onclick = () => safe(api("/api/query", cue()));
  for (const id of ["know-x", "know-y", "context", "action"])
    $(id).addEventListener("change", () => {
      if (!state?.sleep.busy) safe(api("/api/query", cue()));
    });
  $("collect").onclick = () =>
    safe(api("/api/collect", { count: 32, context: context() }));
  $("fade").onclick = () => safe(api("/api/forget", { steps: 40 }));
  $("reset").onclick = () =>
    safe(
      (async () => {
        clearTimeout(pollTimer);
        selectedId = null;
        previousHash = null;
        await api("/api/reset", { seed: 7 });
        await api("/api/query", cue());
      })(),
    );
  async function sleep() {
    await api("/api/sleep", {
      strategy: $("strategy").value,
      steps: Number($("sleep-steps").value),
      position: position.slice(),
      context: context() ?? 0,
    });
    schedulePoll();
  }
  $("sleep").onclick = () => safe(sleep());
  $("sleep-secondary").onclick = () => safe(sleep());
  $("cycle").onclick = () =>
    safe(
      (async () => {
        cycleActive = true;
        await api("/api/collect", { count: 32, context: context() });
        await api("/api/query", cue());
        await api("/api/forget", { steps: 40 });
        await sleep();
        cycleActive = false;
      })(),
    );
  $("restore").onclick = () => {
    if (selectedId !== null) safe(api("/api/restore", { id: selectedId }));
  };
  $("correct").onclick = () => {
    if (selectedId !== null)
      safe(
        api("/api/correct", {
          id: selectedId,
          successor: [
            Number($("correct-x").value),
            Number($("correct-y").value),
          ],
        }),
      );
  };
  $("rare-query").onclick = () => {
    $("context").value = "1";
    $("know-x").checked = true;
    $("know-y").checked = true;
    position = [-0.3, -0.3];
    safe(api("/api/query", cue()));
  };
  $("partial-query").onclick = () => {
    $("know-x").checked = false;
    $("know-y").checked = true;
    safe(api("/api/query", cue()));
  };
  $("export").onclick = () => {
    if (!state) return;
    const url = URL.createObjectURL(
      new Blob(
        [
          JSON.stringify(
            { schema: "somna/browser-evidence-v1", events, state },
            null,
            2,
          ),
        ],
        { type: "application/json" },
      ),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "somna-tick-" + state.tick + ".json";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  let resizeTimer;
  addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(draw, 100);
  });
  document.fonts.ready.then(draw);
  (async () => {
    try {
      await api("/api/state");
      if (!state.sleep.busy) await api("/api/query", cue());
    } catch (e) {
      $("connection").className = "bad";
      $("connection").querySelector("span").textContent = "Engine unavailable";
      error(
        new Error(
          "Start python -m research.serve_somna --port 8791 and open http://127.0.0.1:8791/. " +
            e.message,
        ),
      );
    }
  })();
})();
