// Source-bound lifecycle views. These sets describe the actual read receipt,
// not a learned salience field or additional evidence supplied to the planner.
const color = {
  cold: "#27529a",
  hot: "#50ccdf",
  recovered: "#f1c86d",
  retired: "#a58ac9",
};

export function persistentState(evidence) {
  const r = evidence.decision.dependency;
  if (r?.graph_source !== "active_and_explicitly_recovered_only") return null;
  const ids = new Set(evidence.facts.map((f) => f.id));
  const active = new Set(r.available_ids),
    recovered = new Set(r.recovered_ids),
    returned = new Set(evidence.decision.memory_ids),
    retired = new Set(evidence.retiredIds || []),
    evicted = new Set(evidence.evictedIds || r.evicted_ids || []);
  if (
    ids.size !== evidence.facts.length ||
    active.size !== r.available_ids.length ||
    recovered.size !== r.recovered_ids.length ||
    returned.size !== evidence.decision.memory_ids.length ||
    active.size > r.active_capacity ||
    !Number.isInteger(r.active_capacity) ||
    [...active, ...recovered, ...returned].some((id) => !ids.has(id)) ||
    [...recovered, ...returned].some((id) => !active.has(id)) ||
    evidence.facts.some(
      (f) =>
        !Number.isInteger(f.id) ||
        f.id <= 0 ||
        ![f.x, f.y, f.observed_step].every(Number.isFinite) ||
        f.observed_step > evidence.step,
    )
  )
    throw Error("Persistent source or active-capacity boundary violated");
  return {
    active,
    recovered,
    returned,
    retired,
    evicted,
    cold: new Set([...ids].filter((id) => !active.has(id))),
    capacity: r.active_capacity,
    status: r.recovery_status,
    reason: r.recovery_reason,
    referenceHash: r.reference_hash,
    referenceKind: r.reference_kind,
    work: r.work_delta,
  };
}

export function persistentMemoryModel(evidence, { activeOnly = false } = {}) {
  const state = persistentState(evidence);
  if (!state) throw Error("No persistent task receipt");
  const { decision: d } = evidence;
  const facts = evidence.facts.filter(
    (f) => !activeOnly || state.active.has(f.id),
  );
  const points = facts.map((f) => {
    const recovered = state.recovered.has(f.id),
      active = state.active.has(f.id),
      returned = state.returned.has(f.id),
      retired = state.retired.has(f.id),
      evicted = state.evicted.has(f.id);
    const layer = recovered
      ? "Recovered this read"
      : active
        ? "Active workspace"
        : "Dormant archive";
    return {
      id: String(f.id),
      position: [f.x / 8, recovered ? 1.3 : active ? 0.65 : 0, f.y / 8],
      color: recovered
        ? color.recovered
        : active
          ? color.hot
          : retired || evicted
            ? color.retired
            : color.cold,
      dim: !active && !retired && !evicted,
      selected: returned,
      returned,
      fields: ["x", "y", "object", "color", "state", "observed_step"].map(
        (name) => ({ name, value: f[name] }),
      ),
      label: `Original #${f.id}`,
      detail: `${layer}${returned ? " · returned to planner" : ""}${retired ? " · retired by age this step" : ""}${evicted ? " · evicted from active capacity this step" : ""}`,
    };
  });
  const xs = [d.pose[0] / 8, ...points.map((p) => p.position[0])],
    zs = [d.pose[1] / 8, ...points.map((p) => p.position[2])],
    bounds = [
      Math.min(...xs) - 0.15,
      Math.max(...xs) + 0.15,
      Math.min(...zs) - 0.15,
      Math.max(...zs) + 0.15,
    ];
  const cue = [d.pose[0] / 8, 1.4, d.pose[1] / 8],
    segments = [];
  for (const p of points) {
    if (p.selected)
      segments.push({
        from: cue,
        to: p.position,
        color: color.hot,
        kind: "read",
      });
    if (state.recovered.has(Number(p.id)))
      segments.push({
        from: [p.position[0], 0, p.position[2]],
        to: p.position,
        color: color.recovered,
        kind: "stem",
      });
  }
  return {
    key: evidence.key + (activeOnly ? ":active" : ":lifecycle"),
    kind: "task-memory",
    points,
    segments,
    anchors: [{ position: cue, label: "Current cue" }],
    planes: (activeOnly
      ? [["active", "ACTIVE WORKSPACE", 0.65, color.hot]]
      : [
          ["cold", "DORMANT / RECOVERABLE", 0, color.cold],
          ["active", "ACTIVE WORKSPACE", 0.65, color.hot],
          ["recovered", "RECOVERED THIS READ", 1.3, color.recovered],
        ]
    ).map(([id, label, y, c]) => ({ id, label, y, color: c, bounds })),
    sourceCount: points.length,
    readCount: state.returned.size,
    queryPlane: 0.65,
    queryBounds: bounds,
    heightLabel: activeOnly
      ? "Available payloads only · archive is not queried on this decision"
      : "Height = memory state · rings = returned now · gold = cold recovery",
  };
}
