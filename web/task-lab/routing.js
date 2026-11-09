"use strict";
(function (root) {
  function routingModel(route, heads, returnedIds) {
    const byId = new Map(heads.map((f) => [f.id, f])),
      returned = new Set(returnedIds),
      raw = new Set(route.selected_fact_ids || []),
      spans = new Map(
        (route.node_spans || []).map((s) => [s.level + ":" + s.index, s]),
      );
    const indexed = route.index_fact_ids?.map((id) => {
        if (!byId.has(id))
          throw Error("Routing source is outside the observed prefix");
        return byId.get(id);
      }),
      mapped = Boolean(indexed && Array.isArray(route.node_spans));
    for (const id of raw)
      if (!byId.has(id))
        throw Error("Attended original is outside the observed prefix");
    for (const span of spans.values())
      if (
        !Number.isInteger(span.start) ||
        !Number.isInteger(span.stop) ||
        span.start < 1 ||
        span.stop <= span.start ||
        !indexed ||
        span.stop > indexed.length + 1
      )
        throw Error("Invalid recorded node span");
    const levels = (route.steps || [])
      .slice()
      .sort((a, b) => b.level - a.level)
      .map((step) => {
        const kept = new Set(step.selected);
        return {
          level: step.level,
          nodes: step.candidates.map((index, i) => {
            const key = step.level + ":" + index,
              span = spans.get(key);
            if (mapped && !span) throw Error("Missing recorded node span");
            return {
              key,
              level: step.level,
              index,
              kept: kept.has(index),
              score: step.scores[i],
              span,
              facts:
                mapped && span
                  ? indexed.slice(span.start - 1, span.stop - 1)
                  : [],
              returned: false,
            };
          }),
        };
      });
    const originals =
      indexed ||
      [...raw].map((id) => {
        if (!byId.has(id))
          throw Error("Original is outside the observed prefix");
        return byId.get(id);
      });
    levels.push({
      level: 0,
      nodes: originals.map((fact, index) => ({
        key: "0:" + index,
        level: 0,
        index,
        span: indexed ? { start: index + 1, stop: index + 2 } : null,
        kept: raw.has(fact.id),
        returned: returned.has(fact.id),
        facts: [fact],
      })),
    });
    const edges = [];
    if (mapped)
      for (let i = 0; i < levels.length - 1; i++)
        for (const p of levels[i].nodes)
          if (p.kept && p.span)
            for (const c of levels[i + 1].nodes)
              if (
                c.span &&
                c.span.start >= p.span.start &&
                c.span.stop <= p.span.stop
              )
                edges.push([p.key, c.key]);
    return {
      levels,
      edges,
      mapped,
      originalCount: indexed?.length || heads.length,
      rawCount: raw.size,
      returnedCount: heads.filter((f) => returned.has(f.id)).length,
    };
  }
  function resolveEvent(run, route) {
    if (!Object.hasOwn(route, "route_ref")) return route;
    const event = run.routing_events?.[route.route_ref];
    if (typeof route.route_ref !== "string" || !event)
      throw Error("Recorded routing event is unavailable");
    return event;
  }
  function resolveSnapshot(run, route) {
    if (!run.routing_snapshots) return route;
    const layout = run.routing_snapshots[route.snapshot_id];
    if (!layout) throw Error("Recorded routing snapshot is unavailable");
    return { ...route, ...layout };
  }
  function cueLabel(index, mission, repair) {
    return (
      repair?.cues?.find((c) => c.query_index === index)?.label ||
      (index === 0
        ? "Local position"
        : index === 1
          ? "Mission"
          : mission.includes("matching") && index === 2
            ? "Remembered sample"
            : "Cue " + (index + 1))
    );
  }
  function nodeDescription(node) {
    const names = {
        1: "empty",
        2: "wall",
        3: "floor",
        4: "door",
        5: "key",
        6: "ball",
        7: "box",
        8: "goal",
        9: "lava",
        10: "agent",
      },
      counts = new Map();
    for (const f of node.facts) {
      const name = f.cue ? "sample cue" : names[f.object] || "cell";
      counts.set(name, (counts.get(name) || 0) + 1);
    }
    return (
      (node.level
        ? "L" + node.level + " / node " + node.index
        : "Original #" + node.facts[0]?.id) +
      " · " +
      ([...counts].map(([n, c]) => c + " " + n).join(", ") ||
        "constituents not recorded") +
      (Number.isFinite(node.score) ? " · score " + node.score.toFixed(3) : "")
    );
  }
  const api = {
    routingModel,
    cueLabel,
    nodeDescription,
    resolveSnapshot,
    resolveEvent,
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.SomnaRouting = api;
})(globalThis);
