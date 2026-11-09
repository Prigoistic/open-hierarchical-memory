"use strict";
(() => {
  const $ = (id) => document.getElementById(id),
    labels = {
      none: "No episodic recall",
      flat_zha_mask: "Flat ZHA + coverage",
      flat_exact_mask: "Flat exact + coverage",
      flat_exact_history_mask: "Exact history + coverage",
      bundle_zha: "ZHA dependency bundles",
      bundle_exact: "Exact dependency bundles",
      bundle_recency: "Recent dependency bundles",
      graph: "Observed graph + coverage",
      full: "Full observed memory",
      exact: "Exact fact retrieval",
      fifo: "FIFO facts",
      recency: "Recent facts",
      zha: "ZHA fixed threshold",
      zha_adaptive: "ZHA adaptive fill",
      matching: "Geometric search",
      linear: "Same cases / ridge model",
      dense: "Dense case attention",
      top16: "Exact top 16",
      "zha-p25": "ZHA / p = 0.25",
      "zha-p50": "ZHA / p = 0.50",
      "random-values": "Shuffled case targets",
    };
  let catalog = { runs: [], summary: [] },
    bank = null,
    run = null,
    mode = "solution",
    cursor = 0,
    playing = false,
    timer = null,
    requestId = 0,
    readMap = new Map();
  const signature = (s) => s.player + "|" + s.boxes.join(",");
  function fail(e) {
    $("error").hidden = false;
    $("error").textContent = e.message || String(e);
    $("connection").textContent = "Experiment unavailable";
    pause();
  }
  async function json(url) {
    const c = new AbortController(),
      t = setTimeout(() => c.abort(), 15000);
    try {
      const r = await fetch(url, { signal: c.signal });
      const v = await r.json();
      if (!r.ok) throw Error(v.error || "Artifact request failed");
      return v;
    } finally {
      clearTimeout(t);
    }
  }
  function opts(el, values, preferred) {
    const old = preferred ?? el.value;
    el.replaceChildren();
    for (const [value, text] of values) {
      const o = document.createElement("option");
      o.value = value;
      o.textContent = text;
      el.append(o);
    }
    if (values.some((v) => String(v[0]) === String(old)))
      el.value = String(old);
  }
  function unique(values) {
    return [...new Set(values)];
  }
  function suiteRows() {
    const [task, split] = $("suite").value.split(":");
    return catalog.runs.filter((r) => r.task === task && r.split === split);
  }
  function fillLevels(preferred) {
    opts(
      $("level"),
      unique(suiteRows().map((r) => r.level_id))
        .sort((a, b) => a - b)
        .map((x) => [
          String(x),
          ($("suite").value.startsWith("minigrid:") ? "Seed " : "Puzzle ") + x,
        ]),
      preferred,
    );
    fillConfigs();
  }
  function fillConfigs(preferred) {
    const rows = suiteRows().filter(
      (r) => String(r.level_id) === $("level").value,
    );
    opts(
      $("config"),
      unique(rows.map((r) => r.config))
        .sort()
        .map((x) => [x, labels[x] || x]),
      preferred,
    );
    opts(
      $("budget"),
      unique(rows.map((r) => r.expansion_limit))
        .sort((a, b) => a - b)
        .map((x) => [
          String(x),
          x.toLocaleString() +
            ($("suite").value.startsWith("minigrid:")
              ? " actions"
              : " expansions"),
        ]),
      $("budget").value || "1024",
    );
  }
  async function reload() {
    pause();
    catalog = await json("/api/catalog");
    if (!catalog.runs.length)
      throw Error("No completed benchmark runs are available yet.");
    bank = await json("/api/bank");
    opts(
      $("suite"),
      unique(catalog.runs.map((r) => r.task + ":" + r.split)).map((s) => [
        s,
        s === "boxoban:hard"
          ? "Boxoban / official hard set"
          : s === "boxoban:test"
            ? "Boxoban / official test set"
            : s
                .replace("minigrid:MiniGrid-", "MiniGrid / ")
                .replace("/minigrid-", " / "),
      ]),
      $("suite").value || "boxoban:hard",
    );
    const start = new URLSearchParams(location.search).get("task"),
      dependencyStart = !run && start === "dependencies",
      mazeStart = !run && start === "maze";
    if (dependencyStart) {
      const cohorts = unique(
        catalog.runs
          .filter((r) => r.dataset?.startsWith("dependency-evaluation-"))
          .map((r) => r.dataset),
      ).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
      const dataset = cohorts.at(-1);
      if (dataset)
        $("suite").value = "minigrid:MiniGrid-KeyCorridorS6R3-v0/" + dataset;
    }
    if (mazeStart)
      $("suite").value =
        "minigrid:MiniGrid-MultiRoom-N6-v0/minigrid-evaluation-v2";
    fillLevels(dependencyStart ? "2001" : mazeStart ? "1001" : undefined);
    fillConfigs(
      run
        ? $("config").value
        : dependencyStart
          ? "bundle_zha"
          : mazeStart
            ? "zha_adaptive"
            : "zha-p25",
    );
    if (mazeStart || dependencyStart) mode = "search";
    await loadRun();
    if (mazeStart) {
      cursor = 17;
      draw();
    }
  }
  async function loadRun() {
    pause();
    const row = suiteRows().find(
      (r) =>
        String(r.level_id) === $("level").value &&
        r.config === $("config").value &&
        String(r.expansion_limit) === $("budget").value,
    );
    if (!row) return;
    const id = ++requestId;
    $("connection").textContent = "Reading checksum-bound trace";
    const next = await json("/api/run?id=" + encodeURIComponent(row.uid));
    if (id !== requestId) return;
    run = next;
    cursor = 0;
    readMap = new Map((run.reads || []).map((r) => [signature(r), r]));
    if (!isMaze() && !run.success && mode === "solution") mode = "search";
    $("error").hidden = true;
    $("connection").textContent = "Completed experiment · source checked";
    $("board-label").textContent = "BOXOBAN / " + run.split.toUpperCase();
    $("board-title").textContent =
      (run.split === "hard" ? "Hard puzzle #" : "Puzzle #") + run.level_id;
    configureTaskDisplay();
    renderMetrics();
    renderComparison();
    draw();
  }
  function metric(host, name, value) {
    const d = document.createElement("div"),
      s = document.createElement("span"),
      b = document.createElement("b");
    s.textContent = name;
    b.textContent = value;
    d.append(s, b);
    host.append(d);
  }
  function renderMetrics() {
    const h = $("run-metrics");
    h.replaceChildren();
    metric(h, "Outcome", statusLabel(run));
    metric(
      h,
      isMaze() ? "Actions" : "Search expansions",
      run.expanded.toLocaleString(),
    );
    metric(
      h,
      isMaze() ? "Return" : "Solution pushes",
      isMaze() ? run.result.return.toFixed(3) : (run.pushes ?? "—"),
    );
    metric(
      h,
      isMaze() ? "Episode time" : "Search time",
      (run.wall_seconds * 1000).toFixed(1) + " ms",
    );
    metric(
      h,
      isMaze() ? "Archived fact versions" : "Training cases",
      (isMaze() ? run.archive.length : bank.cases.length).toLocaleString(),
    );
    $("solution").disabled = !isMaze() && !run.success;
  }
  function frames() {
    return isMaze()
      ? run.trajectory
      : mode === "solution"
        ? run?.path || []
        : run?.expanded_trace || [];
  }
  function pause() {
    playing = false;
    clearTimeout(timer);
    $("play").textContent = "Play trace ↗";
  }
  function tick() {
    if (!playing) return;
    const data = frames();
    if (cursor >= data.length - 1) {
      pause();
      return;
    }
    cursor++;
    draw();
    timer = setTimeout(tick, mode === "search" ? 65 : 280);
  }
  function play() {
    if (playing) {
      pause();
      return;
    }
    if (cursor >= frames().length - 1) cursor = 0;
    playing = true;
    $("play").textContent = "Pause Ⅱ";
    tick();
  }
  function canvas(el) {
    const r = el.getBoundingClientRect(),
      d = Math.min(devicePixelRatio || 1, 2);
    el.width = Math.round(r.width * d);
    el.height = Math.round(r.height * d);
    const c = el.getContext("2d");
    c.setTransform(d, 0, 0, d, 0, 0);
    c.clearRect(0, 0, r.width, r.height);
    return { c, w: r.width, h: r.height };
  }
  function paint(el, rows, state) {
    const { c, w, h } = canvas(el);
    if (!rows?.length || !state || w < 40 || h < 40) return;
    const side = Math.min(w - 32, h - 16),
      cell = Math.floor(side / Math.max(rows.length, rows[0].length)),
      x0 = (w - cell * rows[0].length) / 2,
      y0 = (h - cell * rows.length) / 2,
      boxes = new Set(state.boxes);
    for (let y = 0; y < rows.length; y++)
      for (let x = 0; x < rows[y].length; x++) {
        const tile = rows[y][x],
          n = y * rows[0].length + x,
          px = x0 + x * cell,
          py = y0 + y * cell,
          goal = ".*+".includes(tile);
        c.fillStyle = tile === "#" ? "#313131" : "#131209";
        c.fillRect(px + 1, py + 1, cell - 2, cell - 2);
        if (goal) {
          c.strokeStyle = "#87d9cb";
          c.lineWidth = 2;
          c.beginPath();
          c.arc(px + cell / 2, py + cell / 2, cell * 0.22, 0, Math.PI * 2);
          c.stroke();
        }
        if (boxes.has(n)) {
          c.fillStyle = goal ? "#87d9cb" : "#e2ce86";
          const inset = Math.max(2, cell * 0.16);
          c.fillRect(
            px + inset,
            py + inset,
            cell - 2 * inset,
            cell - 2 * inset,
          );
          c.strokeStyle = "#131209";
          c.lineWidth = 1;
          c.strokeRect(
            px + inset + 2,
            py + inset + 2,
            cell - 2 * inset - 4,
            cell - 2 * inset - 4,
          );
        }
        if (n === state.player) {
          c.fillStyle = "#f2f0dc";
          c.beginPath();
          c.arc(
            px + cell / 2,
            py + cell / 2,
            Math.max(2, cell * 0.17),
            0,
            Math.PI * 2,
          );
          c.fill();
        }
      }
  }
  function dlMetric(dl, name, value) {
    const t = document.createElement("dt"),
      d = document.createElement("dd");
    t.textContent = name;
    d.textContent = value;
    dl.append(t, d);
  }
  function readsFor(state) {
    return state ? readMap.get(signature(state)) : null;
  }
  function renderRead(state) {
    const read = readsFor(state),
      host = $("read-metrics"),
      gallery = $("cases");
    host.replaceChildren();
    gallery.replaceChildren();
    const d = document.createElement("dl"),
      work = run.read_work || {};
    dlMetric(
      d,
      "Reader setup before search",
      ((work.lifetime_reader_setup_seconds || 0) * 1000).toFixed(2) + " ms",
    );
    dlMetric(d, "Total read calls", Number(work.calls || 0).toLocaleString());
    dlMetric(
      d,
      "Raw keys scored",
      Number(work.raw_key_scores || 0).toLocaleString(),
    );
    dlMetric(
      d,
      "Summary channel dots",
      Number(work.summary_dot_products || 0).toLocaleString(),
    );
    dlMetric(
      d,
      "Index tensor storage",
      (Number(work.index_owned_tensor_bytes || 0) / 1024).toFixed(1) + " KiB",
    );
    if (read)
      dlMetric(
        d,
        "Estimated extra pushes",
        Math.max(0, Math.min(40, read.value)).toFixed(3),
      );
    host.append(d);
    if (run.method === "matching") {
      $("read-description").textContent =
        "This baseline uses an exact geometric box-to-goal lower bound. It does not consult the case bank.";
      $("case-caption").textContent =
        "The same legal moves, deadlock checks and search budget apply to all readers.";
      return;
    }
    if (run.method === "linear") {
      $("read-description").textContent =
        "A ridge predictor was fitted on the same training cases. Its search-time prediction does not retrieve individual examples.";
      $("case-caption").textContent =
        "This control tests whether retrieval is needed at all.";
      return;
    }
    if (!read) {
      $("read-description").textContent =
        "No case read was made for this state. Initial and known-goal states use the geometric bound; choose an intermediate state to inspect recall.";
      $("case-caption").textContent =
        "No invented recall is shown for a state with no recorded read.";
      return;
    }
    const ids =
      read.selected_ids === null
        ? bank.cases.map((_, i) => i + 1)
        : read.selected_ids.filter((i) => i > 0);
    $("read-description").textContent =
      (read.selected_ids === null
        ? "All training cases were read. "
        : ids.length + " training examples were selected. ") +
      (run.method === "random_values"
        ? "This negative control permutes their target costs."
        : "Their saved suffix costs adjust search priority; they do not validate moves.");
    for (const id of ids.slice(0, 4)) {
      const item = bank.cases[id - 1];
      if (!item) continue;
      const card = document.createElement("article"),
        cv = document.createElement("canvas"),
        p = document.createElement("p");
      card.className = "case";
      cv.setAttribute(
        "aria-label",
        "Actual selected training puzzle " + item.level_id,
      );
      p.textContent =
        "Train #" +
        item.level_id +
        " · " +
        item.remaining_pushes +
        " observed pushes remaining";
      card.append(cv, p);
      gallery.append(card);
      paint(cv, bank.boards[String(item.level_id)], item);
    }
    $("case-caption").textContent =
      "Showing " +
      Math.min(ids.length, 4) +
      " of " +
      ids.length +
      " selected examples in source order. The zero-valued attention sink is omitted from the thumbnails.";
  }
  function statusLabel(row) {
    if (row.task === "minigrid" || row.environment_id) {
      const result = row.result || row;
      return row.success
        ? "Solved"
        : result.error
          ? "Policy error"
          : result.truncated
            ? "Env timeout"
            : result.external_cutoff
              ? "Action limit"
              : "Terminated";
    }
    return row.success
      ? "Solved"
      : row.status === "expansion_limit"
        ? "Expansion limit"
        : row.status === "wall_timeout"
          ? "Time limit"
          : row.status === "retrieval_budget"
            ? "Read budget"
            : "Search exhausted";
  }
  function renderComparison() {
    const host = $("comparison-body");
    host.replaceChildren();
    const rows = catalog.runs
      .filter(
        (r) =>
          r.task === run.task &&
          r.split === (run.catalog_split || run.split) &&
          r.level_id === run.level_id &&
          r.expansion_limit === run.expansion_limit,
      )
      .sort((a, b) =>
        (labels[a.config] || a.config).localeCompare(
          labels[b.config] || b.config,
        ),
      );
    for (const row of rows) {
      const tr = document.createElement("tr");
      if (row.config === run.config) tr.className = "current";
      const name = document.createElement("td"),
        button = document.createElement("button");
      button.textContent = labels[row.config] || row.config;
      button.onclick = () => {
        $("config").value = row.config;
        safe(loadRun());
      };
      name.append(button);
      tr.append(name);
      for (const [i, value] of [
        statusLabel(row),
        isMaze() ? Number(row.return).toFixed(3) : (row.pushes ?? "—"),
        row.expanded.toLocaleString(),
        (row.wall_seconds * 1000).toFixed(1) + " ms",
        Number(row.read_work?.raw_key_scores || 0).toLocaleString(),
        Number(row.read_work?.summary_dot_products || 0).toLocaleString(),
      ].entries()) {
        const td = document.createElement("td");
        td.textContent = value;
        if (i === 0) td.className = row.success ? "ok" : "bad";
        tr.append(td);
      }
      host.append(tr);
    }
    $("comparison-label").textContent =
      run.split +
      " #" +
      run.level_id +
      " / " +
      run.expansion_limit.toLocaleString() +
      (isMaze() ? " actions" : " expansions");
  }
  function isMaze() {
    return run?.task === "minigrid";
  }
  const objectNames = [
      "unseen",
      "empty",
      "wall",
      "floor",
      "door",
      "key",
      "ball",
      "box",
      "goal",
      "lava",
      "agent",
    ],
    objectColors = [
      "#e9987d",
      "#87d9cb",
      "#83a5e8",
      "#baa2e6",
      "#e2ce86",
      "#929b89",
    ];
  function tile(ctx, x, y, size, object, color, state) {
    const c = objectColors[color] || "#e5e6dc";
    ctx.fillStyle =
      object === 0 ? "#000" : object === 2 ? "#313131" : "#181818";
    ctx.fillRect(x + 1, y + 1, size - 2, size - 2);
    ctx.fillStyle = c;
    if (object === 4) {
      ctx.strokeStyle = c;
      ctx.lineWidth = 2;
      ctx.strokeRect(x + size * 0.15, y + size * 0.1, size * 0.7, size * 0.8);
      if (state !== 0)
        ctx.fillRect(x + size * 0.2, y + size * 0.15, size * 0.6, size * 0.7);
      if (state === 2) {
        ctx.fillStyle = "#000";
        ctx.fillRect(x + size * 0.45, y + size * 0.4, size * 0.1, size * 0.2);
      }
    } else if (object === 5) {
      ctx.beginPath();
      ctx.arc(x + size * 0.4, y + size * 0.35, size * 0.13, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillRect(x + size * 0.35, y + size * 0.35, size * 0.1, size * 0.4);
      ctx.fillRect(x + size * 0.35, y + size * 0.6, size * 0.25, size * 0.08);
    } else if (object === 6) {
      ctx.beginPath();
      ctx.arc(x + size / 2, y + size / 2, size * 0.25, 0, Math.PI * 2);
      ctx.fill();
    } else if (object === 7 || object === 8 || object === 9) {
      ctx.fillStyle = object === 8 ? "#87d9cb" : object === 9 ? "#e9987d" : c;
      ctx.fillRect(x + size * 0.2, y + size * 0.2, size * 0.6, size * 0.6);
    }
  }
  function agent(ctx, x, y, size, direction) {
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((direction * Math.PI) / 2);
    ctx.fillStyle = "#f2f0dc";
    ctx.beginPath();
    ctx.moveTo(size * 0.33, 0);
    ctx.lineTo(-size * 0.2, -size * 0.2);
    ctx.lineTo(-size * 0.2, size * 0.2);
    ctx.closePath();
    ctx.fill();
    ctx.restore();
  }
  function coverageCells(packet) {
    if (!packet) return [];
    if (
      packet.width !== 64 ||
      packet.height !== 64 ||
      packet.bits_hex?.length !== 1024 ||
      !(
        packet.origin?.length === 2 &&
        packet.origin.every(Number.isInteger) &&
        packet.origin.every((v) => v === -32)
      ) ||
      !/^[0-9a-f]+$/i.test(packet.bits_hex)
    )
      throw Error("Unsupported recorded coverage mask");
    const result = [];
    for (let byte = 0; byte < 512; byte++) {
      const value = parseInt(packet.bits_hex.slice(byte * 2, byte * 2 + 2), 16);
      for (let bit = 0; bit < 8; bit++)
        if (value & (1 << bit)) {
          const index = byte * 8 + bit;
          result.push([
            packet.origin[0] + (index % 64),
            packet.origin[1] + Math.floor(index / 64),
          ]);
        }
    }
    return result;
  }
  function dependencyDetails(d) {
    const panel = document.getElementById("dependency-detail");
    if (!panel) return;
    panel.hidden = !d.dependency;
    panel.replaceChildren();
    if (!d.dependency) return;
    const summary = document.createElement("summary");
    summary.textContent = "Inspect dependency receipts";
    panel.append(summary);
    const scope = document.createElement("p");
    scope.className = "caption-5 muted";
    scope.textContent =
      "Path and one-hop support checks. These receipts do not certify global map completeness or a successful plan.";
    panel.append(scope);
    for (const b of d.dependency.bundles || []) {
      const p = document.createElement("p");
      p.className = "caption-5";
      p.textContent =
        b.kind +
        " #" +
        b.seed_id +
        " · " +
        b.status +
        " · " +
        b.required_historical_count +
        " historical facts" +
        (b.missing?.length ? " · " + b.missing.join(", ") : "");
      panel.append(p);
    }
    if (!(d.dependency.bundles || []).length) {
      const p = document.createElement("p");
      p.className = "caption-5";
      p.textContent = "Coverage-only control: no dependency bundles packed.";
      panel.append(p);
    }
  }

  function drawMaze() {
    const row = run.trajectory[cursor];
    if (!row) return;
    const { c, w, h } = canvas($("board")),
      d = row.decision;
    if (mode === "solution") {
      const image = row.observation.image,
        n = image.length,
        cell = Math.floor(Math.min(w - 32, h - 32) / n),
        x0 = (w - n * cell) / 2,
        y0 = (h - n * cell) / 2;
      for (let x = 0; x < n; x++)
        for (let y = 0; y < n; y++)
          tile(c, x0 + x * cell, y0 + y * cell, cell, ...image[x][y]);
      agent(
        c,
        x0 + (Math.floor(n / 2) + 0.5) * cell,
        y0 + (n - 0.5) * cell,
        cell,
        3,
      );
    } else {
      const facts = new Map(
        (d.memory_facts || []).map((f) => [f.x + "," + f.y, f]),
      );
      for (const f of d.current_facts || []) facts.set(f.x + "," + f.y, f);
      const known = coverageCells(d.coverage);
      const all = [...facts.values()],
        px = d.pose[0],
        py = d.pose[1],
        xs = [px, ...all.map((f) => f.x), ...known.map((p) => p[0])],
        ys = [py, ...all.map((f) => f.y), ...known.map((p) => p[1])],
        loX = Math.min(...xs) - 1,
        loY = Math.min(...ys) - 1,
        nx = Math.max(...xs) - loX + 2,
        ny = Math.max(...ys) - loY + 2,
        cell = Math.max(2, Math.floor(Math.min((w - 32) / nx, (h - 32) / ny))),
        x0 = (w - nx * cell) / 2,
        y0 = (h - ny * cell) / 2;
      c.strokeStyle = "#54606b";
      c.lineWidth = 1;
      for (const [x, y] of known)
        if (!facts.has(x + "," + y))
          c.strokeRect(
            x0 + (x - loX) * cell + 1,
            y0 + (y - loY) * cell + 1,
            Math.max(1, cell - 2),
            Math.max(1, cell - 2),
          );
      for (const f of all)
        tile(
          c,
          x0 + (f.x - loX) * cell,
          y0 + (f.y - loY) * cell,
          cell,
          f.object,
          f.color,
          f.state,
        );
      const archive = new Map((run.archive || []).map((f) => [f.id, f]));
      c.strokeStyle = "#69c6c3";
      c.lineWidth = 1.5;
      for (const b of d.dependency?.bundles || [])
        if (b.status === "complete")
          for (const [a, z] of b.support_edges || []) {
            const f = archive.get(a),
              g = archive.get(z);
            if (!f || !g) continue;
            c.beginPath();
            c.moveTo(
              x0 + (f.x - loX + 0.5) * cell,
              y0 + (f.y - loY + 0.5) * cell,
            );
            c.lineTo(
              x0 + (g.x - loX + 0.5) * cell,
              y0 + (g.y - loY + 0.5) * cell,
            );
            c.stroke();
          }
      c.strokeStyle = "#baa2e6";
      c.lineWidth = 2;
      c.beginPath();
      for (const [i, p] of (d.plan || []).entries()) {
        const x = x0 + (p[0] - loX + 0.5) * cell,
          y = y0 + (p[1] - loY + 0.5) * cell;
        i ? c.lineTo(x, y) : c.moveTo(x, y);
      }
      c.stroke();
      agent(
        c,
        x0 + (px - loX + 0.5) * cell,
        y0 + (py - loY + 0.5) * cell,
        cell,
        d.pose[2],
      );
    }
    $("solution").classList.toggle("selected", mode === "solution");
    $("search").classList.toggle("selected", mode === "search");
    $("timeline").max = String(Math.max(0, run.trajectory.length - 1));
    $("timeline").value = String(cursor);
    $("cursor").textContent =
      cursor + " / " + Math.max(0, run.trajectory.length - 1);
    const actions = [
      "turn left",
      "turn right",
      "forward",
      "pick up",
      "drop",
      "toggle",
      "done",
    ];
    $("step-description").textContent =
      "Step " +
      row.step +
      " · " +
      d.objective +
      " · action: " +
      actions[row.action] +
      " · returned reward " +
      Number(row.reward).toFixed(3) +
      ".";
    $("trace-warning").textContent =
      mode === "solution"
        ? "Official egocentric observation before this action. Black cells are unseen. The policy receives no hidden layout or true simulator position."
        : d.coverage
          ? "Outlined cells were previously observed; their contents are omitted. Cyan edges show accepted bundle support; purple shows the planner route. The mask cannot supply a route through missing facts."
          : "Only visible cells and selected historical facts are drawn. Purple line: current plan. Gaps in recall can disconnect this map.";
    $("maze-legend").hidden = mode !== "search" || !d.coverage;
    renderMazeRead(row);
  }
  function renderMazeRead(row) {
    const d = row.decision,
      w = d.work || {},
      host = $("read-metrics"),
      gallery = $("cases");
    host.replaceChildren();
    gallery.replaceChildren();
    const dl = document.createElement("dl");
    for (const [name, value] of [
      ["History facts returned", d.memory_facts.length],
      ["Current visible facts", d.current_facts.length],
      [
        "Historical slot limit",
        run.reader === "full" ? "All observed" : run.capacity,
      ],
      ["Prefix raw attention pairs", w.raw_attention_pairs || 0],
      [
        "Prefix exact + rerank scores",
        (w.exact_score_pairs || 0) + (w.rerank_pairs || 0),
      ],
      ["Prefix summary channel dots", w.summary_dot_products || 0],
      ["Prefix index rebuilds", w.index_builds || 0],
      ["Full-candidate fallbacks", w.full_candidate_fallbacks || 0],
    ])
      dlMetric(
        dl,
        name,
        typeof value === "number" ? value.toLocaleString() : value,
      );
    if (d.dependency) {
      const bundles = d.dependency.bundles || [],
        work = d.dependency.work_delta || {};
      for (const [name, value] of [
        ["Coverage (binary bytes)", d.coverage?.binary_bytes || 0],
        [
          "Bundles packed",
          bundles.filter((b) => b.status === "complete").length,
        ],
        [
          "Rejected / budget",
          bundles.filter((b) => b.status === "overbudget").length,
        ],
        [
          "Rejected / prerequisite",
          bundles.filter((b) => b.status === "missing_prerequisite").length,
        ],
        ["Head scans / this read", work.head_scan_items || 0],
        ["BFS nodes / this read", work.bfs_nodes || 0],
        [
          "Residual omitted neighbors",
          d.dependency.residual_known_neighbor_omissions?.length || 0,
        ],
      ])
        dlMetric(dl, name, value.toLocaleString());
    }
    host.append(dl);
    dependencyDetails(d);
    $("read-description").textContent =
      "Mission: " +
      row.observation.mission +
      ". Current objective: " +
      d.objective +
      ". " +
      (run.reader === "none"
        ? "This reader returns no episodic facts."
        : "The map is rebuilt from selected facts plus the current observation.");
    for (const f of d.memory_facts.slice(0, 4)) {
      const card = document.createElement("article"),
        cv = document.createElement("canvas"),
        p = document.createElement("p");
      card.className = "case";
      p.textContent =
        "#" +
        f.id +
        " " +
        (objectNames[f.object] || f.object) +
        " at (" +
        f.x +
        ", " +
        f.y +
        "), observed step " +
        f.observed_step +
        (f.cue ? " · cue" : "");
      card.append(cv, p);
      gallery.append(card);
      const { c, w, h } = canvas(cv),
        sz = Math.min(w, h) * 0.7;
      tile(c, (w - sz) / 2, (h - sz) / 2, sz, f.object, f.color, f.state);
    }
    $("case-caption").textContent =
      "First " +
      Math.min(4, d.memory_facts.length) +
      " of " +
      d.memory_facts.length +
      " actual historical facts. Empty map regions are not silently filled from the archive.";
  }

  function cohortSummary() {
    const rows = catalog.summary.filter((r) =>
      isMaze()
        ? r.task === "minigrid" &&
          r.dataset === run.dataset &&
          r.environment_id === run.environment_id
        : r.task === "boxoban" &&
          r.split === run.split &&
          r.expansion_limit === run.expansion_limit,
    );
    const configs = [
      run.config,
      ...(isMaze()
        ? run.dataset.startsWith("dependency-")
          ? ["flat_zha_mask", "flat_exact_history_mask", "graph", "full"]
          : ["exact", "full"]
        : ["top16", "matching"]),
    ];
    const chosen = [...new Set(configs)]
      .map((name) => rows.find((r) => (r.reader || r.config) === name))
      .filter(Boolean);
    $("cohort-status").textContent =
      (isMaze()
        ? "Same task across " +
          (run.split === "evaluation" ? "held out" : "development") +
          " seeds: "
        : "Same budget across the puzzle cohort: ") +
      chosen
        .map(
          (r) =>
            (labels[r.reader || r.config] || r.reader || r.config) +
            " " +
            (r.successes ?? r.solved) +
            "/" +
            (r.episodes ?? r.n),
        )
        .join(" · ");
  }
  function configureTaskDisplay() {
    const maze = isMaze();
    cohortSummary();
    $("solution").textContent = maze ? "Observed view" : "Solution";
    $("search").textContent = maze ? "Recall map" : "Search probes";
    document.querySelector(".legend").hidden = maze;
    $("maze-legend").hidden = true;
    $("dependency-detail").hidden = !maze;
    document.querySelectorAll("thead th")[2].textContent = maze
      ? "Return"
      : "Pushes";
    document.querySelectorAll("thead th")[3].textContent = maze
      ? "Actions"
      : "Expanded";
    document.querySelectorAll("thead th")[4].textContent = maze
      ? "Episode time"
      : "Search time";
    $("level").parentElement.childNodes[0].textContent = maze
      ? "Episode seed"
      : "Puzzle";
    $("budget").parentElement.childNodes[0].textContent = maze
      ? "External action cap"
      : "Search budget";
    $("board").setAttribute(
      "aria-label",
      maze
        ? "Official maze observations and selected historical map"
        : "Recorded puzzle states and search candidates",
    );
    document.querySelector(".comparison .helper").textContent = maze
      ? "Episode time includes policy, reconstruction, environment steps and trace recording. Different readers take different actions and may truncate; these are not matched-compute speed measurements. Query counters include every adaptive pass and rerank."
      : "Latency includes feature extraction, retrieval, search and trace collection. Reader setup is recorded separately. Summary channel dots and raw key scores have different costs.";
    document.querySelector(".comparison .eyebrow").textContent = maze
      ? "Same task seed · same action cap"
      : "Same puzzle · same expansion budget";
    $("scope").textContent = maze
      ? "MiniGrid supplies official partial observations. A fixed symbolic controller rebuilds its map from visible cells and retrieved historical facts; it receives no hidden layout. This tests memory and planning, not a learned RL policy or industrial deployment."
      : "Boxoban is fully observed. ZHA retrieves solved training examples to guide classical search; it does not decide which pushes are legal. This is a research diagnostic, not validation of an industrial deployment.";
    if (maze) {
      $("board-label").textContent = "MINIGRID / " + run.split.toUpperCase();
      $("board-title").textContent =
        run.environment_id.replace("MiniGrid-", "") + " / seed " + run.seed;
    }
  }

  function draw() {
    if (!run) return;
    const data = frames();
    cursor = Math.min(Math.max(0, cursor), Math.max(0, data.length - 1));
    if (isMaze()) {
      drawMaze();
      return;
    }
    const state = data[cursor];
    paint($("board"), run.rows, state);
    $("solution").classList.toggle("selected", mode === "solution");
    $("search").classList.toggle("selected", mode === "search");
    $("timeline").max = String(Math.max(0, data.length - 1));
    $("timeline").value = String(cursor);
    $("cursor").textContent = cursor + " / " + Math.max(0, data.length - 1);
    $("step-description").textContent =
      mode === "solution"
        ? "Validated solution · " +
          state?.pushes +
          " pushes so far · " +
          run.moves.length +
          " primitive moves in the complete route."
        : "Search probe " +
          cursor +
          " · push depth " +
          (state?.pushes ?? 0) +
          " · queued candidates " +
          (state?.frontier ?? 0) +
          ".";
    $("trace-warning").textContent =
      mode === "search"
        ? "These are hypothetical search candidates, not a physically executed trajectory. Failed runs retain their probes."
        : "Each displayed step is a box push. Walking between pushes is included in the saved, independently checked move sequence.";
    renderRead(state);
  }
  function safe(p) {
    p.catch(fail);
  }
  $("suite").onchange = () => {
    fillLevels();
    safe(loadRun());
  };
  $("level").onchange = () => {
    fillConfigs();
    safe(loadRun());
  };
  $("config").onchange = $("budget").onchange = () => safe(loadRun());
  $("reload").onclick = () => safe(reload());
  $("play").onclick = play;
  $("back").onclick = () => {
    pause();
    cursor--;
    draw();
  };
  $("forward").onclick = () => {
    pause();
    cursor++;
    draw();
  };
  $("timeline").oninput = () => {
    pause();
    cursor = Number($("timeline").value);
    draw();
  };
  for (const kind of ["solution", "search"])
    $(kind).onclick = () => {
      pause();
      mode = kind;
      cursor = 0;
      draw();
    };
  $("board").onkeydown = (e) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      pause();
      if (e.key === "Home") cursor = 0;
      else if (e.key === "End") cursor = frames().length - 1;
      else cursor += e.key === "ArrowRight" ? 1 : -1;
      draw();
    }
  };
  let resizeTimer;
  addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(draw, 100);
  });
  document.fonts.ready.then(draw);
  safe(reload());
})();
