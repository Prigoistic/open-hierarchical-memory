"use strict";
(() => {
  const $ = (id) => document.getElementById(id),
    labels = {
      persistent_zha: "Fitted ZHA · persistent memory",
      persistent_support_parent: "Original recovery · 64 slots",
      persistent_support_compact: "Compact path packing · 64 slots",
      persistent_support_connected_zha: "Connected ZHA · 64 slots",
      persistent_support_connected_exact: "Connected exact · control",
      persistent_support_connected_graph: "Connected graph · control",
      persistent_fixed: "Fixed ZHA · persistent memory",
      persistent_random: "Random ZHA · control",
      persistent_always: "Always recover · control",
      persistent_exact: "Exact recovery · control",
      persistent_none: "No cold recovery · control",
      progress_zha: "ZHA + graph recovery",
      progress_exact: "Exact + graph recovery",
      cues_zha: "ZHA cues + widening",
      cues_exact: "Exact cues + widening",
      none: "No recall",
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
  for (const schedule of ["uniform", "priority", "recent"])
    for (const seed of [7, 19, 31])
      labels[`persistent_replay_${schedule}-${seed}`] =
        `${{ uniform: "Uniform replay", priority: "Error priority replay", recent: "Recent only replay" }[schedule]} · ${seed}`;
  Object.assign(labels, {
    persistent_replay_parent: "Unchanged parent · 64 slots",
    persistent_replay_random: "Frozen random · 64 slots",
    persistent_replay_exact: "Exact recovery · 64 slots",
    persistent_replay_no_recovery: "No cold recovery · 64 slots",
    "persistent_replay_parent-cap96": "Unchanged parent · 96 slots",
    "persistent_replay_exact-cap96": "Exact recovery · 96 slots",
  });
  const initialView = new URLSearchParams(location.search);
  let pendingStep = initialView.has("step")
    ? Number(initialView.get("step"))
    : null;
  let catalog = { runs: [], summary: [] },
    bank = null,
    run = null,
    mode = "solution",
    cursor = 0,
    playing = false,
    timer = null,
    streamDelay = 300,
    requestId = 0,
    readMap = new Map(),
    headCursor = -1,
    headMap = new Map(),
    routingView = ["structure", "tree"].includes(initialView.get("view"))
      ? initialView.get("view")
      : "layers",
    routingHits = [],
    routingFocus = null,
    routing3D = null,
    panelRouting = null;
  const navigationMotion = new SomnaVisuals.PoseTween();
  let navigationRevision = 0;
  let activityCache = { key: null, value: null };
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)");
  const signature = (s) => s.player + "|" + s.boxes.join(",");
  function fail(e) {
    $("error").hidden = false;
    $("error").textContent = e.message || String(e);
    $("connection").textContent = "Run unavailable";
    $("board-title").textContent = "Run unavailable";
    $("run-notice").textContent = "Choose another run or retry.";
    $("routing-description").textContent = "No trace loaded.";
    $("latest").hidden =
      !catalog.runs.length || $("cohort").value === latestCohort();
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
    if (
      rows.some((r) => r.config === "persistent_replay_uniform-7") &&
      !rows.some((r) => r.config === (preferred ?? $("config").value))
    )
      preferred = "persistent_replay_uniform-7";
    if (
      rows.some((r) => r.config === "persistent_support_connected_zha") &&
      !rows.some((r) => r.config === (preferred ?? $("config").value))
    )
      preferred = "persistent_support_connected_zha";
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
  function datasetLabel(name) {
    if (name === "task-support-v1") return "Path recovery · fresh seed study";
    if (name === "task-replay-v1") return "Routing replay · fresh seed study";
    if (name === "persistent-task-v2") return "Persistent memory · development";
    if (/(?:progress|repair).*evaluation/.test(name))
      return "Retrieval repair · evaluation";
    if (name.startsWith("progress-") && name.includes("development"))
      return "Repair development " + name.match(/v\d+$/)?.[0];
    if (name.startsWith("progress-") && name.includes("diagnostic"))
      return "Exposed seed diagnostic " + name.match(/v\d+$/)?.[0];
    if (name === "dependency-evaluation-v1")
      return "Coverage & bundles · previous";
    if (name === "minigrid-evaluation-v2")
      return "Original readers · historical";
    if (name === "boxoban-search-v1") return "Boxoban puzzles";
    return name
      .replace("dependency-", "Memory / ")
      .replace("minigrid-", "MiniGrid / ")
      .replaceAll("-", " ");
  }
  function taskLabel(id) {
    return id
      .replace("MiniGrid-", "")
      .replace("KeyCorridorS6R3-v0", "Key corridor")
      .replace("DoorKey-16x16-v0", "Door & key")
      .replace("MultiRoom-N6-v0", "Six rooms")
      .replace("MemoryS17Random-v0", "Remember the sample");
  }
  function latestCohort() {
    const all = unique(catalog.runs.map((r) => r.dataset));
    const rank = (n) =>
      n === "persistent-task-v2"
        ? 120
        : /(?:progress|repair).*evaluation/.test(n)
          ? 100
          : n === "dependency-evaluation-v1"
            ? 80
            : n === "minigrid-evaluation-v2"
              ? 60
              : n === "boxoban-search-v1"
                ? 40
                : 0;
    return all.sort(
      (a, b) =>
        rank(b) - rank(a) || b.localeCompare(a, undefined, { numeric: true }),
    )[0];
  }
  function fillSuites(preferred) {
    const rows = catalog.runs.filter((r) => r.dataset === $("cohort").value);
    if (preferred === undefined) {
      const [oldTask, oldSplit] = $("suite").value.split(":");
      const oldEnv = oldSplit?.split("/")[0];
      const same = rows.find(
        (r) =>
          r.task === oldTask &&
          (r.environment_id === oldEnv || r.split === oldSplit),
      );
      if (same) preferred = same.task + ":" + same.split;
    }
    opts(
      $("suite"),
      unique(rows.map((r) => r.task + ":" + r.split)).map((value) => [
        value,
        value.startsWith("boxoban:")
          ? value.endsWith("hard")
            ? "Hard puzzles"
            : "Test puzzles"
          : taskLabel(value.split(":")[1].split("/")[0]),
      ]),
      preferred,
    );
  }
  function fillCohorts(preferred) {
    const latest = latestCohort(),
      cohorts = unique(catalog.runs.map((r) => r.dataset)).filter(
        (n) =>
          $("show-development").checked ||
          n.includes("evaluation") ||
          n === "persistent-task-v2" ||
          n === "task-replay-v1" ||
          n === "task-support-v1" ||
          n === "boxoban-search-v1",
      );
    opts(
      $("cohort"),
      cohorts
        .sort((a, b) =>
          a === b
            ? 0
            : a === latest
              ? -1
              : b === latest
                ? 1
                : a.localeCompare(b),
        )
        .map((n) => [n, datasetLabel(n)]),
      preferred,
    );
  }
  async function reload() {
    pause();
    catalog = await json("/api/catalog");
    if (!catalog.runs.length) throw Error("No completed runs are available.");
    bank = await json("/api/bank");
    const params = new URLSearchParams(location.search),
      first = !run;
    if (
      first &&
      params.get("dataset") &&
      !params.get("dataset").includes("evaluation") &&
      params.get("dataset") !== "boxoban-search-v1"
    )
      $("show-development").checked = true;
    fillCohorts(
      first ? params.get("dataset") || latestCohort() : $("cohort").value,
    );
    const env = params.get("env") || "MiniGrid-KeyCorridorS6R3-v0";
    fillSuites(
      first ? "minigrid:" + env + "/" + $("cohort").value : $("suite").value,
    );
    fillLevels(first ? params.get("seed") || undefined : $("level").value);
    const available = unique(suiteRows().map((r) => r.config));
    const preferred = first
      ? params.get("reader") ||
        (available.includes("persistent_zha")
          ? "persistent_zha"
          : available.includes("progress_zha")
            ? "progress_zha"
            : available.includes("bundle_zha")
              ? "bundle_zha"
              : available.includes("zha_adaptive")
                ? "zha_adaptive"
                : "zha-p25")
      : $("config").value;
    fillConfigs(preferred);
    if (first)
      mode = $("suite").value.startsWith("minigrid:") ? "search" : "solution";
    await loadRun();
  }
  function updateRunNotice(row) {
    if (run.live) {
      const phase =
        row?.decision.dependency?.graph_source ===
        "active_and_explicitly_recovered_only"
          ? "Persistent observed memory"
          : row?.decision.repair?.fallback_active
            ? "Observed graph recovery"
            : row?.decision.repair?.stage === 2
              ? "Wider ZHA search"
              : "Hierarchical recall";
      $("run-notice").textContent =
        `Fresh solve · ${run.live.status} · ${phase}`;
      $("run-notice").dataset.warning = String(
        !!row?.decision.repair?.fallback_active,
      );
      return;
    }
    if (run.replay || run.support_study) {
      $("run-notice").textContent =
        `Fresh seed comparison · ${statusLabel(run)} · ${run.capacity} active slots`;
      $("run-notice").dataset.warning = "false";
      return;
    }
    const historical = !/(?:progress|repair).*evaluation/.test(run.dataset),
      status = statusLabel(run);
    let text =
      (run.split === "development"
        ? "Development recording"
        : run.split === "diagnostic"
          ? "Exposed seed diagnostic"
          : historical
            ? "Historical recording"
            : "Recorded evaluation") +
      " · " +
      status.toLowerCase();
    if (row?.decision.repair) {
      const repair = row.decision.repair;
      text +=
        " · " +
        (repair.fallback_active
          ? "observed graph fallback"
          : [
              "base recall",
              "directional cues",
              "wider candidate search",
              "graph fallback",
            ][repair.stage]);
    }
    $("run-notice").textContent = text;
    $("run-notice").dataset.warning = String(
      !run.success || Boolean(row?.decision.repair?.fallback_active),
    );
    $("latest").hidden = run.dataset === latestCohort();
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
    run = null;
    setRunControls(true);
    routingHits = [];
    panelRouting = null;
    $("next-event").hidden = true;
    headCursor = -1;
    headMap.clear();
    $("board-title").textContent = "Loading selected run";
    $("run-notice").textContent = "Loading selected run";
    $("run-metrics").replaceChildren();
    $("cases").replaceChildren();
    $("read-metrics").replaceChildren();
    $("comparison-body").replaceChildren();
    $("read-description").textContent = "";
    $("step-description").textContent = "";
    $("routing-description").textContent = "Loading recorded routing";
    $("routing-inspection").textContent = "";
    canvas($("board"));
    routingCanvas();
    for (const field of [
      "case-caption",
      "trace-warning",
      "cohort-status",
      "routing-inspection",
    ])
      $(field).textContent = "";
    let next;
    try {
      next = await json("/api/run?id=" + encodeURIComponent(row.uid));
    } catch (error) {
      if (id !== requestId) return;
      throw error;
    }
    if (id !== requestId) return;
    run = next;
    setRunControls(false);
    cursor =
      Number.isSafeInteger(pendingStep) && pendingStep >= 0 ? pendingStep : 0;
    pendingStep = null;
    headCursor = -1;
    headMap.clear();
    routingFocus = null;
    readMap = new Map((run.reads || []).map((r) => [signature(r), r]));
    if (!isMaze() && !run.success && mode === "solution") mode = "search";
    $("error").hidden = true;
    $("connection").textContent = "Recorded experiment";
    $("board-label").textContent = "BOXOBAN / " + run.split.toUpperCase();
    $("board-title").textContent =
      (run.split === "hard" ? "Hard puzzle #" : "Puzzle #") + run.level_id;
    configureTaskDisplay();
    renderMetrics();
    renderComparison();
    updateRunNotice();
    const params = new URLSearchParams({
      task: isMaze() ? "maze" : "puzzles",
      dataset: run.dataset,
      reader: run.reader || run.config,
      seed: String(run.level_id),
    });
    if (isMaze()) params.set("env", run.environment_id);
    params.set("step", String(cursor));
    params.set("view", routingView);
    if (initialView.get("renderer") === "canvas")
      params.set("renderer", "canvas");
    history.replaceState(null, "", "?" + params);
    draw();
  }
  function setRunControls(disabled) {
    for (const id of [
      "play",
      "back",
      "forward",
      "timeline",
      "next-event",
      "cue",
      "routing-pass",
      "layers",
      "structure",
      "tree-view",
      "solution",
      "search",
    ])
      $(id).disabled = disabled;
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
      isMaze() ? "Stored versions" : "Training cases",
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
    $("play").textContent = "Play";
  }
  function tick() {
    if (!playing) return;
    const data = frames();
    if (cursor >= data.length - 1) {
      if (["running", "streaming"].includes(run.live?.status)) {
        timer = setTimeout(tick, 120);
        return;
      }
      pause();
      return;
    }
    cursor++;
    draw();
    timer = setTimeout(tick, run.live ? streamDelay : Number($("speed").value));
  }
  function play() {
    if (playing) {
      pause();
      return;
    }
    if (cursor >= frames().length - 1) cursor = 0;
    playing = true;
    $("play").textContent = "Pause";
    tick();
  }
  function canvas(el) {
    const r = el.getBoundingClientRect(),
      d = Math.min(devicePixelRatio || 1, 2);
    const width = Math.round(r.width * d),
      height = Math.round(r.height * d);
    if (el.width !== width) el.width = width;
    if (el.height !== height) el.height = height;
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
        row.wall_seconds === null
          ? "—"
          : (row.wall_seconds * 1000).toFixed(1) + " ms",
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

  function observedHeads() {
    if (cursor < headCursor) {
      headCursor = -1;
      headMap.clear();
    }
    while (headCursor < cursor) {
      headCursor++;
      for (const f of run.trajectory[headCursor].new_facts)
        headMap.set(f.x + "," + f.y, f);
    }
    return [...headMap.values()].sort((a, b) => a.id - b.id);
  }
  function routingCanvas() {
    routing3D?.setVisible(false);
    $("routing-readout").replaceChildren();
    $("routing").hidden = false;
    return canvas($("routing"));
  }
  function renderRouting(row) {
    const d = row.decision,
      persistent =
        d.dependency?.graph_source === "active_and_explicitly_recovered_only",
      routes = (d.route || []).map((route) =>
        SomnaRouting.resolveEvent(run, route),
      ),
      mission = row.observation.mission;
    const cueIds = unique(routes.map((r) => r.query_index));
    opts(
      $("cue"),
      cueIds.map((i) => [
        String(i),
        SomnaRouting.cueLabel(i, mission, d.repair),
      ]),
      $("cue").value,
    );
    const passes = routes
      .map((r, i) => [r, i])
      .filter(([r]) => String(r.query_index) === $("cue").value);
    opts(
      $("routing-pass"),
      passes.map(([r, i]) => [
        String(i),
        "Pass " + (r.attempt + 1) + " · p=" + r.p,
      ]),
      $("routing-pass").value || String(passes.at(-1)?.[1]),
    );
    $("cue").disabled = $("routing-pass").disabled = !routes.length;
    $("layers").disabled = $("tree-view").disabled = !routes.length;
    $("structure").disabled = !routes.length || !routing3D;
    $("routing").setAttribute("aria-disabled", String(!routes.length));
    const inventory = d.inventory
      ? (objectNames[d.inventory[0]] || "object") +
        " / " +
        ["red", "green", "blue", "purple", "yellow", "grey"][d.inventory[1]]
      : "empty hands";
    $("cue-context").textContent =
      "Position (" + d.pose.slice(0, 2).join(", ") + ") · " + inventory;
    routingHits = [];
    if (!routes.length) {
      panelRouting = null;
      const { c, w, h } = routingCanvas();
      const fallback = d.repair?.fallback_active;
      if (persistent && routing3D) {
        $("routing").hidden = true;
        routing3D.setVisible(true);
        const model = SomnaVisuals.persistentMemoryModel(
          {
            facts: observedHeads(),
            decision: d,
            step: row.step,
            key:
              (run.live?.id || run.dataset + run.reader + run.seed) +
              ":" +
              row.step,
            retiredIds: row.retired_ids || [],
            evictedIds:
              row.lifecycle?.capacity_evicted_ids ||
              row.decision.dependency?.evicted_ids ||
              [],
          },
          { activeOnly: true },
        );
        routing3D.setData(model);
        routingHits = model.points.map((p) => ({
          node: {
            key: p.id,
            level: 0,
            index: Number(p.id),
            kept: p.selected,
            facts: observedHeads().filter((f) => String(f.id) === p.id),
          },
        }));
      }
      opts($("cue"), [
        ["none", fallback ? "Graph recovery" : "No hierarchy cue"],
      ]);
      opts($("routing-pass"), [["none", "Not applicable"]]);
      c.fillStyle = "#e8e8e5";
      c.font = "18px Geist";
      c.fillText(
        persistent
          ? "Active workspace"
          : fallback
            ? "Observed graph recovery"
            : "Direct fact selection",
        16,
        80,
      );
      c.fillStyle = "#939795";
      c.font = "12px Geist";
      c.fillText(
        d.memory_ids.length + " facts returned · no hierarchy pass",
        16,
        112,
      );
      $("routing-description").textContent = persistent
        ? d.dependency.recovery_status === "deferred_active_progress"
          ? "Archive idle · active memory serves this decision. No hierarchy pass was run."
          : d.dependency.recovery_status === "budget_exhausted"
            ? "Archive budget reached · no hidden exact fallback."
            : "Direct archive selection · no hierarchical pass."
        : fallback
          ? "The progress guard escalated to the observed graph. This step is counted as a fallback."
          : "This method selects facts without hierarchical routing.";
      $("routing-inspection").textContent = "";
      return;
    }
    const recorded = routes[Number($("routing-pass").value)],
      route = SomnaRouting.resolveSnapshot(run, recorded),
      model = SomnaRouting.routingModel(route, observedHeads(), d.memory_ids);
    panelRouting = model;
    $("structure").disabled = !routing3D || !model.mapped;
    if (routing3D && routingView !== "tree" && model.mapped) {
      $("routing").hidden = true;
      routing3D.setVisible(true);
      routingHits = model.levels.flatMap((l) =>
        l.nodes.map((node) => ({ node })),
      );
      const key = [
        run.environment_id,
        run.dataset,
        run.reader,
        run.seed,
        cursor,
        $("cue").value,
        $("routing-pass").value,
      ].join(":");
      routing3D.setData(
        (routingView === "structure"
          ? SomnaVisuals.arborHierarchyModel
          : SomnaVisuals.indexHierarchyModel)(model, key, {
          columns:
            innerWidth <
            (document.documentElement.classList.contains("is-embedded")
              ? 1000
              : 600)
              ? 12
              : 24,
        }),
      );
      routing3D.highlight(routingFocus);
      $("routing-description").textContent =
        model.rawCount +
        " originals attended; " +
        d.memory_ids.length +
        " facts returned to the planner. Drag to orbit; select a node to inspect.";
      const selected = routingHits.find((p) => p.node.key === routingFocus);
      $("routing-inspection").textContent = selected
        ? SomnaRouting.nodeDescription(selected.node)
        : "Select a node to inspect its original records.";
      $("layers").classList.toggle("selected", routingView === "layers");
      $("structure").classList.toggle("selected", routingView === "structure");
      $("tree-view").classList.remove("selected");
      $("layers").setAttribute(
        "aria-pressed",
        String(routingView === "layers"),
      );
      $("structure").setAttribute(
        "aria-pressed",
        String(routingView === "structure"),
      );
      $("tree-view").setAttribute("aria-pressed", "false");
      return;
    }
    const { c, w, h } = routingCanvas();
    const positions = new Map(),
      levels = model.levels;
    levels.forEach((level, j) => {
      const nodes = level.nodes;
      if (routingView === "layers") {
        const gap = (w - 32) / levels.length,
          x0 = 16 + j * gap,
          y0 = 64,
          pw = Math.max(24, gap - 24),
          ph = h - 124;
        const project = (u, v) => ({
          x: x0 + u + v * 0.08,
          y: y0 + v - u * 0.25,
        });
        c.strokeStyle = "#303b39";
        c.lineWidth = 1;
        c.beginPath();
        [
          [0, 0],
          [pw, 0],
          [pw, ph],
          [0, ph],
          [0, 0],
        ].forEach(([u, v], k) => {
          const p = project(u, v);
          k ? c.lineTo(p.x, p.y) : c.moveTo(p.x, p.y);
        });
        c.stroke();
        c.fillStyle = "#939795";
        c.font = "12px Geist";
        c.fillText(level.level ? "Level " + level.level : "Originals", x0, 28);
        const cols = Math.max(
            1,
            Math.ceil(Math.sqrt((nodes.length * pw) / ph)),
          ),
          rows = Math.max(1, Math.ceil(nodes.length / cols));
        nodes.forEach((node, k) => {
          const p = project(
            (((k % cols) + 0.5) * pw) / cols,
            ((Math.floor(k / cols) + 0.5) * ph) / rows,
          );
          positions.set(node.key, {
            ...p,
            node,
            size: Math.max(
              1,
              Math.min(6, (pw / cols) * 0.6, (ph / rows) * 0.6),
            ),
          });
        });
        c.fillStyle = "#939795";
        c.fillText(
          nodes.filter((n) => n.kept).length + " / " + nodes.length,
          x0,
          h - 24,
        );
      } else {
        const y0 = 32 + (j * (h - 48)) / levels.length,
          left = 80,
          width = w - left - 16,
          cols = Math.max(1, Math.floor(width / 8));
        c.fillStyle = "#939795";
        c.font = "12px Geist";
        c.fillText(
          level.level ? "Level " + level.level : "Originals",
          12,
          y0 + 10,
        );
        nodes.forEach((node, k) =>
          positions.set(node.key, {
            x: left + (((k % cols) + 0.5) * width) / cols,
            y: y0 + Math.floor(k / cols) * 8,
            node,
            size: Math.min(5, (width / cols) * 0.6),
          }),
        );
      }
    });
    c.strokeStyle = "#355f58";
    c.lineWidth = 0.7;
    for (const [a, b] of model.edges) {
      const x = positions.get(a),
        y = positions.get(b);
      if (!x || !y) continue;
      c.beginPath();
      c.moveTo(x.x, x.y);
      c.lineTo(y.x, y.y);
      c.stroke();
    }
    for (const point of positions.values()) {
      const { node, x, y, size } = point;
      c.fillStyle = node.kept
        ? node.level
          ? "#87d9cb"
          : "#e2ce86"
        : "#414846";
      c.fillRect(x - size / 2, y - size / 2, size, size);
      if (node.returned) {
        c.strokeStyle = "#e8e8e5";
        c.lineWidth = 0.7;
        c.strokeRect(x - size / 2 - 1, y - size / 2 - 1, size + 2, size + 2);
      }
      if (node.key === routingFocus) {
        c.strokeStyle = "#e2ce86";
        c.lineWidth = 1;
        c.strokeRect(x - 6, y - 6, 12, 12);
      }
      routingHits.push(point);
    }
    const fallback = d.repair?.fallback_active;
    $("routing-description").textContent =
      (fallback
        ? "Unused hierarchy read; observed graph fallback supplied this step. "
        : "") +
      model.rawCount +
      " originals attended; " +
      d.memory_ids.length +
      " facts returned to the planner." +
      (model.mapped
        ? " Select a node to inspect its contents."
        : " Historical trace: node contents were not recorded.");
    const selected = routingHits.find((p) => p.node.key === routingFocus);
    $("routing-inspection").textContent = selected
      ? SomnaRouting.nodeDescription(selected.node)
      : "";
    $("layers").classList.toggle("selected", routingView === "layers");
    $("tree-view").classList.toggle("selected", routingView === "tree");
    $("layers").setAttribute("aria-pressed", String(routingView === "layers"));
    $("tree-view").setAttribute("aria-pressed", String(routingView === "tree"));
    $("routing-description").setAttribute(
      "aria-live",
      playing ? "off" : "polite",
    );
  }
  function inspectRouting(point) {
    if (!run) return;
    routingFocus = point?.node.key || null;
    if (point && window.parent !== window)
      window.parent.postMessage({ type: "somna-selection" }, location.origin);
    renderRouting(run.trajectory[cursor]);
  }

  function objectiveLabel(value) {
    return (
      {
        explore: "Explore a frontier",
        "scan-frontier": "Look around",
        "scan-no-reachable-frontier": "No reachable frontier in recall",
        "fetch-key": "Get the key",
        "open-door": "Reach a closed door",
        "matching-target": "Return to the matching object",
        "matching-target-adjacent": "At the matching object",
        "drop-for-pickup": "Put down the held object",
        "pickup-target": "Pick up the target",
        goal: "Reach the goal",
      }[value] || value.replaceAll("-", " ")
    );
  }
  function paintMaze(target, displayPose) {
    const row = run.trajectory[cursor];
    if (!row) return;
    const { c, w, h } = canvas(target),
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
      c.strokeStyle = "#495043";
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
      c.strokeStyle = "#91b5a3";
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
      c.strokeStyle = "#aba4bb";
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
        x0 + ((displayPose?.[0] ?? px) - loX + 0.5) * cell,
        y0 + ((displayPose?.[1] ?? py) - loY + 0.5) * cell,
        cell,
        displayPose?.[2] ?? d.pose[2],
      );
    }
  }
  function drawMaze() {
    const row = run.trajectory[cursor];
    if (!row) return;
    const d = row.decision;
    navigationMotion.update(
      run.live?.id || run.dataset + run.environment_id + run.seed + run.reader,
      cursor,
      row.decision.pose,
      performance.now(),
      playing && !reduceMotion.matches,
      (run.live ? streamDelay : Number($("speed").value)) * 0.8,
    );
    paintMaze($("board"), navigationMotion.sample(performance.now()).pose);
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
      objectiveLabel(d.objective) +
      " · " +
      actions[row.action] +
      (row.reward ? " · reward " + Number(row.reward).toFixed(3) : "");
    $("trace-warning").textContent =
      mode === "solution"
        ? "Official egocentric observation before this action. Black cells are unseen. The policy receives no hidden layout or true simulator position."
        : d.coverage
          ? "Outlines mark previously observed cells whose contents were omitted. Cyan marks bundle support; purple marks the plan."
          : "Visible and recalled cells. Purple marks the plan; missing facts can disconnect it.";
    $("maze-legend").hidden = mode !== "search" || !d.coverage;
    renderMazeRead(row);
    renderRouting(row);
    updateRunNotice(row);
    if (parent !== window)
      parent.postMessage({ type: "somna-frame" }, location.origin);
    const persistent =
      d.dependency?.graph_source === "active_and_explicitly_recovered_only";
    $("next-event").hidden = !d.repair && !persistent;
    $("next-event").disabled = !run.trajectory.some(
      (r, i) =>
        i > cursor &&
        (persistent
          ? r.retired_ids?.length ||
            r.lifecycle?.capacity_evicted_ids?.length ||
            r.decision.dependency?.recovered_ids?.length ||
            r.decision.dependency?.evicted_ids?.length
          : r.decision.repair?.stage !==
            run.trajectory[i - 1]?.decision.repair?.stage),
    );
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
      [
        "Prefix raw attention pairs",
        w.archive_raw_pairs ?? w.raw_attention_pairs ?? 0,
      ],
      [
        "Prefix exact + rerank scores",
        (w.exact_score_pairs || 0) +
          (w.rerank_pairs || 0) +
          (w.archive_rerank_pairs || 0),
      ],
      [
        "Prefix summary channel dots",
        w.archive_summary_dot_products ?? w.summary_dot_products ?? 0,
      ],
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
    if (d.repair)
      for (const [name, value] of [
        [
          "Recovery stage",
          [
            "Base recall",
            "Directional cues",
            "Wider candidate search",
            "Observed graph",
          ][d.repair.stage],
        ],
        ["Reads without new evidence", d.repair.no_information_reads],
        [
          "Source candidate limit",
          d.repair.candidate_budget ?? "All observed heads",
        ],
        ["Graph recovery reads so far", w.repair_graph_fallback_reads || 0],
      ])
        dlMetric(
          dl,
          name,
          typeof value === "number" ? value.toLocaleString() : value,
        );
    host.append(dl);
    dependencyDetails(d);
    $("read-description").textContent =
      row.observation.mission + ". " + objectiveLabel(d.objective) + ".";
    const prioritized = d.memory_facts
      .slice()
      .sort(
        (a, b) =>
          Number(Boolean(b.cue)) -
          Number(Boolean(a.cue)) +
          2 *
            (Number([4, 5, 6, 7, 8].includes(b.object)) -
              Number([4, 5, 6, 7, 8].includes(a.object))),
      );
    for (const f of prioritized.slice(0, 4)) {
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
      "Showing " +
      Math.min(4, d.memory_facts.length) +
      " of " +
      d.memory_facts.length +
      " returned facts. Landmarks and sample cues shown first.";
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
        ? run.dataset.startsWith("dependency-") ||
          run.dataset.startsWith("progress-")
          ? run.dataset.startsWith("progress-")
            ? ["bundle_zha", "cues_zha", "graph"]
            : ["flat_zha_mask", "flat_exact_history_mask", "graph", "full"]
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
    $("routing-panel").hidden = !maze;
    document.querySelector(".workbench").classList.toggle("single-view", !maze);
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
      ? "Seed"
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
      ? "Time includes the complete recorded episode. Different trajectories use different amounts of work."
      : "Latency includes feature extraction, retrieval, search and trace collection. Reader setup is recorded separately. Summary channel dots and raw key scores have different costs.";
    document.querySelector(".comparison .eyebrow").textContent = maze
      ? "Same task seed · same action cap"
      : "Same puzzle · same expansion budget";
    $("scope").textContent = maze
      ? "Official MiniGrid observations and a shared symbolic planner. Each frame is a recorded decision; memory contains observed cells only."
      : "Official Boxoban puzzles. Retrieved training cases guide a shared classical search.";
    if (maze) {
      $("board-label").textContent = "MINIGRID / " + run.split.toUpperCase();
      $("board-title").textContent =
        taskLabel(run.environment_id) + " / " + run.seed;
    }
  }

  function draw() {
    if (!run) return;
    navigationRevision++;
    const data = frames();
    cursor = Math.min(Math.max(0, cursor), Math.max(0, data.length - 1));
    if (!playing) {
      const u = new URL(location.href);
      u.searchParams.set("step", String(cursor));
      u.searchParams.set("view", routingView);
      history.replaceState(null, "", u);
    }
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
  routing3D = globalThis.SomnaVisuals?.create({
    canvas: $("routing-spatial"),
    readout: $("routing-readout"),
    onPick: (key) =>
      inspectRouting(routingHits.find((p) => p.node.key === key)),
  });
  if (!routing3D && routingView === "structure") routingView = "tree";
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
  $("show-development").onchange = () => {
    fillCohorts($("cohort").value);
    fillSuites();
    fillLevels();
    fillConfigs();
    safe(loadRun());
  };
  $("next-event").onclick = () => {
    pause();
    const i = run.trajectory.findIndex(
      (r, i) =>
        i > cursor &&
        (run.reader?.startsWith("persistent_")
          ? r.retired_ids?.length ||
            r.lifecycle?.capacity_evicted_ids?.length ||
            r.decision.dependency?.recovered_ids?.length ||
            r.decision.dependency?.evicted_ids?.length
          : r.decision.repair?.stage !==
            run.trajectory[i - 1]?.decision.repair?.stage),
    );
    if (i >= 0) {
      cursor = i;
      draw();
    }
  };
  $("cohort").onchange = () => {
    fillSuites();
    fillLevels();
    fillConfigs();
    safe(loadRun());
  };
  $("latest").onclick = () => {
    $("cohort").value = latestCohort();
    fillSuites();
    fillLevels();
    fillConfigs("progress_zha");
    safe(loadRun());
  };
  $("cue").onchange = () => {
    $("routing-pass").value = "";
    routingFocus = null;
    renderRouting(run.trajectory[cursor]);
  };
  $("routing-pass").onchange = () => {
    routingFocus = null;
    renderRouting(run.trajectory[cursor]);
  };
  $("layers").onclick = () => {
    routingView = "layers";
    draw();
    renderRouting(run.trajectory[cursor]);
  };
  $("structure").onclick = () => {
    routingView = "structure";
    draw();
    renderRouting(run.trajectory[cursor]);
  };
  $("tree-view").onclick = () => {
    routingView = "tree";
    draw();
    renderRouting(run.trajectory[cursor]);
  };
  $("routing").onclick = (e) => {
    const r = $("routing").getBoundingClientRect(),
      x = e.clientX - r.left,
      y = e.clientY - r.top;
    const nearest = routingHits
      .map((p) => ({ p, d: Math.hypot(p.x - x, p.y - y) }))
      .sort((a, b) => a.d - b.d)[0];
    inspectRouting(nearest?.d < 12 ? nearest.p : null);
  };
  $("routing").onkeydown = (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End", "Escape"].includes(e.key))
      return;
    e.preventDefault();
    const i = routingHits.findIndex((p) => p.node.key === routingFocus);
    if (e.key === "Escape") inspectRouting(null);
    else
      inspectRouting(
        routingHits[
          e.key === "Home"
            ? 0
            : e.key === "End"
              ? routingHits.length - 1
              : Math.max(
                  0,
                  Math.min(
                    routingHits.length - 1,
                    i + (e.key === "ArrowRight" ? 1 : -1),
                  ),
                )
        ],
      );
  };

  $("routing-spatial").onkeydown = (e) => $("routing").onkeydown(e);
  let resizeTimer;
  addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(draw, 100);
  });
  document.fonts.ready.then(draw);

  const panelChoices = (id) =>
    [...$(id).options].map((o) => ({ value: o.value, label: o.textContent }));
  function solveStart(packet) {
    pause();
    ++requestId; // A stale artifact fetch cannot replace a fresh solve.
    const c = packet.config;
    run = {
      task: "minigrid",
      dataset: "live-session",
      environment_id: c.environment,
      reader: c.reader,
      seed: c.seed,
      level_id: c.seed,
      capacity: packet.memory?.active_capacity || 96,
      split: "diagnostic",
      archive: [],
      trajectory: [],
      routing_events: {},
      routing_snapshots: {},
      result: { success: false, return: 0, steps: 0 },
      success: false,
      expanded: 0,
      expansion_limit: c.step_cap,
      wall_seconds: 0,
      live: { id: packet.id, status: packet.status, memory: packet.memory },
    };
    cursor = 0;
    headCursor = -1;
    headMap.clear();
    routingFocus = null;
    panelRouting = null;
    mode = "search";
    $("run-metrics").replaceChildren();
    $("comparison-body").replaceChildren();
    $("routing-inspection").textContent =
      "Select a node to inspect its original records.";
    $("error").hidden = true;
    $("run-notice").textContent = "Starting fresh observation-only solve";
    configureTaskDisplay();
    setRunControls(true);
    // The first published decision starts the single shared timeline.
    playing = true;
    timer = setTimeout(tick, 120);
  }
  function solveAppend(packet) {
    if (run?.live?.id !== packet.id) throw Error("Solve identity changed");
    if (packet.after !== run.trajectory.length)
      throw Error("Noncontiguous solve evidence");
    Object.assign(run.routing_events, packet.routing_events);
    Object.assign(run.routing_snapshots, packet.routing_snapshots);
    for (const row of packet.trajectory) {
      run.trajectory.push(row);
      run.archive.push(...row.new_facts);
    }
    run.live.status =
      packet.next < packet.available ? "streaming" : packet.status;
    run.live.reason = packet.reason;
    run.live.memory = packet.memory;
    run.expanded = run.trajectory.length;
    if (packet.result) {
      run.result = packet.result;
      run.success = packet.status === "solved";
    }
    if (run.trajectory.length) {
      setRunControls(false);
      draw();
    }
  }
  window.SomnaPanel = {
    evidence() {
      if (!run || !isMaze() || !run.trajectory[cursor]) return null;
      const row = run.trajectory[cursor];
      const sourceKey =
        (run.live?.id ||
          run.dataset + run.environment_id + run.seed + run.reader) +
        ":" +
        cursor;
      if (activityCache.key !== sourceKey) {
        const counts = {},
          history = [];
        for (let i = 0; i <= cursor; i++) {
          const d = run.trajectory[i].decision;
          for (const f of d.memory_facts || []) {
            const k = `${f.x},${f.y}`;
            counts[k] = (counts[k] || 0) + 1;
          }
          history.push({
            step: i,
            returned: d.memory_ids.length,
            fallback: !!d.repair?.fallback_active,
          });
        }
        activityCache = { key: sourceKey, value: { counts, history } };
      }
      return structuredClone({
        activity: activityCache.value,
        key:
          (run.live?.id ||
            run.dataset + run.environment_id + run.seed + run.reader) +
          ":" +
          cursor,
        step: cursor,
        facts: observedHeads(),
        decision: row.decision,
        objective: objectiveLabel(row.decision.objective),
        newIds: row.new_facts.map((f) => f.id),
        retiredIds: row.retired_ids || [],
        evictedIds:
          row.lifecycle?.capacity_evicted_ids ||
          row.decision.dependency?.evicted_ids ||
          [],
        memory: run.memory || run.live?.memory || null,
        replay: run.replay || null,
        supportStudy: run.support_study || null,
        source: run.live ? "fresh" : "recorded",
        action: row.action,
      });
    },
    paintNavigation(target) {
      if (!run) return false;
      if (!isMaze()) {
        paint(target, run.rows, frames()[cursor]);
        return false;
      }
      const sample = navigationMotion.sample(performance.now());
      paintMaze(target, sample.pose);
      target.dataset.visualPose = JSON.stringify(sample.pose);
      target.dataset.evidencePose = JSON.stringify(
        run.trajectory[cursor]?.decision.pose,
      );
      target.dataset.interpolating = String(sample.active);
      return sample.active;
    },
    snapshot() {
      return {
        kind: "tasks",
        navigationRevision,
        taskKind: run ? (isMaze() ? "maze" : "puzzles") : null,
        address: run
          ? {
              task: isMaze() ? "maze" : "puzzles",
              dataset: run.dataset,
              reader: run.reader || run.config,
              seed: String(run.level_id),
              env: run.environment_id,
            }
          : null,
        ready: !!run && frames().length > 0,
        live: run?.live ? { ...run.live } : null,
        solveConfig:
          run && isMaze()
            ? {
                environment: run.environment_id,
                reader: run.reader,
                seed: run.seed,
              }
            : null,
        error: $("error").hidden ? "" : $("error").textContent,
        title: $("board-title").textContent,
        status: $("run-notice").textContent,
        selection: Object.fromEntries(
          ["cohort", "suite", "level", "config", "cue", "routing-pass"].map(
            (id) => [id, $(id).value],
          ),
        ),
        choices: Object.fromEntries(
          ["cohort", "suite", "level", "config", "cue", "routing-pass"].map(
            (id) => [id, panelChoices(id)],
          ),
        ),
        cursor,
        max: run ? Math.max(0, frames().length - 1) : 0,
        playing,
        view: routingView,
        hierarchy: !!panelRouting,
        workspace: !!run?.reader?.startsWith("persistent_") && !panelRouting,
        memory: run?.live?.memory || null,
        canBranch: !$("structure").disabled,
        originals: panelRouting?.originalCount ?? null,
        read: panelRouting?.rawCount ?? null,
        inspector: $("routing-inspection").textContent,
        description: $("routing-description").textContent,
        population:
          panelRouting?.levels.map((l) => ({
            level: l.level,
            count: l.nodes.length,
            kept: l.nodes.filter((n) => n.kept).length,
          })) || [],
        returned:
          run && isMaze()
            ? run.trajectory[cursor]?.decision.memory_ids.length
            : null,
        metrics: [...$("run-metrics").children].map((d) => ({
          label: d.querySelector("span")?.textContent,
          value: d.querySelector("b")?.textContent,
        })),
        renderer: routing3D ? "three" : "canvas",
      };
    },
    command(name, payload) {
      if (name === "speed") {
        if (![120, 300, 650].includes(payload))
          throw Error("Unsupported playback speed");
        streamDelay = payload;
        return;
      }
      if (name === "solveStart") {
        solveStart(payload);
        return;
      }
      if (name === "solveAppend") {
        solveAppend(payload);
        return;
      }
      if (name === "pause") {
        pause();
        return;
      }
      if (name === "select") {
        if (
          ![
            "cohort",
            "suite",
            "level",
            "config",
            "cue",
            "routing-pass",
          ].includes(payload?.id)
        )
          throw Error("Unsupported task selector");
        const el = $(payload.id);
        if (![...el.options].some((o) => o.value === payload.value))
          throw Error("Unknown task option");
        el.value = payload.value;
        el.dispatchEvent(new Event("change"));
        return;
      }
      if (name === "step") {
        if (
          !Number.isInteger(payload) ||
          payload < 0 ||
          payload > Number($("timeline").max)
        )
          throw Error("Invalid recorded step");
        $("timeline").value = payload;
        $("timeline").dispatchEvent(new Event("input"));
        return;
      }
      if (name === "view") {
        const id = {
          layers: "layers",
          structure: "structure",
          tree: "tree-view",
        }[payload];
        if (!id || $(id).disabled) throw Error("View unavailable");
        $(id).click();
        return;
      }
      if (name === "play") {
        $("play").click();
        return;
      }
      if (name === "recovery") {
        if (!$("next-event").hidden) $("next-event").click();
        return;
      }
      if (name === "navigation") {
        if (!["observed", "recall"].includes(payload))
          throw Error("Unknown navigation view");
        pause();
        mode = payload === "recall" ? "search" : "solution";
        draw();
        return;
      }
      if (name === "map") {
        document.body.classList.toggle("show-navigation", !!payload);
        return;
      }
      if (name === "camera") {
        if (!routing3D) return;
        if (payload === "home") routing3D.reset();
        else if (payload === "focus") routing3D.focus();
        else if (payload === "replay") routing3D.replay();
        else if (payload === "orbit") {
          routing3D.controls.autoRotate =
            !routing3D.controls.autoRotate && !routing3D.reduced;
          routing3D.dirty = true;
        } else throw Error("Unknown camera action");
        return;
      }
      throw Error("Unsupported task command");
    },
  };
  safe(reload());
})();
