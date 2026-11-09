"use strict";
(() => {
  class PoseTween {
    constructor() {
      this.source = null;
      this.step = -1;
      this.target = null;
      this.from = null;
      this.started = 0;
      this.duration = 0;
    }
    update(source, step, pose, now, animate, duration) {
      if (source === this.source && step === this.step) return;
      const previous = this.sample(now).pose;
      const adjacent =
        source === this.source &&
        step === this.step + 1 &&
        previous &&
        Math.abs(pose[0] - this.target[0]) +
          Math.abs(pose[1] - this.target[1]) <=
          1;
      this.source = source;
      this.step = step;
      this.target = pose.slice();
      this.from = previous || pose.slice();
      if (adjacent)
        this.from[2] = pose[2] - (((pose[2] - this.from[2] + 6) % 4) - 2);
      this.started = now;
      this.duration =
        animate && adjacent ? Math.max(0, Math.min(240, duration)) : 0;
    }
    sample(now) {
      if (!this.target) return { pose: null, active: false };
      const t = this.duration
        ? Math.max(0, Math.min(1, (now - this.started) / this.duration))
        : 1;
      const eased = 1 - (1 - t) ** 3;
      return {
        pose: this.target.map(
          (v, i) => this.from[i] + (v - this.from[i]) * eased,
        ),
        active: t < 1,
      };
    }
  }
  const api = { PoseTween };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
