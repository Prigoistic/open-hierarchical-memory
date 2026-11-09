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
    lastSelection = { tasks: "", memory: "" };
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
          ? "Hierarchical read"
          : "Evidence selection",
    );
    text("task-title", s.ready ? s.title : "");
    text("task-status", s.error || s.status || "Opening recorded evidence.");
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
    $("recovery").disabled = !s.ready;
    $("timeline").disabled = !s.ready;
    if (s.ready) {
      const mini = $("navigation-preview"),
        source = frames.tasks.contentDocument?.querySelector("#board");
      mini.hidden = !$("show-map").checked;
      if (source?.width && source?.height) {
        const c = mini.getContext("2d"),
          scale = Math.min(
            mini.width / source.width,
            mini.height / source.height,
          );
        c.clearRect(0, 0, mini.width, mini.height);
        c.drawImage(
          source,
          (mini.width - source.width * scale) / 2,
          (mini.height - source.height * scale) / 2,
          source.width * scale,
          source.height * scale,
        );
      }

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
        ...s.address,
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
      const ready = !!states.tasks?.ready && !!states.memory?.ready;
      $("connection").className = "connection " + (ready ? "ready" : "partial");
      text("connection", ready ? "Both views connected" : "Connecting views");
      selection();
    }
  }
  for (const key of keys)
    $("task-" + key).addEventListener("change", (e) =>
      command("tasks", "select", { id: key, value: e.target.value }),
    );
  $("play").onclick = () => command("tasks", "play");
  $("timeline").oninput = (e) =>
    command("tasks", "step", Number(e.target.value));
  $("recovery").onclick = () => command("tasks", "recovery");
  $("hierarchy-view").onchange = (e) =>
    command("tasks", "view", e.target.value);
  $("memory-view").onchange = (e) => command("memory", "view", e.target.value);
  $("show-map").onchange = (e) => command("tasks", "map", e.target.checked);
  $("navigation").onchange = (e) =>
    command("tasks", "navigation", e.target.value);
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
      step: "51",
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
  frames.memory.src =
    "/live/?embed=1" +
    (params.get("renderer") === "canvas" ? "&renderer=canvas" : "");
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
  poll();
  setInterval(poll, 500);
})();
