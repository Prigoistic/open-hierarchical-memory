import test from "node:test";
import assert from "node:assert/strict";
import motion from "../src/navigation.cjs";
const { PoseTween } = motion;
test("movement starts at the previous observed pose, eases and ends exactly", () => {
  const tween = new PoseTween();
  tween.update("run", 0, [0, 0, 0], 0, true, 200);
  tween.update("run", 1, [1, 0, 0], 10, true, 200);
  assert.deepEqual(tween.sample(10).pose, [0, 0, 0]);
  const mid = tween.sample(110);
  assert.ok(mid.active && mid.pose[0] > 0 && mid.pose[0] < 1);
  assert.deepEqual(tween.sample(210), { pose: [1, 0, 0], active: false });
});
test("scrubbing and changing source never animate across unobserved space", () => {
  const tween = new PoseTween();
  tween.update("a", 1, [0, 0, 0], 0, true, 200);
  tween.update("a", 12, [8, 8, 1], 10, true, 200);
  assert.deepEqual(tween.sample(10), { pose: [8, 8, 1], active: false });
  tween.update("b", 13, [7, 8, 1], 20, true, 200);
  assert.deepEqual(tween.sample(20), { pose: [7, 8, 1], active: false });
  tween.update("b", 14, [6, 8, 1], 30, false, 200);
  assert.deepEqual(tween.sample(30), { pose: [6, 8, 1], active: false });
});
test("turn interpolation takes the shortest compass path and does not mutate evidence", () => {
  const tween = new PoseTween(),
    target = Object.freeze([0, 0, 0]);
  tween.update("run", 0, [0, 0, 3], 0, false, 200);
  tween.update("run", 1, target, 10, true, 200);
  assert.ok(tween.sample(110).pose[2] > -1 && tween.sample(110).pose[2] < 0);
  assert.deepEqual(tween.sample(210).pose, target);
  assert.deepEqual(target, [0, 0, 0]);
});
test("a repeated render does not restart the transition", () => {
  const tween = new PoseTween();
  tween.update("run", 0, [0, 0, 0], 0, false, 200);
  tween.update("run", 1, [1, 0, 0], 10, true, 200);
  const pose = tween.sample(110).pose;
  tween.update("run", 1, [1, 0, 0], 110, true, 200);
  assert.deepEqual(tween.sample(110).pose, pose);
  assert.equal(tween.sample(210).active, false);
});
