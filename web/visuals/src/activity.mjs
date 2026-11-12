// An observed-domain display of actual retrieval counts, not a dynamics model.
const SCALE = 0.28,
  SUBDIVISIONS = 6;
const key = (x, y) => `${x},${y}`;
const stops = [
  [0, [16, 35, 159]],
  [0.2, [0, 113, 225]],
  [0.4, [0, 219, 218]],
  [0.6, [88, 235, 73]],
  [0.8, [255, 223, 25]],
  [1, [255, 60, 9]],
];
export function activityColor(value) {
  if (!Number.isFinite(value)) throw Error("Non-finite activity colour");
  const t = Math.max(0, Math.min(1, value));
  const i = Math.min(
    stops.length - 2,
    stops.findIndex((s, j) => j < stops.length - 1 && t <= stops[j + 1][0]),
  );
  const a = stops[i],
    b = stops[i + 1],
    u = (t - a[0]) / (b[0] - a[0]);
  return (
    "#" +
    a[1]
      .map((v, j) =>
        Math.round(v + (b[1][j] - v) * u)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}
export function activityModel(evidence, { cloudOnly = false } = {}) {
  const { facts, decision: d, step } = evidence;
  if (!facts.length) throw Error("No observed domain");
  if (facts.some((f) => f.observed_step > step))
    throw Error("Future observation in activity field");
  const ids = new Set(facts.map((f) => f.id));
  if (d.memory_ids.some((id) => !ids.has(id)))
    throw Error("Returned source outside current observed heads");
  const counts = new Map(Object.entries(evidence.activity?.counts || {}));
  if (
    [...counts.values()].some(
      (n) => !Number.isInteger(n) || n < 0 || n > step + 1,
    )
  )
    throw Error("Invalid observed retrieval count");
  const cells = new Map(facts.map((f) => [key(f.x, f.y), f])),
    maximum = Math.max(0, ...facts.map((f) => counts.get(key(f.x, f.y)) || 0)),
    norm = (n) => Math.log1p(n) / Math.log1p(Math.max(1, maximum)),
    height = (n) => norm(n) * 2.6,
    count = (x, y, fallback) =>
      cells.has(key(x, y)) ? counts.get(key(x, y)) || 0 : fallback,
    returned = new Set(d.memory_ids),
    points = [],
    samples = [],
    wire = [],
    triangles = [];
  for (const f of facts) {
    const reads = counts.get(key(f.x, f.y)) || 0,
      h = height(reads);
    points.push({
      id: String(f.id),
      position: [f.x * SCALE, h, f.y * SCALE],
      color: activityColor(norm(reads)),
      selected: returned.has(f.id),
      dim: false,
      returned: false,
      label: `Original #${f.id} · (${f.x}, ${f.y})`,
      detail: `${reads} historical returns at this location${returned.has(f.id) ? " · returned now" : ""}`,
      fields: [
        { name: "observed step", value: f.observed_step },
        { name: "location returns", value: reads },
      ],
    });
    const grid = [];
    for (let z = 0; z <= SUBDIVISIONS; z++)
      for (let x = 0; x <= SUBDIVISIONS; x++) {
        const dx = x / SUBDIVISIONS - 0.5,
          dz = z / SUBDIVISIONS - 0.5,
          wx = Math.abs(dx),
          wz = Math.abs(dz),
          sx = Math.sign(dx),
          sz = Math.sign(dz),
          cx = count(f.x + sx, f.y, reads),
          cz = count(f.x, f.y + sz, reads),
          cd = count(f.x + sx, f.y + sz, reads),
          value =
            reads * (1 - wx) * (1 - wz) +
            cx * wx * (1 - wz) +
            cz * (1 - wx) * wz +
            cd * wx * wz,
          point = {
            position: [(f.x + dx) * SCALE, height(value), (f.y + dz) * SCALE],
            color: activityColor(norm(value)),
            sourceId: f.id,
          };
        grid.push(point);
        samples.push(point);
        if (cloudOnly && x % 2 === 0 && z % 2 === 0 && point.position[1] > 0.12)
          for (let j = 1; j <= 5; j++)
            samples.push({
              ...point,
              position: [
                point.position[0],
                (point.position[1] * j) / 6,
                point.position[2],
              ],
              color: activityColor((norm(value) * j) / 6),
            });
      }
    for (let z = 0; z < SUBDIVISIONS; z++)
      for (let x = 0; x < SUBDIVISIONS; x++) {
        const a = grid[z * (SUBDIVISIONS + 1) + x],
          b = grid[z * (SUBDIVISIONS + 1) + x + 1],
          c = grid[(z + 1) * (SUBDIVISIONS + 1) + x],
          e = grid[(z + 1) * (SUBDIVISIONS + 1) + x + 1];
        triangles.push(a, b, c, b, e, c);
        wire.push(
          { from: a.position, to: b.position, color: a.color },
          { from: a.position, to: c.position, color: a.color },
        );
      }
  }
  const xs = facts.map((f) => f.x * SCALE),
    zs = facts.map((f) => f.y * SCALE),
    bounds = [
      Math.min(...xs) - SCALE / 2,
      Math.max(...xs) + SCALE / 2,
      Math.min(...zs) - SCALE / 2,
      Math.max(...zs) + SCALE / 2,
    ],
    poseKey = key(d.pose[0], d.pose[1]),
    cue = [
      d.pose[0] * SCALE,
      height(counts.get(poseKey) || 0) + 0.16,
      d.pose[1] * SCALE,
    ],
    segments = [],
    byId = new Map(points.map((p) => [Number(p.id), p]));
  for (const id of d.memory_ids)
    segments.push({
      from: cue,
      to: byId.get(id).position,
      color: "#a0f5ff",
      kind: "read",
    });
  for (let i = 1; i < (d.plan || []).length; i++) {
    const a = d.plan[i - 1],
      b = d.plan[i];
    segments.push({
      from: [
        a[0] * SCALE,
        height(counts.get(key(...a)) || 0) + 0.08,
        a[1] * SCALE,
      ],
      to: [
        b[0] * SCALE,
        height(counts.get(key(...b)) || 0) + 0.08,
        b[1] * SCALE,
      ],
      color: "#ffffff",
      kind: "plan",
    });
  }
  return {
    key: evidence.key + ":activity:" + cloudOnly,
    kind: "activity",
    layout: "activity",
    points,
    segments,
    planes: [],
    anchors: [{ position: cue, label: "QUERY" }],
    samples,
    wire,
    triangles: cloudOnly ? [] : triangles,
    cloudOnly,
    volumeBounds: [...bounds, 0, 2.9],
    queryBounds: bounds,
    queryPlane: 0,
    heightLabel:
      "Height / colour = log-scaled retrieval count · observed locations only",
    sourceCount: facts.length,
    readCount: d.memory_ids.length,
    stats: {
      maximum,
      displaySamples: samples.length,
      triangles: cloudOnly ? 0 : triangles.length / 3,
      returned: d.memory_ids.length,
    },
    legend: { minimum: 0, maximum, scale: "log(1 + returns)" },
  };
}
