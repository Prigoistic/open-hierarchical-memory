import test from "node:test";
import assert from "node:assert/strict";
import {
  memoryModel,
  hierarchyModel,
  COLORS,
  indexHierarchyModel,
  arborHierarchyModel,
} from "../src/models.mjs";
const node = (id, context = 0) => ({
  id,
  context,
  x: 0.1 * id,
  y: -0.2,
  next_x: 0.1 * id + 0.08,
  next_y: -0.16,
  salience: 0.5,
  current: true,
  hot: true,
});
const state = () => ({
  revision: 3,
  tick: 4,
  nodes: [node(17), node(28, 1)],
  query: {
    cue: { position: [0.3, -0.4], mask: [true, true], context: 0 },
    selected_ids: [17],
    prediction: [0.07, 0.02],
  },
});
const freeze = (o) => {
  if (o && typeof o === "object") {
    Object.freeze(o);
    Object.values(o).forEach(freeze);
  }
  return o;
};
test("memory coordinates, contexts, original IDs and reads come from immutable source", () => {
  const source = freeze(state()),
    m = memoryModel(source);
  assert.deepEqual(
    m.points.map((p) => p.id),
    ["17", "28"],
  );
  assert.deepEqual(m.points[0].position, [source.nodes[0].x, 0.12, -0.2]);
  assert.deepEqual(m.points[1].position, [source.nodes[1].x, 1.2 + 0.12, -0.2]);
  assert.equal(m.points[0].color, COLORS.gold);
  assert.equal(m.points[1].color, COLORS.b);
  assert.equal(m.sourceCount, 2);
  assert.equal(m.readCount, 1);
  assert.equal(m.segments.filter((s) => s.kind === "transition").length, 2);
  assert.deepEqual(
    m.segments.find((s) => s.kind === "read").to,
    m.points[0].position,
  );
});
test("salience height is capped and superseded facts do not gain transition arrows", () => {
  const s = state();
  s.nodes[0].salience = 100;
  s.nodes[1].current = false;
  const m = memoryModel(s);
  assert.equal(m.points[0].position[1], 0.48);
  assert.equal(m.points[1].dim, true);
  assert.equal(m.segments.filter((s) => s.kind === "transition").length, 1);
});
test("partial cues use a stripe and read origins do not expose the unknown coordinate", () => {
  const s = state();
  s.query.cue.mask = [true, false];
  const m = memoryModel(s);
  assert.equal(m.anchors[0].label, "Partial cue");
  assert.equal(m.anchors[0].position[2], 0);
  assert.deepEqual(
    m.segments.find((s) => s.kind === "cue").from,
    [0.3, 0.018, -1],
  );
  assert.deepEqual(
    m.segments.find((s) => s.kind === "read").from,
    [0.3, 0.018, -0.2],
  );
  assert.equal(
    m.segments.some((s) => s.kind === "prediction"),
    false,
  );
});
test("fully unknown position does not imply a point cue or a hidden-coordinate prediction", () => {
  const s = state();
  s.query.cue.mask = [false, false];
  const m = memoryModel(s);
  assert.equal(m.anchors.length, 0);
  assert.equal(
    m.segments.some((s) => ["read", "cue", "prediction"].includes(s.kind)),
    false,
  );
});
test("unknown context marks both available planes without inventing a context", () => {
  const s = state();
  s.query.cue.context = null;
  s.query.selected_ids = [28];
  const m = memoryModel(s);
  assert.equal(m.anchors.length, 2);
  assert.equal(m.segments.find((s) => s.kind === "read").from[1], 1.218);
  assert.equal(
    m.segments.some((s) => s.kind === "prediction"),
    false,
  );
});
test("recalled displacement is separate from source transitions", () => {
  const m = memoryModel(state()),
    p = m.segments.find((s) => s.kind === "prediction");
  assert.deepEqual(p.from, [0.3, 0.025, -0.4]);
  assert.deepEqual(p.to, [0.37, 0.025, -0.38]);
  assert.equal(p.color, COLORS.white);
});
test("unknown read IDs and nonfinite coordinates fail instead of fabricating geometry", () => {
  const s = state();
  s.query.selected_ids = [999];
  assert.throws(() => memoryModel(s), /missing/);
  const b = state();
  b.nodes[0].x = NaN;
  assert.throws(() => memoryModel(b), /Nonfinite/);
});
const hierarchy = () => ({
  mapped: true,
  originalCount: 2,
  rawCount: 1,
  edges: [["1:0", "0:0"]],
  levels: [
    {
      level: 0,
      nodes: [
        {
          key: "0:0",
          level: 0,
          index: 0,
          facts: [{ id: 17, x: 8, y: 16 }],
          kept: true,
          returned: true,
          score: 0.5,
        },
      ],
    },
    {
      level: 1,
      nodes: [
        {
          key: "1:0",
          level: 1,
          index: 0,
          facts: [
            { id: 17, x: 8, y: 16 },
            { id: 28, x: 24, y: 32 },
          ],
          kept: true,
          returned: false,
          score: 0.2,
        },
      ],
    },
  ],
});
test("hierarchy points use original source coordinates and exact recorded group centroids", () => {
  const h = freeze(hierarchy()),
    m = hierarchyModel(h, "source-key");
  assert.equal(m.key, "source-key");
  assert.equal(m.sourceCount, 2);
  assert.equal(m.readCount, 1);
  assert.deepEqual(m.points[0].position, [1, 0, 2]);
  assert.equal(m.points[0].returned, true);
  assert.deepEqual(m.points[1].position, [2, 0.85, 3]);
  assert.deepEqual(m.segments[0].from, m.points[1].position);
  assert.deepEqual(m.segments[0].to, m.points[0].position);
});
test("historical traces without source spans do not get invented spatial geometry", () => {
  assert.throws(
    () => hierarchyModel({ mapped: false }, "old"),
    /Recorded node spans/,
  );
  const h = hierarchy();
  h.edges.push(["unknown", "0:0"]);
  assert.throws(() => hierarchyModel(h, "bad"), /Unknown hierarchy edge/);
  const b = hierarchy();
  b.levels[0].nodes[0].facts = [];
  assert.throws(() => hierarchyModel(b, "empty"), /no observed source/);
});

test("archive identity invalidates cached geometry even with matching ticks and original IDs", () => {
  const a = state(),
    b = state();
  a.archive = { checksum: "archive-a" };
  b.archive = { checksum: "archive-b" };
  assert.notEqual(memoryModel(a).key, memoryModel(b).key);
});
test("offline replay rings mark only the recorded sources of the active update", () => {
  const s = state();
  s.sleep = { busy: true, trace: [{ sources: [28] }] };
  assert.deepEqual(
    memoryModel(s)
      .points.filter((p) => p.replayed)
      .map((p) => p.id),
    ["28"],
  );
  s.sleep.busy = false;
  assert.equal(
    memoryModel(s).points.some((p) => p.replayed),
    false,
  );
});

function mappedHierarchy() {
  const a = { id: 17, x: 8, y: 16, object: 4, color: 0, state: 2 },
    b = { id: 28, x: 24, y: 32, object: 5, color: 2, state: 0 };
  return {
    mapped: true,
    originalCount: 2,
    rawCount: 1,
    edges: [
      ["1:0", "0:0"],
      ["1:0", "0:1"],
    ],
    levels: [
      {
        level: 1,
        nodes: [
          {
            key: "1:0",
            level: 1,
            index: 0,
            facts: [a, b],
            kept: true,
            returned: false,
            score: 0.23,
          },
        ],
      },
      {
        level: 0,
        nodes: [
          {
            key: "0:0",
            level: 0,
            index: 0,
            facts: [a],
            kept: true,
            returned: true,
          },
          {
            key: "0:1",
            level: 0,
            index: 1,
            facts: [b],
            kept: false,
            returned: false,
          },
        ],
      },
    ],
  };
}
test("ordinal atlas preserves original IDs, five actual fields and recorded edge ownership", () => {
  const h = freeze(mappedHierarchy()),
    m = indexHierarchyModel(h, "index");
  assert.equal(m.sourceCount, 2);
  assert.equal(m.readCount, 1);
  assert.deepEqual(
    m.points.map((p) => p.id),
    ["1:0", "0:0", "0:1"],
  );
  assert.equal(m.points[1].fields.length, 5);
  assert.equal(m.points[1].fields.find((f) => f.name === "object").value, 4);
  for (let i = 0; i < h.edges.length; i++) {
    const [a, b] = h.edges[i];
    assert.deepEqual(
      m.segments[i].from,
      m.points.find((p) => p.id === a).position,
    );
    assert.deepEqual(
      m.segments[i].to,
      m.points.find((p) => p.id === b).position,
    );
  }
  assert.equal(
    m.points[0].position[0],
    (m.points[1].position[0] + m.points[2].position[0]) / 2,
  );
  assert.equal(m.readout[0].kept, 1);
  assert.equal(m.readout[1].count, 2);
});
test("ordinal atlas refuses member IDs absent from its indexed originals", () => {
  const h = mappedHierarchy();
  h.levels[0].nodes[0].facts.push({ id: 999, x: 1, y: 2 });
  assert.throws(() => indexHierarchyModel(h, "bad"), /Missing original/);
});
test("branch display preserves topology and produces finite separated display coordinates", () => {
  const h = freeze(mappedHierarchy()),
    a = arborHierarchyModel(h, "arbor"),
    b = indexHierarchyModel(h, "index");
  assert.equal(a.layout, "arbor");
  assert.equal(a.planes.length, 0);
  assert.equal(a.segments.length, h.edges.length);
  assert.deepEqual(
    a.points.map((p) => p.id),
    b.points.map((p) => p.id),
  );
  assert.notDeepEqual(a.points[1].position, a.points[2].position);
  assert.ok(a.points.every((p) => p.position.every(Number.isFinite)));
  assert.ok(a.segments.every((s) => Number.isFinite(s.radius) && s.radius > 0));
});
test("ending an offline update invalidates the replay-source cache at the same model tick", () => {
  const s = state();
  s.sleep = { busy: true, trace: [{ sources: [28] }] };
  const a = memoryModel(s);
  s.sleep.busy = false;
  const b = memoryModel(s);
  assert.notEqual(a.key, b.key);
  assert.equal(
    b.points.some((p) => p.replayed),
    false,
  );
});
test("portrait atlas changes display columns while preserving IDs and recorded edge topology", () => {
  const h = freeze(mappedHierarchy()),
    wide = indexHierarchyModel(h, "wide"),
    portrait = indexHierarchyModel(h, "portrait", { columns: 12 });
  assert.deepEqual(
    wide.points.map((p) => p.id),
    portrait.points.map((p) => p.id),
  );
  assert.equal(wide.segments.length, portrait.segments.length);
  assert.notEqual(wide.key, portrait.key);
  assert.throws(
    () => indexHierarchyModel(h, "bad", { columns: 0 }),
    /Invalid ordinal/,
  );
});

test("task memory follows current observed heads, exact returned ids and plan", async () => {
  const { taskMemoryModel } = await import("../src/models.mjs");
  const evidence = freeze({
    key: "run:3",
    step: 3,
    newIds: [2],
    facts: [
      { id: 1, x: 0, y: 0, object: 2, color: 0, state: 0, observed_step: 0 },
      { id: 2, x: 2, y: 1, object: 4, color: 1, state: 2, observed_step: 3 },
    ],
    decision: {
      pose: [1, 1, 0],
      memory_ids: [2],
      plan_fact_ids: [2],
      plan: [
        [1, 1],
        [2, 1],
      ],
    },
  });
  const model = taskMemoryModel(evidence);
  assert.equal(model.sourceCount, 2);
  assert.equal(model.readCount, 1);
  assert.deepEqual(
    model.points.map((p) => p.id),
    ["1", "2"],
  );
  assert.deepEqual(model.points[1].position, [0.25, 0.7, 0.125]);
  assert.equal(model.points[1].color, COLORS.violet);
  assert.equal(model.segments.filter((s) => s.kind === "read").length, 1);
  assert.equal(model.segments.filter((s) => s.kind === "plan").length, 1);
  assert.match(model.heightLabel, /observed \/ returned/);
  const invalid = structuredClone(evidence);
  invalid.facts[1].observed_step = 4;
  assert.throws(() => taskMemoryModel(invalid), /Future fact/);
  invalid.facts[1].observed_step = 3;
  invalid.decision.memory_ids = [999];
  assert.throws(() => taskMemoryModel(invalid), /missing from observed/);
});
