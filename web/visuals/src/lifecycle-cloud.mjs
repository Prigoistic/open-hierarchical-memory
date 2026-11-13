// Display-only samples retain an original source ID. State and return counts
// come from the selected decision; neither changes the planner or archive.
import { activityModel } from "./activity.mjs";
import { persistentState } from "./persistent.mjs";

export const cloudColors = Object.freeze({
  dormant: "#5577df",
  active: "#50ccdf",
  recovered: "#f1c86d",
});
const levels = Object.freeze({ dormant: 0, active: 1.45, recovered: 2.9 });
const HEIGHT_SCALE = 0.28;

export function lifecycleCloudModel(evidence) {
  const state = persistentState(evidence);
  if (!state) throw Error("No persistent task receipt for memory cloud");
  const field = activityModel(evidence, { cloudOnly: true });
  const category = (id) =>
    state.recovered.has(id)
      ? "recovered"
      : state.active.has(id)
        ? "active"
        : "dormant";
  const sources = new Map(field.points.map((p) => [Number(p.id), p]));
  const lift = (position, id) => [
    position[0],
    levels[category(id)] + position[1] * HEIGHT_SCALE,
    position[2],
  ];
  const points = field.points.map((p) => {
    const id = Number(p.id),
      group = category(id);
    return {
      ...p,
      position: lift(p.position, id),
      color: cloudColors[group],
      dim: false,
      selected: state.returned.has(id),
      returned: state.returned.has(id),
      lifecycleState: group,
      detail: `${group === "dormant" ? "Dormant: stored outside active workspace" : group === "recovered" ? "Recovered from archive this read; included in active workspace" : "Active: available to planner"}${state.returned.has(id) ? " · returned to planner" : ""} · ${p.detail}`,
    };
  });
  const samples = field.samples.map((sample) => {
    if (!sources.has(sample.sourceId))
      throw Error("Cloud sample escaped original source set");
    return {
      ...sample,
      position: lift(sample.position, sample.sourceId),
      color: cloudColors[category(sample.sourceId)],
    };
  });
  const cue = [
    evidence.decision.pose[0] * 0.28,
    4.05,
    evidence.decision.pose[1] * 0.28,
  ];
  const segments = points
    .filter((p) => p.returned)
    .map((p) => ({
      from: cue,
      to: p.position,
      color: "#a0f5ff",
      kind: "read",
    }));
  for (const p of points.filter((p) => p.lifecycleState === "recovered")) {
    const original = sources.get(Number(p.id));
    segments.push({
      from: [p.position[0], original.position[1] * HEIGHT_SCALE, p.position[2]],
      to: p.position,
      color: cloudColors.recovered,
      kind: "stem",
    });
  }
  const counts = {
    dormant: state.cold.size,
    active: state.active.size,
    retained: state.active.size - state.recovered.size,
    recovered: state.recovered.size,
    returned: state.returned.size,
    capacity: state.capacity,
  };
  return {
    ...field,
    key: evidence.key + ":lifecycle-cloud",
    layout: "lifecycle-cloud",
    lifecycleCloud: true,
    points,
    samples,
    segments,
    anchors: [{ position: cue, label: "CURRENT QUERY" }],
    planes: [
      ["dormant", `DORMANT ARCHIVE · ${counts.dormant}`],
      ["active", `ACTIVE WORKSPACE · ${counts.retained} retained`],
      ["recovered", `RECOVERED NOW · ${counts.recovered} active`],
    ].map(([id, label]) => ({
      id,
      label,
      y: levels[id],
      color: cloudColors[id],
      labelColor: cloudColors[id],
      bounds: field.queryBounds,
    })),
    volumeBounds: [...field.queryBounds, 0, 4.1],
    queryPlane: levels.active,
    heightLabel:
      "X/Z = observed map · bands = memory state · height = past location returns · fine cloud = display samples",
    stateCounts: counts,
    sourceCount: points.length,
    readCount: counts.returned,
    stats: {
      ...field.stats,
      displaySamples: samples.length,
      returned: counts.returned,
    },
  };
}
