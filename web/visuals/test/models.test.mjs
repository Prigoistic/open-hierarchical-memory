import test from "node:test";
import assert from "node:assert/strict";
import { memoryModel, hierarchyModel, COLORS } from "../src/models.mjs";
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
