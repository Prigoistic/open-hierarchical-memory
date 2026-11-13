import test from "node:test";
import assert from "node:assert/strict";
import { lifecycleCloudModel, cloudColors } from "../src/lifecycle-cloud.mjs";

const fixture = () => ({
  key: "run:2",
  step: 2,
  facts: [1, 2, 3, 4].map((id) => ({
    id,
    x: id,
    y: 0,
    observed_step: 0,
    object: 1,
    color: 0,
    state: 0,
  })),
  activity: { counts: { "1,0": 0, "2,0": 2, "3,0": 1, "4,0": 1 } },
  decision: {
    pose: [0, 0, 0],
    memory_ids: [2, 3],
    plan: [],
    dependency: {
      graph_source: "active_and_explicitly_recovered_only",
      available_ids: [2, 3],
      recovered_ids: [3],
      evicted_ids: [4],
      active_capacity: 2,
      reference_hash: "checkpoint",
      reference_kind: "fitted",
      work_delta: {},
    },
  },
});

test("memory cloud partitions actual sources and counts recovery inside active", () => {
  const e = fixture(),
    before = structuredClone(e),
    m = lifecycleCloudModel(e);
  assert.deepEqual(m.stateCounts, {
    dormant: 2,
    active: 2,
    retained: 1,
    recovered: 1,
    returned: 2,
    capacity: 2,
  });
  assert.deepEqual(
    m.points.map((p) => p.id),
    ["1", "2", "3", "4"],
  );
  assert.equal(m.points.find((p) => p.id === "1").color, cloudColors.dormant);
  assert.equal(m.points.find((p) => p.id === "2").color, cloudColors.active);
  assert.equal(m.points.find((p) => p.id === "3").color, cloudColors.recovered);
  assert.equal(m.points.filter((p) => p.returned).length, 2);
  assert.deepEqual(e, before);
});

test("dense geometry has a real source and never crosses lifecycle bands", () => {
  const m = lifecycleCloudModel(fixture()),
    points = new Map(m.points.map((p) => [Number(p.id), p]));
  assert.ok(m.samples.length > m.points.length);
  for (const sample of m.samples) {
    const p = points.get(sample.sourceId);
    assert.ok(p);
    assert.equal(sample.color, p.color);
    assert.ok(sample.position.every(Number.isFinite));
    const base = { dormant: 0, active: 1.45, recovered: 2.9 }[p.lifecycleState];
    assert.ok(
      sample.position[1] >= base && sample.position[1] <= base + 0.728 + 1e-12,
    );
  }
  assert.match(m.heightLabel, /display samples/);
  assert.equal(m.sourceCount, 4);
});

test("cloud rings and read links correspond exactly to returned originals", () => {
  const m = lifecycleCloudModel(fixture());
  assert.deepEqual(
    m.points.filter((p) => p.returned).map((p) => p.id),
    ["2", "3"],
  );
  const destinations = m.segments
    .filter((s) => s.kind === "read")
    .map((s) => s.to);
  assert.deepEqual(
    destinations,
    m.points.filter((p) => p.returned).map((p) => p.position),
  );
  assert.equal(m.segments.filter((s) => s.kind === "stem").length, 1);
});

test("rewind clears future source states and recovery overlays", () => {
  const e = fixture();
  e.decision.dependency.recovered_ids = [];
  e.decision.memory_ids = [];
  const m = lifecycleCloudModel(e);
  assert.equal(m.stateCounts.recovered, 0);
  assert.equal(m.stateCounts.returned, 0);
  assert.equal(m.segments.length, 0);
  assert.ok(m.points.every((p) => p.lifecycleState !== "recovered"));
});

test("future, foreign and over-capacity state fails before cloud geometry", () => {
  for (const change of [
    (e) => (e.facts[0].observed_step = 3),
    (e) => (e.decision.dependency.recovered_ids = [999]),
    (e) => (e.decision.dependency.active_capacity = 1),
    (e) => (e.activity.counts["1,0"] = -1),
  ]) {
    const e = fixture();
    change(e);
    assert.throws(() => lifecycleCloudModel(e));
  }
});
