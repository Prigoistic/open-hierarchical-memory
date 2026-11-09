"use strict";
const assert = require("node:assert/strict");
const {
  routingModel,
  cueLabel,
  nodeDescription,
  resolveSnapshot,
  resolveEvent,
} = require(
  require("node:path").resolve(process.argv[2] || "web/task-lab/routing.js"),
);
const heads = Array.from({ length: 16 }, (_, i) => ({
  id: 100 + i * 7,
  x: i,
  y: 0,
  object: i === 3 ? 5 : 1,
  color: 0,
  cue: i === 3,
}));
const route = {
  index_fact_ids: heads.map((f) => f.id),
  node_spans: [
    { level: 2, index: 0, start: 1, stop: 17 },
    { level: 1, index: 0, start: 1, stop: 5 },
    { level: 1, index: 1, start: 5, stop: 9 },
    { level: 1, index: 2, start: 9, stop: 13 },
    { level: 1, index: 3, start: 13, stop: 17 },
  ],
  steps: [
    { level: 2, candidates: [0], selected: [0], scores: [1.25] },
    { level: 1, candidates: [0, 1, 2, 3], selected: [0], scores: [4, 3, 2, 1] },
  ],
  selected_fact_ids: [heads[3].id],
};
const m = routingModel(route, heads, [heads[3].id, heads[8].id]);
assert.deepEqual(
  m.levels[1].nodes[0].facts.map((f) => f.id),
  heads.slice(0, 4).map((f) => f.id),
);
assert.equal(m.edges.filter(([a]) => a === "2:0").length, 4);
assert.equal(m.edges.filter(([a]) => a === "1:0").length, 4);
assert.equal(
  m.edges.some(([a]) => a === "1:1"),
  false,
);
assert.equal(m.levels.at(-1).nodes[8].returned, true);
assert.equal(m.levels.at(-1).nodes[8].kept, false);
assert.equal(m.rawCount, 1);
assert.equal(m.returnedCount, 2);
assert.match(nodeDescription(m.levels[1].nodes[0]), /sample cue/);
const historical = routingModel(
  { ...route, index_fact_ids: undefined, node_spans: undefined },
  heads,
  [],
);
assert.equal(historical.mapped, false);
assert.deepEqual(historical.edges, []);
assert.equal(historical.levels[0].nodes[0].facts.length, 0);
assert.throws(
  () => routingModel({ ...route, index_fact_ids: [99999] }, heads, []),
  /observed prefix/,
);
assert.equal(cueLabel(0, "go to goal"), "Local position");
assert.equal(
  cueLabel(3, "go to goal", {
    cues: [{ query_index: 3, label: "Search west" }],
  }),
  "Search west",
);

assert.throws(
  () =>
    routingModel(
      { ...route, node_spans: route.node_spans.slice(1) },
      heads,
      [],
    ),
  /Missing recorded node span/,
);

assert.throws(
  () => resolveSnapshot({ routing_snapshots: {} }, { snapshot_id: "missing" }),
  /snapshot is unavailable/,
);
assert.equal(resolveSnapshot({}, route), route);
assert.deepEqual(
  resolveSnapshot(
    { routing_snapshots: { test: { index_fact_ids: [100] } } },
    { snapshot_id: "test" },
  ).index_fact_ids,
  [100],
);
assert.equal(
  resolveEvent({ routing_events: { actual: route } }, { route_ref: "actual" }),
  route,
);
assert.throws(
  () => resolveEvent({ routing_events: {} }, { route_ref: "missing" }),
  /event is unavailable/,
);
assert.equal(resolveEvent({}, route), route);
console.log(
  JSON.stringify({
    all_passed: true,
    checks: [
      "recorded spans",
      "kept edges",
      "raw and returned distinction",
      "historical limits",
      "observed prefix ownership",
      "cue labels",
    ],
    scope:
      "Recorded span membership, branch connections, returned/raw distinction, historical metadata limits, observed-prefix ownership and actual cue labels",
  }),
);
