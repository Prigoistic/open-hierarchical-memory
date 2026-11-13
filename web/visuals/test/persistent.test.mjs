import test from "node:test";
import assert from "node:assert/strict";
import { persistentState, persistentMemoryModel } from "../src/persistent.mjs";
const fixture = () => ({
  key: "run:2",
  step: 2,
  retiredIds: [1],
  facts: [1, 2, 3, 4].map((id) => ({
    id,
    x: id,
    y: 0,
    observed_step: 0,
    object: 1,
    color: 0,
    state: 0,
  })),
  decision: {
    pose: [0, 0, 0],
    memory_ids: [2],
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
test("lifecycle distinguishes active, dormant, actual recovery and returned evidence", () => {
  const e = fixture(),
    before = structuredClone(e),
    s = persistentState(e),
    m = persistentMemoryModel(e);
  assert.deepEqual([...s.cold], [1, 4]);
  assert.deepEqual([...s.recovered], [3]);
  assert.equal(m.points.find((p) => p.id === "1").position[1], 0);
  assert.equal(m.points.find((p) => p.id === "2").position[1], 0.65);
  assert.equal(m.points.find((p) => p.id === "3").position[1], 1.3);
  assert.equal(m.points.filter((p) => p.returned).length, 1);
  assert.match(m.points.find((p) => p.id === "4").detail, /evicted/);
  assert.deepEqual(e, before);
});
test("idle workspace view never includes dormant payloads", () => {
  const m = persistentMemoryModel(fixture(), { activeOnly: true });
  assert.deepEqual(
    m.points.map((p) => p.id),
    ["2", "3"],
  );
  assert.equal(m.sourceCount, 2);
});
test("recovery cannot fabricate an active or observed source", () => {
  for (const ids of [[1], [999]]) {
    const e = fixture();
    e.decision.dependency.recovered_ids = ids;
    assert.throws(() => persistentState(e), /boundary/);
  }
});
test("future sources and capacity escapes fail before rendering", () => {
  const e = fixture();
  e.facts[0].observed_step = 3;
  assert.throws(() => persistentMemoryModel(e), /boundary/);
  const a = fixture();
  a.decision.dependency.available_ids.push(4);
  assert.throws(() => persistentMemoryModel(a), /boundary/);
});
test("legacy evidence keeps its existing rendering path", () => {
  const e = fixture();
  delete e.decision.dependency;
  assert.equal(persistentState(e), null);
});

test("nonfinite coordinates and duplicate returned identities cannot reach the GPU", () => {
  const e = fixture();
  e.facts[0].x = NaN;
  assert.throws(() => persistentMemoryModel(e), /boundary/);
  const d = fixture();
  d.decision.memory_ids = [2, 2];
  assert.throws(() => persistentMemoryModel(d), /boundary/);
});
