"use strict";
(() => {
  const $ = (id) => document.getElementById(id),
    frames = { tasks: $("task-frame"), memory: $("memory-frame") },
    controllers = {},
    states = {},
    seen = {},
    initialised = new Set();
  let selectedPanel = null,
    cueDraft = false,
    lastSelection = { tasks: "", memory: "" },
    episodeMode = true,
    episodeModel = null,
    episodeEvidence = null,
    evidenceKey = "",
    solveJob = null,
    solving = false,
    solvePolling = false,
    solveAfter = 0,
    solveRequest = false,
    resumeAttempted = false,
    selectedEpisode = null,
    navigationDirty = true,
    navigationAnimating = false,
    navigationRevision = -1;
  const episodeView =
    (new URLSearchParams(location.search).get("renderer") !== "canvas" &&
      globalThis.SomnaVisuals?.create({
        canvas: $("episode-spatial"),
        readout: $("episode-readout"),
        onPick: (id) => {
          selectedEpisode =
            episodeEvidence?.facts.find((f) => String(f.id) === id) || null;
          if (selectedEpisode) {
            selectedPanel = "episode";
            episodeView?.highlight(id);
            selection();
          }
        },
      })) ||
    null;
  if (!episodeView) {
    $("episode-spatial").hidden = true;
    $("episode-flat").hidden = false;
  }
  const requestedSolve = new URLSearchParams(location.search).get("solve");
  const keys = ["cohort", "suite", "level", "config", "cue", "routing-pass"];
  const text = (id, value) => {
    const el = $(id);
    const next = String(value ?? "—");
    if (el.textContent !== next) el.textContent = next;
  };
  const error = (e) => {
    text("dashboard-error", e.message || String(e));
    $("dashboard-error").hidden = false;
    setTimeout(() => ($("dashboard-error").hidden = true), 7000);
  };
  function command(panel, name, payload) {
    try {
      if (panel === "memory" && episodeMode) {
        if (name === "view") {
          episodeView?.setMode(payload);
          drawEpisodeFlat();
          return;
        }
        if (name === "camera") {
          if (payload === "home") episodeView?.reset();
          else if (payload === "focus") episodeView?.focus();
          else if (payload === "replay") episodeView?.replay();
          else if (payload === "orbit" && episodeView) {
            episodeView.controls.autoRotate =
              !episodeView.controls.autoRotate && !episodeView.reduced;
            episodeView.dirty = true;
          }
          return;
        }
      }
      if (!controllers[panel]) throw Error("This view is still connecting");
      controllers[panel].command(name, payload);
    } catch (e) {
      error(e);
    }
  }
  function options(id, items, value, disabled) {
    const el = $(id),
      signature = JSON.stringify(items);
    if (seen[id] !== signature) {
      el.replaceChildren(
        ...items.map((item) => {
          const o = document.createElement("option");
          o.value = item.value;
          o.textContent = item.label;
          return o;
        }),
      );
      seen[id] = signature;
    }
    if (document.activeElement !== el) el.value = value ?? "";
    el.disabled = !!disabled;
  }
  function selection() {
    const t = states.tasks,
      m = states.memory;
    if (selectedPanel === "episode" && selectedEpisode) {
      const f = selectedEpisode,
        p = episodeModel?.points.find((p) => p.id === String(f.id));
      if (!p) {
        selectedEpisode = null;
        text(
          "selection-detail",
          "Selection is outside this decision. Choose a visible fact.",
        );
        return;
      }
      text("selection-source", `Task original #${f.id}`);
      text(
        "selection-detail",
        `${p.label} · (${f.x}, ${f.y}) · ${p.detail} · observed at step ${f.observed_step}`,
      );
      $("selection-values").replaceChildren();
      return;
    }
    if (selectedPanel === "tasks" && (!t?.ready || !t?.inspector)) {
      text("selection-source", "No task selection");
      text("selection-detail", "Choose a node in the recorded hierarchy.");
      $("selection-values").replaceChildren();
      return;
    }
    if (selectedPanel === "tasks" && t?.inspector) {
      text("selection-source", "Recorded hierarchy");
      text("selection-detail", t.inspector);
      $("selection-values").replaceChildren();
      return;
    }
    if (selectedPanel === "memory" && m?.selection) {
      const s = m.selection;
      text("selection-source", "Live original #" + s.id);
      text(
        "selection-detail",
        (s.current ? (s.hot ? "Active" : "Dormant") : "Superseded") +
          " · World " +
          (s.context === 0 ? "A" : "B"),
      );
      $("selection-values").replaceChildren(
        ...Object.entries({
          Position: `${s.x.toFixed(3)}, ${s.y.toFixed(3)}`,
          Salience: s.salience.toFixed(3),
          Version: s.version,
        }).map(([key, value]) => {
          const d = document.createElement("div"),
            dt = document.createElement("dt"),
            dd = document.createElement("dd");
          dt.textContent = key;
          dd.textContent = value;
          d.append(dt, dd);
          return d;
        }),
      );
      return;
    }
  }
  function syncTasks(s) {
    $("task-loading").hidden = s.ready;
    $("retry-tasks").hidden = !s.error;
    $("task-loading").querySelector("span").textContent = s.error
      ? "Recorded view unavailable. Choose another run or retry."
      : "Opening recorded evidence";
    text(
      "task-view-name",
      s.taskKind === "puzzles"
        ? "Puzzle search"
        : s.hierarchy
          ? "Retrieval hierarchy"
          : "Evidence selection",
    );
    text("task-title", s.ready ? s.title : "");
    text("task-source", s.live ? "Fresh solve" : "Saved example");
    text("task-status", s.error || s.status || "Opening task evidence.");
    const supported = [
      "progress_zha",
      "progress_exact",
      "cues_zha",
      "cues_exact",
      "bundle_zha",
      "bundle_exact",
      "graph",
    ];
    $("solve").disabled =
      solveRequest ||
      (!solving &&
        (!s.solveConfig || !supported.includes(s.solveConfig.reader)));
    text("solve", solving ? "Stop solve □" : "Solve maze ↗");
    if (!solveJob)
      text(
        "solve-status",
        s.solveConfig
          ? "Run a fresh maze. Both structures follow each decision."
          : "Saved puzzle example. Choose a maze for a fresh solve.",
      );
    for (const key of keys)
      options(
        "task-" + key,
        s.choices[key] || [],
        s.selection[key],
        !(s.choices[key] || []).length ||
          (["cue", "routing-pass"].includes(key) && (!s.ready || !s.hierarchy)),
      );
    $("hierarchy-view").disabled = !s.ready || !s.hierarchy;
    document
      .querySelectorAll('[data-panel="tasks"]')
      .forEach(
        (b) =>
          (b.disabled = !s.ready || !s.hierarchy || s.renderer !== "three"),
      );
    $("play").disabled = !s.ready;
    for (const id of [
      "task-suite",
      "task-config",
      "task-cohort",
      "task-level",
    ]) {
      // Freeze run identity while the worker or evidence stream is active.
      if (solving) $(id).disabled = true;
    }
    $("recovery").disabled = !s.ready;
    $("timeline").disabled = !s.ready;
    if (!s.ready) {
      const c = $("navigation-preview");
      c.getContext("2d").clearRect(0, 0, c.width, c.height);
      navigationDirty = false;
      navigationAnimating = false;
      text("navigation-step", "Waiting for evidence");
    }
    if (s.ready) {
      const mini = $("navigation-preview");
      mini.hidden = !$("show-map").checked;
      if (navigationRevision !== s.navigationRevision) {
        navigationDirty = true;
        navigationRevision = s.navigationRevision;
      }
      text("navigation-step", `Decision ${s.cursor}`);
      $("task-loading").hidden = true;
      $("timeline").max = String(s.max);
      if (document.activeElement !== $("timeline"))
        $("timeline").value = String(s.cursor);
      text("cursor", s.cursor + " / " + s.max);
      text("play", s.playing ? "Pause Ⅱ" : "Play ▷");
      $("hierarchy-view").value = s.view;
      $("hierarchy-view").querySelector("[value=structure]").disabled =
        !s.canBranch;
      text(
        "task-counts",
        s.hierarchy
          ? `${s.originals} originals · ${s.read} attended · ${s.returned ?? "—"} returned`
          : s.taskKind === "puzzles"
            ? "Recorded puzzle search · retrieved examples"
            : "Returned evidence · " + (s.returned ?? "—") + " facts",
      );
      const u = new URL(location.href);
      for (const [key, value] of Object.entries({
        ...(s.live ? {} : s.address),
        step: s.cursor,
        view: s.view,
      }))
        if (value !== undefined) u.searchParams.set(key, String(value));
      if (u.href !== location.href) history.replaceState(null, "", u);
    }
    if (
      s.inspector &&
      s.inspector !== lastSelection.tasks &&
      !s.inspector.startsWith("Select a node")
    ) {
      selectedPanel = "tasks";
      lastSelection.tasks = s.inspector;
    }
  }
  function syncMemory(s) {
    $("memory-loading").hidden = s.ready;
    $("retry-memory").hidden = !s.error;
    $("memory-loading").querySelector("span").textContent = s.error
      ? "Live archive unavailable."
      : "Connecting to the live archive";
    $("memory-view").disabled = !s.ready;
    document
      .querySelectorAll('[data-panel="memory"]')
      .forEach((b) => (b.disabled = !s.ready || s.renderer !== "three"));
    text("memory-originals", s.originals);
    text("memory-hot", s.hot);
    text("memory-updates", s.updates);
    text("memory-phase", s.error || s.phase || "Connecting to archive.");
    $("memory-cycle").disabled =
      $("memory-query").disabled =
      $("memory-execute").disabled =
        !s.ready || s.busy;
    if (s.ready) {
      $("memory-loading").hidden = true;
      text("memory-state", s.busy ? "Learning offline" : "Persistent archive");
      text("memory-counts", `${s.read ?? 0} in read · ${s.cold} dormant`);
      text(
        "memory-busy",
        s.busy ? "Updating weights" : "Click a point to inspect",
      );
      $("memory-view").value = s.projection;
      if (!cueDraft) {
        $("memory-context").value = s.context;
        $("memory-action").value = s.action;
        $("mask-x").checked = s.mask[0];
        $("mask-y").checked = s.mask[1];
      }
      $("memory-tool").value = s.tool;
    }
    const signature = s.selection ? JSON.stringify(s.selection) : "";
    if (signature && signature !== lastSelection.memory) {
      selectedPanel = "memory";
      lastSelection.memory = signature;
    }
  }
  function poll() {
    if (!document.hidden) {
      for (const panel of ["tasks", "memory"])
        try {
          controllers[panel] = frames[panel].contentWindow?.SomnaPanel;
          if (panel === "memory" && episodeMode) continue;
          if (!controllers[panel]) continue;
          let s = controllers[panel].snapshot();
          if (s.ready && !initialised.has(panel)) {
            initialised.add(panel);
            if (panel === "memory")
              controllers[panel].command("tool", "inspect");
            else {
              controllers[panel].command("map", $("show-map").checked);
              controllers[panel].command("navigation", "recall");
            }
            s = controllers[panel].snapshot();
          }
          states[panel] = s;
          (panel === "tasks" ? syncTasks : syncMemory)(s);
        } catch (e) {
          text(
            panel === "tasks" ? "task-status" : "memory-phase",
            "View unavailable. Reload this dashboard.",
          );
        }
      if (episodeMode && states.tasks?.ready) renderEpisode();
      if (requestedSolve && !resumeAttempted && states.tasks?.ready) {
        resumeAttempted = true;
        resumeSolve(requestedSolve);
      }
      const ready =
        !!states.tasks?.ready &&
        (episodeMode ? !!episodeModel : !!states.memory?.ready);
      $("connection").className = "connection " + (ready ? "ready" : "partial");
      text("connection", ready ? "Connected" : "Connecting");
      selection();
    }
  }
  function renderEpisode() {
    const evidence = controllers.tasks?.evidence();
    if (!evidence) {
      if (episodeMode) {
        episodeView?.setVisible(false);
        episodeModel = null;
        episodeEvidence = null;
        evidenceKey = "";
        $("memory-loading").hidden = false;
        $("memory-loading").querySelector("span").textContent =
          "Task memory is available for maze episodes. Choose a maze to solve.";
        text("memory-counts", "No maze decision selected");
      }
      return;
    }
    if (evidence.key === evidenceKey) return;
    episodeEvidence = evidence;
    episodeModel = SomnaVisuals.taskMemoryModel(evidence);
    evidenceKey = evidence.key;
    if (episodeView) {
      episodeView.setVisible(true);
      episodeView.setData(episodeModel);
      episodeView.setMode($("memory-view").value);
    } else drawEpisodeFlat();
    text("memory-state", `Decision ${evidence.step} · observed → retrieved`);
    text(
      "memory-counts",
      `${episodeModel.sourceCount} observed · ${episodeModel.readCount} returned`,
    );
    text("memory-busy", "Select a fact to inspect");
    $("memory-view").disabled = false;
    document
      .querySelectorAll('[data-panel="memory"]')
      .forEach((b) => (b.disabled = !episodeView));
    const d = evidence.decision;
    text(
      "receipt-observe",
      `${evidence.newIds.length} new · ${d.current_facts.length} visible`,
    );
    text("receipt-retrieve", `${d.memory_ids.length} facts`);
    text(
      "receipt-plan",
      evidence.objective ||
        (d.objective || "None").replaceAll("_", " ").replaceAll("-", " "),
    );
    text(
      "receipt-act",
      [
        "Turn left",
        "Turn right",
        "Forward",
        "Pick up",
        "Drop",
        "Toggle door",
        "Done",
      ][evidence.action] || evidence.action,
    );
    text(
      "receipt-recovery",
      d.repair?.fallback_active
        ? "Graph recovery · observed map"
        : !d.memory_ids.length
          ? "Current observation only"
          : states.tasks?.solveConfig?.reader?.includes("exact") ||
              states.tasks?.solveConfig?.reader === "graph"
            ? "Exact recall · shared planner"
            : "Hierarchical recall · memory-supported plan",
    );
    $("memory-loading").hidden = true;
    if (selectedEpisode)
      selectedEpisode =
        evidence.facts.find((f) => f.id === selectedEpisode.id) || null;
  }
  function drawEpisodeFlat() {
    if (episodeView || !episodeModel) return;
    const canvas = $("episode-flat"),
      box = canvas.getBoundingClientRect(),
      c = canvas.getContext("2d");
    canvas.width = Math.max(1, box.width * devicePixelRatio);
    canvas.height = Math.max(1, box.height * devicePixelRatio);
    c.scale(devicePixelRatio, devicePixelRatio);
    c.fillStyle = "#000";
    c.fillRect(0, 0, box.width, box.height);
    const [loX, hiX, loZ, hiZ] = episodeModel.queryBounds,
      scale = Math.min(
        (box.width - 64) / (hiX - loX),
        (box.height - 64) / (hiZ - loZ),
      );
    const screen = (p) => [
      box.width / 2 + (p[0] - (loX + hiX) / 2) * scale,
      box.height / 2 + (p[2] - (loZ + hiZ) / 2) * scale,
    ];
    for (const segment of episodeModel.segments.filter((s) =>
      ["plan", "read"].includes(s.kind),
    )) {
      const a = screen(segment.from),
        b = screen(segment.to);
      c.globalAlpha = segment.kind === "plan" ? 1 : 0.12;
      c.strokeStyle = segment.color;
      c.lineWidth = segment.kind === "plan" ? 2 : 1;
      c.beginPath();
      c.moveTo(...a);
      c.lineTo(...b);
      c.stroke();
    }
    c.globalAlpha = 1;
    for (const p of episodeModel.points) {
      const x = box.width / 2 + (p.position[0] - (loX + hiX) / 2) * scale,
        y = box.height / 2 + (p.position[2] - (loZ + hiZ) / 2) * scale;
      p.screen = [x, y];
      c.fillStyle = p.color;
      c.fillRect(x - 3, y - 3, 6, 6);
    }
    text(
      "episode-readout",
      `${episodeModel.sourceCount} observed · ${episodeModel.readCount} returned · top view`,
    );
  }
  $("episode-flat").onclick = (e) => {
    const box = e.currentTarget.getBoundingClientRect(),
      x = e.clientX - box.left,
      y = e.clientY - box.top;
    const p = episodeModel?.points.find(
      (p) => Math.hypot(p.screen[0] - x, p.screen[1] - y) < 10,
    );
    if (p) {
      selectedEpisode = episodeEvidence.facts.find(
        (f) => String(f.id) === p.id,
      );
      selectedPanel = "episode";
      selection();
    }
  };
  addEventListener("resize", drawEpisodeFlat);
  $("episode-spatial").onkeydown = (e) => {
    if (
      !["ArrowLeft", "ArrowRight", "Home"].includes(e.key) ||
      !episodeModel?.points.length
    )
      return;
    e.preventDefault();
    const i = episodeModel.points.findIndex(
      (p) => p.id === String(selectedEpisode?.id),
    );
    const n =
      e.key === "Home"
        ? 0
        : (i + (e.key === "ArrowLeft" ? -1 : 1) + episodeModel.points.length) %
          episodeModel.points.length;
    const p = episodeModel.points[n];
    selectedEpisode = episodeEvidence.facts.find((f) => String(f.id) === p.id);
    selectedPanel = "episode";
    episodeView?.highlight(p.id);
    selection();
  };
  $("episode-flat").onkeydown = $("episode-spatial").onkeydown;
  async function solveApi(path, body) {
    const abort = new AbortController(),
      timer = setTimeout(() => abort.abort(), 15000);
    try {
      const response = await fetch(path, {
        method: body === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: abort.signal,
      });
      const data = await response.json();
      if (!response.ok) throw Error(data.error || "Solve request failed");
      if (data.schema !== "somna-solve-v1")
        throw Error("Unexpected solver response");
      return data;
    } finally {
      clearTimeout(timer);
    }
  }
  async function readSolve() {
    if (!solveJob || solvePolling) return;
    solvePolling = true;
    try {
      const requestJob = solveJob;
      const packet = await solveApi(
        `/api/solve?id=${encodeURIComponent(requestJob)}&after=${solveAfter}`,
      );
      if (requestJob !== solveJob) return;
      controllers.tasks.command("solveAppend", packet);
      solveAfter = packet.next;
      const caughtUp = packet.next === packet.available;
      solving = packet.status === "running" || !caughtUp;
      const label =
        {
          running: "Solving",
          solved: "Solved",
          cancelled: "Stopped",
          limited: "Budget reached",
          failed: "Solve failed",
        }[packet.status] || packet.status;
      text(
        "solve-status",
        `${label} · ${packet.available} actions computed${packet.reason ? " · " + packet.reason : ""}`,
      );
      poll();
      if (!caughtUp || solving) setTimeout(readSolve, caughtUp ? 250 : 10);
    } catch (e) {
      // Never launch a duplicate job on a failed poll. The same id remains
      // available for cancellation/retry; the last valid evidence is retained.
      error(e);
      text(
        "solve-status",
        "Connection interrupted. Stop the run or retry reading its evidence.",
      );
      $("solve-retry").hidden = false;
    } finally {
      solvePolling = false;
    }
  }
  async function resumeSolve(identifier) {
    solveRequest = true;
    try {
      const packet = await solveApi(
        `/api/solve?id=${encodeURIComponent(identifier)}&after=0`,
      );
      solveJob = packet.id;
      solveAfter = 0;
      solving = true;
      controllers.tasks.command("solveStart", packet);
      controllers.tasks.command("speed", Number($("solve-speed").value));
      evidenceKey = "";
      readSolve();
    } catch (e) {
      text("solve-status", "Previous solve expired. Start a fresh maze.");
      error(e);
      const u = new URL(location.href);
      u.searchParams.delete("solve");
      history.replaceState(null, "", u);
    } finally {
      solveRequest = false;
    }
  }
  $("solve").onclick = async () => {
    if (solveRequest) return;
    solveRequest = true;
    $("solve").disabled = true;
    try {
      if (solving) {
        await solveApi("/api/solve/cancel", { id: solveJob });
        text("solve-status", "Stopping after the current decision…");
        if (!solvePolling) readSolve();
        return;
      }
      const config = states.tasks?.solveConfig,
        seed = Number($("solve-seed").value),
        cap = Number($("solve-cap").value);
      if (!config || !Number.isInteger(seed) || seed < 0 || seed >= 2 ** 31)
        throw Error("Choose a maze and a valid integer seed");
      const packet = await solveApi("/api/solve", {
        ...config,
        seed,
        step_cap: cap,
      });
      solveJob = packet.id;
      const address = new URL(location.href);
      address.searchParams.set("solve", solveJob);
      history.replaceState(null, "", address);
      solveAfter = 0;
      solving = true;
      evidenceKey = "";
      episodeModel = null;
      episodeEvidence = null;
      episodeView?.setVisible(false);
      selectedEpisode = null;
      $("memory-loading").hidden = false;
      $("memory-loading").querySelector("span").textContent =
        "Waiting for this solve's first observation";
      controllers.tasks.command("solveStart", packet);
      controllers.tasks.command("speed", Number($("solve-speed").value));
      $("memory-source").value = "episode";
      $("memory-source").dispatchEvent(new Event("change"));
      text("solve-status", "Starting fresh maze · waiting for first decision");
      $("solve-retry").hidden = true;
      if (innerWidth < 600) {
        document.body.classList.remove("controls-open");
        $("rail-toggle").setAttribute("aria-expanded", "false");
      }
      readSolve();
    } catch (e) {
      error(e);
      text("solve-status", e.message);
    } finally {
      solveRequest = false;
      poll();
    }
  };
  $("solve-retry").onclick = () => {
    $("solve-retry").hidden = true;
    readSolve();
  };
  $("solve-speed").onchange = (e) =>
    command("tasks", "speed", Number(e.target.value));
  for (const key of keys)
    $("task-" + key).addEventListener("change", (e) => {
      if (solving && !["cue", "routing-pass"].includes(key)) return;
      if (!["cue", "routing-pass"].includes(key)) {
        solveJob = null;
        evidenceKey = "";
        const u = new URL(location.href);
        u.searchParams.delete("solve");
        history.replaceState(null, "", u);
      }
      command("tasks", "select", { id: key, value: e.target.value });
    });
  $("play").onclick = () => command("tasks", "play");
  $("timeline").oninput = (e) =>
    command("tasks", "step", Number(e.target.value));
  $("recovery").onclick = () => command("tasks", "recovery");
  $("hierarchy-view").onchange = (e) =>
    command("tasks", "view", e.target.value);
  $("memory-view").onchange = (e) => command("memory", "view", e.target.value);
  $("show-map").onchange = (e) => {
    navigationDirty = true;
    command("tasks", "map", e.target.checked);
  };
  $("navigation").onchange = (e) =>
    command("tasks", "navigation", e.target.value);
  $("memory-source").onchange = (e) => {
    episodeMode = e.target.value === "episode";
    $("archive-actions").hidden = episodeMode;
    $("episode-field").hidden = !episodeMode;
    frames.memory.hidden = episodeMode;
    episodeView?.setVisible(episodeMode);
    text(
      "memory-source-label",
      episodeMode ? "Task memory" : "Independent archive",
    );
    text(
      "field-source-note",
      episodeMode
        ? "Same episode · same step"
        : "Separate continuous experiment",
    );
    text("field-key-a", episodeMode ? "Observed" : "World A");
    text("field-key-b", episodeMode ? "Retrieved" : "World B");
    if (!episodeMode && !frames.memory.getAttribute("src"))
      frames.memory.src =
        "/live/?embed=1" +
        (params.get("renderer") === "canvas" ? "&renderer=canvas" : "");
    if (episodeMode) {
      evidenceKey = "";
      poll();
    }
  };
  $("memory-cycle").onclick = () => command("memory", "action", "cycle");
  $("memory-execute").onclick = () =>
    command("memory", "action", $("memory-operation").value);
  $("memory-query").onclick = () => {
    command("memory", "query", {
      context: $("memory-context").value,
      action: $("memory-action").value,
      mask: [$("mask-x").checked, $("mask-y").checked],
    });
    cueDraft = false;
  };
  for (const id of ["memory-context", "memory-action", "mask-x", "mask-y"])
    $(id).onchange = () => (cueDraft = true);
  $("memory-tool").onchange = (e) => command("memory", "tool", e.target.value);
  document.querySelectorAll("[data-camera]").forEach(
    (button) =>
      (button.onclick = () => {
        command(button.dataset.panel, "camera", button.dataset.camera);
        button.closest("details").open = false;
      }),
  );
  $("layout").onchange = (e) => {
    $("workspace").dataset.layout = e.target.value;
    const u = new URL(location.href);
    u.searchParams.set("layout", e.target.value);
    history.replaceState(null, "", u);
  };
  $("rail-toggle").onclick = () => {
    const open = document.body.classList.toggle("controls-open");
    $("rail-toggle").setAttribute("aria-expanded", String(open));
  };
  window.addEventListener("message", (e) => {
    if (
      e.origin === location.origin &&
      e.source === frames.tasks.contentWindow &&
      e.data?.type === "somna-frame"
    ) {
      poll();
      return;
    }
    if (e.origin !== location.origin || e.data?.type !== "somna-selection")
      return;
    for (const panel of ["tasks", "memory"])
      if (e.source === frames[panel].contentWindow) {
        selectedPanel = panel;
        selection();
      }
  });
  const params = new URLSearchParams(location.search),
    defaults = {
      task: "maze",
      dataset: "progress-evaluation-v2",
      reader: "progress_zha",
      seed: "3002",
      env: "MiniGrid-KeyCorridorS6R3-v0",
      step: "0",
      view: "layers",
    };
  const taskParams = new URLSearchParams(
    Object.entries(defaults).map(([key, value]) => [
      key,
      params.get(key) || value,
    ]),
  );
  taskParams.set("embed", "1");
  if (params.get("renderer") === "canvas") taskParams.set("renderer", "canvas");
  frames.tasks.src = "/task/?" + taskParams;
  frames.memory.hidden = true;
  $("memory-loading").hidden = true;
  if (["both", "hierarchy", "memory"].includes(params.get("layout"))) {
    $("layout").value = params.get("layout");
    $("workspace").dataset.layout = params.get("layout");
  }
  $("retry-tasks").onclick = () => {
    initialised.delete("tasks");
    frames.tasks.contentWindow.location.reload();
  };
  $("retry-memory").onclick = () => {
    initialised.delete("memory");
    frames.memory.contentWindow.location.reload();
  };
  function navigationFrame() {
    if (
      !document.hidden &&
      !$("navigation-preview").hidden &&
      controllers.tasks?.paintNavigation &&
      (navigationDirty || navigationAnimating)
    ) {
      navigationAnimating = controllers.tasks.paintNavigation(
        $("navigation-preview"),
      );
      navigationDirty = false;
    }
    requestAnimationFrame(navigationFrame);
  }
  new ResizeObserver(() => {
    navigationDirty = true;
  }).observe($("navigation-preview"));
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      navigationDirty = true;
      poll();
    }
  });
  poll();
  requestAnimationFrame(navigationFrame);
  setInterval(poll, 500);
})();
