import test from "node:test";
import assert from "node:assert/strict";
import { activityColor, activityModel } from "../src/activity.mjs";

const evidence = () => ({
  key: "run-a:3",
  source: "recorded",
  step: 3,
  facts: [
    { id: 20, x: 0, y: 0, observed_step: 0 },
    { id: 31, x: 1, y: 0, observed_step: 2 },
  ],
  decision: {
    pose: [0, 0, 1],
    memory_ids: [31],
    plan: [
      [0, 0],
      [1, 0],
    ],
  },
  activity: {
    counts: { "0,0": 0, "1,0": 4 },
    history: [{ step: 0, returned: 0 }],
  },
});
const freeze = (value) => {
  if (value && typeof value === "object") {
    Object.freeze(value);
    Object.values(value).forEach(freeze);
  }
  return value;
};

test("activity height and colour map actual per-location returns while retaining original IDs", () => {
  const input = freeze(evidence()),
    m = activityModel(input);
  assert.deepEqual(
    m.points.map((p) => p.id),
    ["20", "31"],
  );
  assert.deepEqual(
    m.points.map((p) => p.position[1]),
    [0, 2.6],
  );
  assert.deepEqual(
    m.points.map((p) => p.selected),
    [false, true],
  );
  assert.equal(m.stats.maximum, 4);
  assert.equal(m.points[0].color, activityColor(0));
  assert.equal(m.points[1].color, activityColor(1));
  assert.equal(m.points[1].fields[1].value, 4);
  assert.deepEqual(
    m.segments.find((s) => s.kind === "read").to,
    m.points[1].position,
  );
  assert.equal(m.segments.filter((s) => s.kind === "plan").length, 1);
  assert.equal(m.sourceCount, input.facts.length);
  assert.equal(m.readCount, input.decision.memory_ids.length);
});

test("dense render geometry is bounded to observed cells and linked to its source, not new memories", () => {
  const input = evidence(),
    m = activityModel(input);
  assert.equal(m.samples.length, input.facts.length * 49);
  assert.equal(m.stats.triangles, input.facts.length * 72);
  for (const sample of m.samples) {
    const f = input.facts.find((f) => f.id === sample.sourceId);
    assert.ok(f);
    assert.ok(Math.abs(sample.position[0] / 0.28 - f.x) <= 0.5 + 1e-12);
    assert.ok(Math.abs(sample.position[2] / 0.28 - f.y) <= 0.5 + 1e-12);
    assert.ok(sample.position[1] >= 0 && sample.position[1] <= 2.6);
    assert.equal(Number.isFinite(sample.position[1]), true);
  }
  const edge = m.samples.find(
    (p) =>
      p.sourceId === 20 &&
      Math.abs(p.position[0] - 0.14) < 1e-12 &&
      p.position[2] === 0,
  );
  assert.ok(
    Math.abs(edge.position[1] - (2.6 * Math.log1p(2)) / Math.log1p(4)) < 1e-12,
  );
});

test("cloud projection adds only display samples and preserves exact originals and return mapping", () => {
  const input = evidence(),
    surface = activityModel(input),
    cloud = activityModel(input, { cloudOnly: true });
  assert.deepEqual(cloud.points, surface.points);
  assert.deepEqual(cloud.segments, surface.segments);
  assert.equal(cloud.triangles.length, 0);
  assert.ok(cloud.samples.length > surface.samples.length);
  assert.equal(cloud.sourceCount, surface.sourceCount);
  assert.equal(cloud.legend.maximum, surface.legend.maximum);
  assert.notEqual(cloud.key, surface.key);
});

test("no-return prefix has zero height and reports the real zero peak without NaN", () => {
  const input = evidence();
  input.activity.counts = {};
  input.decision.memory_ids = [];
  const m = activityModel(input);
  assert.equal(m.legend.maximum, 0);
  assert.equal(m.stats.maximum, 0);
  assert.ok(m.samples.every((p) => p.position[1] === 0));
  assert.ok(m.points.every((p) => p.position[1] === 0));
});

test("future observations, foreign returned IDs and impossible prefix counts fail closed", () => {
  const future = evidence();
  future.facts[0].observed_step = 4;
  assert.throws(() => activityModel(future), /Future/);
  const foreign = evidence();
  foreign.decision.memory_ids = [999];
  assert.throws(() => activityModel(foreign), /outside/);
  for (const count of [-1, 0.5, 5, NaN, Infinity]) {
    const bad = evidence();
    bad.activity.counts["0,0"] = count;
    assert.throws(() => activityModel(bad), /Invalid/);
  }
  const empty = evidence();
  empty.facts = [];
  assert.throws(() => activityModel(empty), /No observed/);
});

test("colour scale clamps finite values but rejects non-finite telemetry", () => {
  assert.equal(activityColor(-1), activityColor(0));
  assert.equal(activityColor(2), activityColor(1));
  for (const x of [0, 0.2, 0.4, 0.6, 0.8, 1])
    assert.match(activityColor(x), /^#[0-9a-f]{6}$/);
  for (const x of [NaN, Infinity, -Infinity])
    assert.throws(() => activityColor(x), /Non-finite/);
});
