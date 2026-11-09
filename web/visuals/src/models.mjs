export const COLORS = {
  a: "#87d9cb",
  b: "#e9987d",
  gold: "#e2ce86",
  violet: "#baa2e6",
  white: "#edece4",
  dim: "#45514c",
};
const finite = (v) => {
  if (!Number.isFinite(v)) throw Error("Nonfinite visual coordinate");
  return v;
};
const pos = (x, y, z) => [finite(x), finite(y), finite(z)];
export function memoryModel(state, selectedId = null) {
  const q = state.query,
    cue = q?.cue,
    selected = new Set(q?.selected_ids || []),
    nodes = state.nodes || [],
    replayed = new Set(
      state.sleep?.busy ? state.sleep.trace?.at(-1)?.sources || [] : [],
    ),
    byId = new Map();
  const points = nodes.map((n) => {
    const base = n.context * 1.2,
      height = Math.max(0, Math.min(2, finite(n.salience))) * 0.24;
    const p = {
      id: String(n.id),
      position: pos(n.x, base + height, n.y),
      color: selected.has(n.id)
        ? COLORS.gold
        : n.context === 0
          ? COLORS.a
          : COLORS.b,
      dim: !n.current || !n.hot,
      selected: selected.has(n.id),
      focused: n.id === selectedId,
      fields: ["x", "y", "ax", "ay", "uses", "salience"]
        .filter((k) => Number.isFinite(n[k]))
        .map((k) => ({ name: k, value: n[k] })),
      returned: false,
      replayed: replayed.has(n.id),
      label: "Observation #" + n.id + " · World " + (n.context ? "B" : "A"),
      detail:
        (n.current ? (n.hot ? "Active" : "Dormant") : "Superseded") +
        " · salience " +
        n.salience.toFixed(3),
    };
    byId.set(n.id, p);
    return p;
  });
  const segments = [];
  for (const n of nodes) {
    const p = byId.get(n.id);
    segments.push({
      from: [n.x, n.context * 1.2, n.y],
      to: p.position,
      color: p.color,
      kind: "stem",
    });
    if (n.current)
      segments.push({
        from: p.position,
        to: pos(n.next_x, p.position[1], n.next_y),
        color: p.color,
        kind: "transition",
        dim: p.dim,
      });
  }
  const anchors = [];
  if (cue) {
    const contexts = cue.context === null ? [0, 1] : [cue.context],
      mask = cue.mask;
    for (const c of contexts) {
      const point = pos(
        mask[0] ? cue.position[0] : 0,
        c * 1.2 + 0.018,
        mask[1] ? cue.position[1] : 0,
      );
      if (mask.some(Boolean))
        anchors.push({
          position: point,
          label: mask.every(Boolean) ? "Spatial cue" : "Partial cue",
        });
      if (!mask[0] && mask[1])
        segments.push({
          from: [-1, c * 1.2 + 0.018, point[2]],
          to: [1, c * 1.2 + 0.018, point[2]],
          color: COLORS.white,
          kind: "cue",
        });
      if (!mask[1] && mask[0])
        segments.push({
          from: [point[0], c * 1.2 + 0.018, -1],
          to: [point[0], c * 1.2 + 0.018, 1],
          color: COLORS.white,
          kind: "cue",
        });
    }
    for (const id of selected) {
      const p = byId.get(id);
      if (!p) throw Error("Selected observation missing from visual source");
      const c =
        cue.context === null
          ? nodes.find((n) => n.id === id).context
          : cue.context;
      if (cue.mask.some(Boolean))
        segments.push({
          from: pos(
            cue.mask[0] ? cue.position[0] : p.position[0],
            c * 1.2 + 0.018,
            cue.mask[1] ? cue.position[1] : p.position[2],
          ),
          to: p.position,
          color: COLORS.gold,
          kind: "read",
        });
    }
  }
  if (q?.prediction && cue.mask.every(Boolean) && cue.context !== null) {
    const from = pos(
      cue.position[0],
      cue.context * 1.2 + 0.025,
      cue.position[1],
    );
    segments.push({
      from,
      to: pos(from[0] + q.prediction[0], from[1], from[2] + q.prediction[1]),
      color: COLORS.white,
      kind: "prediction",
    });
  }
  return {
    key: JSON.stringify([
      state.archive?.checksum,
      state.session?.active_archive,
      state.revision,
      state.tick,
      state.model?.trained_steps,
      Boolean(state.sleep?.busy),
      state.sleep?.trace?.at(-1)?.sources,
      cue,
      [...selected],
    ]),
    kind: "memory",
    points,
    segments,
    anchors,
    planes: [
      {
        id: "0",
        label: "WORLD A",
        y: 0,
        color: COLORS.a,
        bounds: [-1.1, 1.1, -1.1, 1.1],
      },
      {
        id: "1",
        label: "WORLD B / RARE",
        y: 1.2,
        color: COLORS.b,
        bounds: [-1.1, 1.1, -1.1, 1.1],
      },
    ],
    queryPlane: cue?.context === 1 ? 1.2 : 0,
    queryBounds: [-1, 1, -1, 1],
    heightLabel: "Height = salience, capped at 2",
    sourceCount: nodes.length,
    readCount: selected.size,
  };
}
export function hierarchyModel(model, key) {
  if (!model.mapped)
    throw Error("Recorded node spans required for spatial hierarchy");
  const points = [],
    segments = [],
    lookup = new Map(),
    colors = [COLORS.gold, COLORS.a, COLORS.violet, COLORS.violet];
  let minX = Infinity,
    maxX = -Infinity,
    minZ = Infinity,
    maxZ = -Infinity;
  for (const level of model.levels)
    for (const n of level.nodes) {
      if (!n.facts.length) throw Error("Recorded node has no observed source");
      const x = n.facts.reduce((s, f) => s + f.x, 0) / n.facts.length / 8,
        z = n.facts.reduce((s, f) => s + f.y, 0) / n.facts.length / 8;
      const p = {
        id: n.key,
        position: pos(x, n.level * 0.85, z),
        color: n.kept ? (n.level ? COLORS.a : COLORS.gold) : COLORS.dim,
        dim: !n.kept,
        selected: n.kept,
        returned: n.returned,
        label: n.level
          ? "L" + n.level + " / node " + n.index
          : "Original #" + n.facts[0].id,
        detail:
          n.facts.length +
          " source " +
          (n.facts.length === 1 ? "record" : "records") +
          (Number.isFinite(n.score) ? " · score " + n.score.toFixed(3) : ""),
      };
      points.push(p);
      lookup.set(n.key, p);
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minZ = Math.min(minZ, z);
      maxZ = Math.max(maxZ, z);
    }
  for (const [a, b] of model.edges) {
    if (!lookup.has(a) || !lookup.has(b)) throw Error("Unknown hierarchy edge");
    segments.push({
      from: lookup.get(a).position,
      to: lookup.get(b).position,
      color: COLORS.a,
      kind: "read",
    });
  }
  const bounds = [minX - 0.2, maxX + 0.2, minZ - 0.2, maxZ + 0.2];
  return {
    key,
    kind: "hierarchy",
    points,
    segments,
    anchors: [],
    planes: model.levels.map((l) => ({
      id: String(l.level),
      label: l.level ? "LEVEL " + l.level : "ORIGINAL RECORDS",
      y: l.level * 0.85,
      color: colors[Math.min(l.level, 3)],
      bounds,
    })),
    heightLabel: "Position = observed group centroid · height = tree level",
    sourceCount: model.originalCount,
    readCount: model.rawCount,
  };
}

// A display atlas of indexed originals. This is an ordinal layout, not an embedding.
export function indexHierarchyModel(model, key, { columns = 24 } = {}) {
  if (!Number.isInteger(columns) || columns < 4 || columns > 64)
    throw Error("Invalid ordinal atlas columns");
  const result = hierarchyModel(model, key + ":ordinal:" + columns),
    originals = model.levels.find((l) => l.level === 0).nodes,
    cols = columns,
    rows = Math.ceil(originals.length / cols),
    slots = new Map(
      originals.map((n, i) => [
        n.facts[0].id,
        [
          ((i % cols) - (cols - 1) / 2) * 0.36,
          (Math.floor(i / cols) - (rows - 1) / 2) * 0.36,
        ],
      ]),
    ),
    lookup = new Map();
  for (const level of model.levels)
    for (const n of level.nodes) {
      const p = result.points.find((p) => p.id === n.key),
        members = n.facts.map((f) => slots.get(f.id));
      if (members.some((p) => !p))
        throw Error("Missing original in ordinal display");
      p.position = [
        members.reduce((s, p) => s + p[0], 0) / members.length,
        n.level * 1.1,
        members.reduce((s, p) => s + p[1], 0) / members.length,
      ];
      p.level = n.level;
      p.memberCount = n.facts.length;
      p.members = members.map((p) => [p[0], 0, p[1]]);
      p.score = n.score;
      p.fields = n.level
        ? []
        : ["x", "y", "object", "color", "state"]
            .filter((k) => Number.isFinite(n.facts[0][k]))
            .map((k) => ({ name: k, value: n.facts[0][k] }));
      lookup.set(n.key, p);
    }
  for (let i = 0; i < model.edges.length; i++) {
    const [a, b] = model.edges[i];
    result.segments[i] = {
      ...result.segments[i],
      from: lookup.get(a).position,
      to: lookup.get(b).position,
      level: lookup.get(a).level,
    };
  }
  const bounds = [
    -cols * 0.18 - 0.18,
    cols * 0.18 + 0.18,
    -Math.max(1.35, rows * 0.18 + 0.2),
    Math.max(1.35, rows * 0.18 + 0.2),
  ];
  result.planes = model.levels.map((l) => ({
    id: String(l.level),
    label: l.level ? "L" + l.level + " / SUMMARIES" : "L0 / ORIGINALS",
    y: l.level * 1.1,
    color: l.level > 1 ? "#8194ad" : l.level ? "#78c4bd" : "#e2ce86",
    bounds,
    count: l.nodes.length,
    kept: l.nodes.filter((n) => n.kept).length,
  }));
  result.layout = "ordinal";
  result.heightLabel =
    "Indexed order × tree level · source values shown as five channel glyphs";
  result.readout = model.levels.map((l) => ({
    label: "L" + l.level,
    count: l.nodes.length,
    kept: l.nodes.filter((n) => n.kept).length,
    scores: l.nodes.map((n) => n.score).filter(Number.isFinite),
  }));
  return result;
}

export function arborHierarchyModel(model, key) {
  const result = indexHierarchyModel(model, key + ":arbor"),
    originals = model.levels.find((l) => l.level === 0).nodes,
    max = Math.max(...model.levels.map((l) => l.level)),
    slots = new Map(
      originals.map((n, i) => {
        const r = Math.sqrt((i + 0.5) / originals.length),
          theta = i * Math.PI * (3 - Math.sqrt(5));
        return [
          n.facts[0].id,
          [
            Math.cos(theta) * r * 3.7,
            3.4 + (1 - r * r) * 0.9,
            Math.sin(theta) * r * 2.4,
          ],
        ];
      }),
    ),
    lookup = new Map();
  for (const level of model.levels)
    for (const n of level.nodes) {
      const p = result.points.find((p) => p.id === n.key),
        members = n.facts.map((f) => slots.get(f.id)),
        spread = 1 - n.level / (max + 1);
      p.position = [
        (members.reduce((s, p) => s + p[0], 0) / members.length) * spread,
        ((max - n.level) / max) * 3.7,
        (members.reduce((s, p) => s + p[2], 0) / members.length) * spread,
      ];
      if (!n.level) p.position = slots.get(n.facts[0].id);
      p.members = null;
      lookup.set(n.key, p);
    }
  for (let i = 0; i < model.edges.length; i++) {
    const [a, b] = model.edges[i];
    result.segments[i] = {
      ...result.segments[i],
      from: lookup.get(a).position,
      to: lookup.get(b).position,
      radius: Math.min(
        0.045,
        0.007 +
          Math.sqrt(lookup.get(b).level ? lookup.get(b).memberCount : 1) *
            0.002,
      ),
    };
  }
  result.layout = "arbor";
  result.planes = [];
  result.heightLabel =
    "Canopy projection of recorded spans · branches preserve actual routing edges";
  return result;
}
