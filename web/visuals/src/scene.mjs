import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { gsap } from "gsap";
import { createContextGrid } from "./grid.mjs";
import navigation from "./navigation.cjs";
import { viewTransition } from "./models.mjs";
export { persistentState, persistentMemoryModel } from "./persistent.mjs";
export const PoseTween = navigation.PoseTween;
export { activityModel, activityColor } from "./activity.mjs";
export { lifecycleCloudModel } from "./lifecycle-cloud.mjs";
import { CustomEase } from "gsap/CustomEase";
export {
  memoryModel,
  taskMemoryModel,
  hierarchyModel,
  indexHierarchyModel,
  arborHierarchyModel,
} from "./models.mjs";
gsap.registerPlugin(CustomEase);
CustomEase.create("somna", "0.22,1,0.36,1");
const V = (p) => new THREE.Vector3(...p);
export class SpatialView {
  constructor({ canvas, onPick, onQuery, onHover, readout }) {
    this.canvas = canvas;
    this.readout = readout;
    this.traceCurves = [];
    this.traceClock = { progress: 1 };
    this.onPick = onPick;
    this.onQuery = onQuery;
    this.onHover = onHover;
    this.model = null;
    this.mode = "layers";
    this.active = true;
    this.dirty = true;
    this.labels = [];
    this.focused = null;
    this.reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    this.renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: "low-power",
    });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
    this.renderer.setClearColor(0x000000);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.contextGrid = createContextGrid();
    this.scene.add(this.contextGrid);
    this.canvas.dataset.contextGrid = "fading floor";
    this.camera = new THREE.OrthographicCamera(-4, 4, 3, -3, 0.01, 100);
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.16, 0.35, 0.86);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this.camera.position.set(5, 5, 7);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, 1, 0);
    this.controls.enableDamping = !this.reduced;
    this.controls.dampingFactor = 0.075;
    this.controls.minZoom = 0.45;
    this.controls.maxZoom = 5;
    this.controls.enablePan = true;
    this.controls.autoRotateSpeed = 0.32;
    this.controls.update();
    this.controls.addEventListener("change", () => {
      this.dirty = true;
    });
    this.controls.addEventListener("start", () => {
      this.userCamera = true;
      gsap.killTweensOf([
        this.camera.position,
        this.controls.target,
        this.camera,
        this.framing,
      ]);
    });
    this.overlay = document.createElement("div");
    this.overlay.className = "spatial-overlay";
    canvas.parentElement.append(this.overlay);
    this.status = document.createElement("span");
    this.status.className = "spatial-status";
    this.overlay.append(this.status);
    this.caption = document.createElement("span");
    this.caption.className = "spatial-caption";
    this.overlay.append(this.caption);
    this.tip = document.createElement("div");
    this.tip.className = "spatial-lens";
    this.tip.hidden = true;
    this.overlay.append(this.tip);
    const toolbar = document.createElement("div");
    toolbar.className = "spatial-toolbar";
    this.overlay.append(toolbar);
    for (const [name, fn] of [
      [
        "Expand",
        () => {
          const stage = this.canvas.parentElement;
          if (document.fullscreenElement === stage)
            document.exitFullscreen().catch(() => {});
          else
            stage.requestFullscreen().catch(() => {
              this.status.textContent =
                "Fullscreen unavailable in this browser";
            });
        },
      ],
      ["Replay read", () => this.replay()],
      ["Home", () => this.reset()],
      ["Focus read", () => this.focus()],
      [
        "Orbit",
        (e) => {
          this.controls.autoRotate = !this.controls.autoRotate && !this.reduced;
          e.currentTarget.setAttribute(
            "aria-pressed",
            String(this.controls.autoRotate),
          );
          this.dirty = true;
        },
      ],
    ]) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = name;
      b.addEventListener("click", fn);
      if (name === "Orbit") {
        b.setAttribute("aria-pressed", "false");
        b.disabled = this.reduced;
      }
      toolbar.append(b);
    }
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.observer = new IntersectionObserver((entries) => {
      this.inView = entries[0].isIntersecting;
      if (this.inView) this.dirty = true;
    });
    this.observer.observe(canvas);
    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.down = null;
    canvas.addEventListener("pointerdown", (e) => {
      this.down = [e.clientX, e.clientY];
    });
    canvas.addEventListener("pointerup", (e) => {
      if (
        !this.down ||
        Math.hypot(e.clientX - this.down[0], e.clientY - this.down[1]) > 5
      )
        return;
      const n = this.pick(e);
      if (e.shiftKey || (this.onPick && !this.onQuery)) {
        if (n) this.onPick?.(n.id, e);
      } else this.onQuery?.(this.ground(e), n?.id, e);
    });
    canvas.addEventListener("pointermove", (e) => {
      if (e.buttons) return;
      const n = this.pick(e);
      this.showTip(n);
      this.onHover?.(n?.id || null);
    });
    canvas.addEventListener("pointerleave", () => this.showTip(null));
    canvas.addEventListener("keydown", (e) => {
      if (e.key === "r") {
        e.preventDefault();
        this.reset();
      }
      if (e.key === "f") {
        e.preventDefault();
        this.focus();
      }
    });
    canvas.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      this.active = false;
      this.status.textContent = "3D view paused";
      const b = document.createElement("button");
      b.textContent = "Use canvas view";
      b.onclick = () => {
        const u = new URL(location.href);
        u.searchParams.set("renderer", "canvas");
        location.href = u;
      };
      toolbar.append(b);
    });
    this.ticker = () => {
      if (!this.active || this.inView === false || document.hidden) return;
      const changed = this.controls.update();
      if (
        changed ||
        this.dirty ||
        gsap.isTweening(this.camera.position) ||
        gsap.isTweening(this.controls.target) ||
        gsap.isTweening(this.traceClock)
      )
        this.render();
    };
    gsap.ticker.add(this.ticker);
    this.canvas.dataset.renderer = "three";
    this.resize();
  }
  setVisible(on) {
    if (this.shown === on) return;
    this.shown = on;
    this.active = on;
    this.canvas.hidden = !on;
    this.overlay.hidden = !on;
    this.controls.enabled = on;
    if (on) {
      this.resize();
      this.dirty = true;
    }
  }
  resize() {
    const r = this.canvas.getBoundingClientRect();
    if (!r.width || !r.height) return;
    this.width = r.width;
    this.height = r.height;
    this.renderer.setSize(r.width, r.height, false);
    this.composer?.setSize(r.width, r.height);
    const aspect = r.width / r.height;
    this.fitSpan(aspect);
    this.applySpan(this.span || 5.5);
    this.dirty = true;
  }
  applySpan(span) {
    const aspect = this.width / this.height;
    this.span = span;
    this.camera.left = (-span * aspect) / 2;
    this.camera.right = (span * aspect) / 2;
    this.camera.top = span / 2;
    this.camera.bottom = -span / 2;
    this.camera.updateProjectionMatrix();
    this.dirty = true;
  }
  fitSpan(aspect) {
    if (!this.box) return;
    const size = this.box.getSize(new THREE.Vector3()),
      d = new THREE.Vector3(5, 3, 7).normalize(),
      right = new THREE.Vector3()
        .crossVectors(new THREE.Vector3(0, 1, 0), d)
        .normalize(),
      up = new THREE.Vector3().crossVectors(d, right);
    const width =
        this.mode === "plane"
          ? size.x
          : Math.abs(right.x) * size.x + Math.abs(right.z) * size.z,
      height =
        this.mode === "plane"
          ? size.z
          : Math.abs(up.x) * size.x +
            Math.abs(up.y) * size.y +
            Math.abs(up.z) * size.z;
    this.span =
      Math.max(2, height, width / aspect) *
      (this.model?.kind === "activity" ? 1.12 : 1.22);
  }
  clear() {
    this.group.traverse((o) => {
      o.geometry?.dispose();
      if (o.material) {
        for (const m of Array.isArray(o.material) ? o.material : [o.material]) {
          gsap.killTweensOf(m);
          m.dispose();
        }
      }
    });
    gsap.killTweensOf(this.traceClock);
    this.traceCurves = [];
    this.traceHeads = null;
    this.group.clear();
    this.focusMarker = null;
    for (const l of this.labels) l.el.remove();
    this.labels = [];
    this.tip.hidden = true;
  }
  line(segments, color, opacity) {
    if (!segments.length) return;
    const geometry = new THREE.BufferGeometry().setFromPoints(
      segments.flatMap((s) => [V(s.from), V(s.to)]),
    );
    const object = new THREE.LineSegments(
      geometry,
      new THREE.LineBasicMaterial({
        color,
        transparent: true,
        opacity,
        depthWrite: false,
      }),
    );
    this.group.add(object);
  }
  points(items, size, opacity, map = null) {
    if (!items.length) return;
    const g = new THREE.BufferGeometry().setFromPoints(
      items.map((p) => V(p.position)),
    );
    const colors = items.flatMap((p) => new THREE.Color(p.color).toArray());
    g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    const material = new THREE.PointsMaterial({
      size,
      sizeAttenuation: false,
      vertexColors: true,
      transparent: true,
      opacity,
      depthWrite: false,
      map,
      alphaTest: map ? 0.02 : 0,
      blending: map ? THREE.AdditiveBlending : THREE.NormalBlending,
    });
    const object = new THREE.Points(g, material);
    this.group.add(object);
    return object;
  }
  texture(kind) {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const x = c.getContext("2d");
    if (kind === "glow") {
      const g = x.createRadialGradient(32, 32, 0, 32, 32, 32);
      g.addColorStop(0, "rgba(255,255,255,1)");
      g.addColorStop(0.16, "rgba(255,255,255,.7)");
      g.addColorStop(1, "rgba(255,255,255,0)");
      x.fillStyle = g;
      x.fillRect(0, 0, 64, 64);
    } else {
      x.strokeStyle = "#fff";
      x.lineWidth = 5;
      x.strokeRect(8, 8, 48, 48);
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }
  label(text, position, color) {
    const el = document.createElement("span");
    el.className = "spatial-label";
    el.dataset.fullLabel = text;
    el.textContent =
      this.width < 500
        ? text.replace(" / SUMMARIES", "").replace(" / ORIGINALS", "")
        : text;
    el.style.color = color;
    this.overlay.append(el);
    this.labels.push({ el, position: V(position) });
  }
  setData(model) {
    if (this.model?.key === model.key) return;
    const first = !this.model,
      transition = viewTransition(this.model, model, this.reduced),
      previousSpan = this.span;
    this.model = model;
    this.clear();
    this.contextGrid.visible = model.kind !== "activity";
    this.bloom.strength = model.kind === "activity" ? 0.48 : 0.24;
    this.bloom.threshold = model.kind === "activity" ? 0.62 : 0.8;
    this.group.rotation.x = model.layout === "ordinal" ? Math.PI / 2 : 0;
    this.group.updateMatrixWorld(true);
    this.glowTexture ??= this.texture("glow");
    this.ringTexture ??= this.texture("ring");
    const box = new THREE.Box3();
    for (const p of model.points) box.expandByPoint(V(p.position));
    for (const plane of model.planes) {
      const [a, b, c, d] = plane.bounds,
        y = plane.y,
        grid = [];
      for (let j = 0; j <= 24; j++) {
        const x = a + ((b - a) * j) / 24,
          z = c + ((d - c) * j) / 24;
        grid.push(
          { from: [x, y, c], to: [x, y, d] },
          { from: [a, y, z], to: [b, y, z] },
        );
      }
      this.line(grid, "#149cd6", 0.085);
      this.line(
        [
          { from: [a, y, c], to: [b, y, c] },
          { from: [b, y, c], to: [b, y, d] },
          { from: [b, y, d], to: [a, y, d] },
          { from: [a, y, d], to: [a, y, c] },
        ],
        "#43a9db",
        0.23,
      );
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(b - a, d - c),
        new THREE.MeshBasicMaterial({
          color: plane.color,
          transparent: true,
          opacity: 0.008,
          side: THREE.DoubleSide,
          depthWrite: false,
        }),
      );
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.set((a + b) / 2, y, (c + d) / 2);
      mesh.renderOrder = -2;
      this.group.add(mesh);
      box.expandByPoint(V([a, y, c]));
      box.expandByPoint(V([b, y, d]));
      this.label(
        plane.label +
          (plane.count !== undefined
            ? " · " + plane.kept + " / " + plane.count
            : ""),
        [a - 0.02, y, d + 0.06],
        plane.labelColor || "#4b91b5",
      );
      this.line(
        [
          { from: [a, y - 0.045, c], to: [b, y - 0.045, c] },
          { from: [b, y - 0.045, c], to: [b, y - 0.045, d] },
          { from: [b, y - 0.045, d], to: [a, y - 0.045, d] },
          { from: [a, y - 0.045, d], to: [a, y - 0.045, c] },
        ],
        "#878e7c",
        0.045,
      );
    }
    const top = Math.max(0, ...model.planes.map((p) => p.y)),
      bottom = Math.min(0, ...model.planes.map((p) => p.y));
    const p = model.planes[0];
    if (p) {
      const [a, b, c, d] = p.bounds;
      this.line(
        [
          [a, c],
          [a, d],
          [b, c],
          [b, d],
        ].map(([x, z]) => ({ from: [x, bottom, z], to: [x, top, z] })),
        0x858d7b,
        0.055,
      );
    }
    for (const kind of [
      "stem",
      "transition",
      "cue",
      "read",
      "prediction",
      "plan",
    ]) {
      const source = model.segments.filter((s) => s.kind === kind),
        colors = [...new Set(source.map((s) => s.color))];
      if (kind === "read" && model.kind === "hierarchy") {
        this.curveLinks(source);
        continue;
      }
      for (const color of colors) {
        const group = source.filter((s) => s.color === color);
        this.line(
          group.filter((s) => !s.dim),
          color,
          kind === "prediction"
            ? 1
            : kind === "plan"
              ? 0.8
              : kind === "read"
                ? 0.19
                : kind === "cue"
                  ? 0.5
                  : kind === "stem"
                    ? 0.06
                    : 0.14,
        );
        this.line(
          group.filter((s) => s.dim),
          color,
          0.055,
        );
      }
    }
    for (const kind of ["transition", "prediction"]) {
      const heads = model.segments
        .filter((s) => s.kind === kind)
        .flatMap((s) => {
          const v = V(s.to).sub(V(s.from));
          if (v.length() < 0.001) return [];
          const length = Math.min(
              kind === "prediction" ? 0.045 : 0.025,
              v.length() * 0.3,
            ),
            side = new THREE.Vector3(-v.z, 0, v.x)
              .normalize()
              .multiplyScalar(length * 0.5),
            base = V(s.to).sub(v.normalize().multiplyScalar(length));
          return [
            { ...s, from: base.clone().add(side).toArray() },
            { ...s, from: base.clone().sub(side).toArray() },
          ];
        });
      for (const color of new Set(heads.map((s) => s.color)))
        this.line(
          heads.filter((s) => s.color === color),
          color,
          kind === "prediction" ? 1 : 0.25,
        );
    }
    if (model.kind === "activity") {
      this.renderActivity(model);
      for (const p of model.points) box.expandByPoint(V(p.position));
      const [x0, x1, z0, z1, y0, y1] = model.volumeBounds;
      box.expandByPoint(V([x0, y0, z0]));
      box.expandByPoint(V([x1, y1, z1]));
    }
    const selected = model.points.filter((p) => p.selected);
    this.points(
      model.points.filter((p) => p.dim),
      2.7,
      0.42,
    );
    this.points(
      model.points.filter((p) => !p.dim),
      3.2,
      0.7,
    );
    this.points(
      selected.map((p) => ({
        ...p,
        color: model.kind === "memory" ? "#e2ce86" : p.color,
      })),
      12,
      0.13,
      this.glowTexture,
    );
    this.points(selected, 4, 0.95);
    this.points(
      model.points
        .filter((p) => p.returned)
        .map((p) => ({ ...p, color: "#edece4" })),
      8,
      0.75,
      this.ringTexture,
    );
    this.points(
      model.points
        .filter((p) => p.replayed)
        .map((p) => ({ ...p, color: "#baa2e6" })),
      10,
      1,
      this.ringTexture,
    );
    if (model.kind !== "activity") this.glyphs(model.points);
    if (model.layout === "ordinal") this.spanContours(model.points);
    for (const a of model.anchors) {
      this.points(
        [{ position: a.position, color: "#edece4" }],
        18,
        1,
        this.ringTexture,
      );
      this.label(a.label, a.position, "#edece4");
    }
    box.applyMatrix4(this.group.matrixWorld);
    const changedBounds = !this.box || !this.box.equals(box);
    this.box = box;
    this.center = box.getCenter(new THREE.Vector3());
    this.status.textContent =
      model.sourceCount +
      " " +
      (model.kind === "memory"
        ? "OBSERVATIONS"
        : model.kind === "task-memory" || model.lifecycleCloud
          ? "OBSERVED FACTS"
          : "INDEXED ORIGINALS") +
      " / " +
      model.readCount +
      " IN READ";
    this.caption.textContent = model.heightLabel;
    if (model.kind === "activity" && !this.reduced && model.readCount)
      this.replay(0.24);
    this.updateReadout(model);
    this.canvas.dataset.sourceCount = model.sourceCount;
    this.canvas.dataset.readCount = model.readCount;
    this.canvas.dataset.modelKey = model.key;
    this.canvas.dataset.geometryPoints = model.points.length;
    this.canvas.dataset.lifecycleCloud = String(!!model.lifecycleCloud);
    this.contextGrid.position.set(
      this.center.x,
      box.min.y - 0.3,
      this.center.z,
    );
    this.contextGrid.material.uniforms.radius.value = Math.max(
      8,
      box.getSize(new THREE.Vector3()).length() * 1.3,
    );
    if (transition.reset) this.reset(transition.duration);
    else if (changedBounds && !this.userCamera) this.reframe(previousSpan);
    else if (!gsap.isTweening(this.framing)) this.resize();
    this.highlight(this.focused);
    this.render();
    if (transition.fadeIn) {
      if (first)
        gsap.from(this.camera.position, {
          x: this.camera.position.x + 2.5,
          z: this.camera.position.z + 3,
          duration: 1.8,
          ease: "somna",
          onUpdate: () => (this.dirty = true),
        });
      let delay = 0;
      this.group.traverse((o) => {
        if (o.material && o.material.transparent) {
          const opacity = o.material.opacity;
          gsap.fromTo(
            o.material,
            { opacity: 0 },
            {
              opacity,
              duration: 0.9,
              delay: Math.min(0.5, (delay += 0.008)),
              ease: "somna",
              onUpdate: () => (this.dirty = true),
            },
          );
        }
      });
      this.replay();
    }
  }
  renderActivity(model) {
    const surface = new THREE.BufferGeometry(),
      vertices = [],
      colours = [];
    for (const p of model.triangles) {
      vertices.push(...p.position);
      colours.push(...new THREE.Color(p.color).toArray());
    }
    if (vertices.length) {
      surface.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(vertices, 3),
      );
      surface.setAttribute(
        "color",
        new THREE.Float32BufferAttribute(colours, 3),
      );
      const mesh = new THREE.Mesh(
        surface,
        new THREE.MeshBasicMaterial({
          vertexColors: true,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: 0.26,
          depthWrite: false,
        }),
      );
      this.group.add(mesh);
    } else surface.dispose();
    if (!model.cloudOnly) {
      const geometry = new THREE.BufferGeometry().setFromPoints(
        model.wire.flatMap((s) => [V(s.from), V(s.to)]),
      );
      geometry.setAttribute(
        "color",
        new THREE.Float32BufferAttribute(
          model.wire.flatMap((s) => {
            const c = new THREE.Color(s.color).toArray();
            return [...c, ...c];
          }),
          3,
        ),
      );
      this.group.add(
        new THREE.LineSegments(
          geometry,
          new THREE.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            opacity: 0.47,
            depthWrite: false,
          }),
        ),
      );
    }
    this.points(
      model.samples,
      model.cloudOnly ? 1.5 : 1.25,
      model.cloudOnly ? 0.9 : 0.75,
    );
    const [a, b, c, d, y0, y1] = model.volumeBounds;
    const corners = [
        [a, y0, c],
        [b, y0, c],
        [b, y0, d],
        [a, y0, d],
        [a, y1, c],
        [b, y1, c],
        [b, y1, d],
        [a, y1, d],
      ],
      edges = [
        [0, 1],
        [1, 2],
        [2, 3],
        [3, 0],
        [4, 5],
        [5, 6],
        [6, 7],
        [7, 4],
        [0, 4],
        [1, 5],
        [2, 6],
        [3, 7],
      ];
    this.line(
      edges.map(([i, j]) => ({ from: corners[i], to: corners[j] })),
      "#a9e6ff",
      0.36,
    );
    this.bloom.strength = 0.48;
    this.bloom.threshold = 0.62;
    this.contextGrid.visible = false;
    this.canvas.dataset.displaySamples = String(model.samples.length);
    this.canvas.dataset.surfaceTriangles = String(model.triangles.length / 3);
  }
  curveLinks(segments) {
    const lines = [];
    for (const s of segments) {
      const a = V(s.from),
        b = V(s.to),
        middle = a.clone().lerp(b, 0.5);
      middle.x += (b.z - a.z) * 0.12;
      if (this.model.layout === "arbor")
        middle.set(a.x, a.y + (b.y - a.y) * 0.7, a.z);
      const curve = new THREE.QuadraticBezierCurve3(a, middle, b);
      if (this.model.layout === "arbor") {
        const tube = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 20, s.radius || 0.012, 4, false),
          new THREE.MeshBasicMaterial({
            color: "#a6b7a0",
            transparent: true,
            opacity: 0.16,
            depthWrite: false,
          }),
        );
        this.group.add(tube);
      }
      this.traceCurves.push({ curve, level: s.level || 1 });
      const pts = curve.getPoints(12);
      for (let i = 1; i < pts.length; i++)
        lines.push({ from: pts[i - 1].toArray(), to: pts[i].toArray() });
    }
    this.line(lines, "#4edcff", 0.44);
    if (this.traceCurves.length) {
      this.traceHeads = this.points(
        this.traceCurves.map(({ curve }) => ({
          position: curve.getPoint(0).toArray(),
          color: "#f4e6ae",
        })),
        5,
        1,
      );
      this.traceHeads.visible = false;
    }
  }
  replay(duration = 2.2) {
    if (this.reduced || !this.model) return;
    this.canvas.dataset.traceReplay = String(
      Number(this.canvas.dataset.traceReplay || 0) + 1,
    );
    const source = this.traceCurves.length
      ? this.traceCurves
      : this.model.segments
          .filter((s) => s.kind === "read")
          .map((s) => ({
            curve: new THREE.LineCurve3(V(s.from), V(s.to)),
            level: 1,
          }));
    if (!source.length) return;
    if (!this.traceHeads) {
      this.traceCurves = source;
      this.traceHeads = this.points(
        source.map(({ curve }) => ({
          position: curve.getPoint(0).toArray(),
          color: "#f4e6ae",
        })),
        5,
        1,
      );
    }
    this.traceHeads.visible = true;
    gsap.fromTo(
      this.traceClock,
      { progress: 0 },
      {
        progress: 1,
        duration,
        ease: "somna",
        overwrite: true,
        onUpdate: () => (this.dirty = true),
        onComplete: () => {
          this.traceHeads.visible = false;
          this.dirty = true;
        },
      },
    );
  }
  glyphs(points) {
    const cells = [];
    const palette = [
      "#a6b6b1",
      "#91afa1",
      "#c1b296",
      "#b6b89e",
      "#aaa2b6",
      "#b2bcaa",
    ];
    for (const p of points)
      for (const [i, f] of (p.fields || []).entries()) {
        const value = Math.min(
          1,
          Math.abs(f.value) /
            (f.name === "x" || f.name === "y"
              ? 32
              : f.name === "object"
                ? 10
                : f.name === "salience"
                  ? 2
                  : 5),
        );
        cells.push({
          position: [
            p.position[0] + ((i % 3) - 1) * 0.045,
            p.position[1] + 0.012 + value * 0.018,
            p.position[2] + (Math.floor(i / 3) - 0.5) * 0.045,
          ],
          color: palette[i % palette.length],
          dim: p.dim,
        });
      }
    this.points(
      cells.filter((p) => p.dim),
      1.6,
      0.17,
    );
    this.points(
      cells.filter((p) => !p.dim),
      2.2,
      0.72,
    );
    this.canvas.dataset.channelGlyphs = cells.length;
  }
  spanContours(points) {
    for (const p of points.filter(
      (p) => p.level && p.selected && p.members?.length,
    )) {
      const xs = p.members.map((p) => p[0]),
        zs = p.members.map((p) => p[2]),
        a = Math.min(...xs) - 0.11,
        b = Math.max(...xs) + 0.11,
        c = Math.min(...zs) - 0.11,
        d = Math.max(...zs) + 0.11,
        y = p.position[1];
      this.line(
        [
          { from: [a, y, c], to: [b, y, c] },
          { from: [b, y, c], to: [b, y, d] },
          { from: [b, y, d], to: [a, y, d] },
          { from: [a, y, d], to: [a, y, c] },
        ],
        "#a1ad94",
        0.055,
      );
    }
  }
  updateReadout(model) {
    if (!this.readout) return;
    this.readout.replaceChildren();
    if (["task-memory", "activity"].includes(model.kind)) return;
    const heading = document.createElement("p");
    heading.className = "console-kicker";
    heading.textContent = "Routing population";
    this.readout.append(heading);
    for (const l of model.readout || []) {
      const row = document.createElement("div");
      row.className = "readout-row";
      const label = document.createElement("span");
      label.textContent = l.label;
      const bar = document.createElement("i");
      bar.style.setProperty(
        "--kept",
        (100 * l.kept) / Math.max(1, l.count) + "%",
      );
      const count = document.createElement("span");
      count.textContent = l.kept + " / " + l.count;
      row.append(label, bar, count);
      this.readout.append(row);
    }
    const hint = document.createElement("p");
    hint.className = "readout-hint";
    hint.textContent = "Expanded / scored · this recorded read";
    this.readout.append(hint);
    const key = document.createElement("div");
    key.className = "channel-key";
    for (const [name, color] of [
      ["X", "#8dbecf"],
      ["Y", "#7ac9bf"],
      ["Object", "#e4b56f"],
      ["Colour", "#c7c97b"],
      ["State", "#a990c9"],
    ]) {
      const item = document.createElement("span"),
        dot = document.createElement("i");
      dot.style.background = color;
      item.append(dot, document.createTextNode(name));
      key.append(item);
    }
    this.readout.append(key);
    const note = document.createElement("p");
    note.className = "readout-hint";
    note.textContent = "Glyph height: normalised magnitude. Hover for values.";
    this.readout.append(note);
  }
  reframe(previousSpan) {
    const offset = this.camera.position.clone().sub(this.controls.target);
    this.resize();
    const goalSpan = this.span,
      duration = this.reduced ? 0 : 0.42;
    gsap.killTweensOf(this.framing);
    this.framing = { span: previousSpan || goalSpan };
    this.applySpan(this.framing.span);
    gsap.to(this.framing, {
      span: goalSpan,
      duration,
      ease: "somna",
      onUpdate: () => this.applySpan(this.framing.span),
    });
    gsap.to(this.controls.target, {
      x: this.center.x,
      y: this.center.y,
      z: this.center.z,
      duration,
      ease: "somna",
      overwrite: true,
      onUpdate: () => {
        this.dirty = true;
      },
    });
    gsap.to(this.camera.position, {
      x: this.center.x + offset.x,
      y: this.center.y + offset.y,
      z: this.center.z + offset.z,
      duration,
      ease: "somna",
      overwrite: true,
      onUpdate: () => {
        this.dirty = true;
      },
    });
    this.canvas.dataset.reframe = "eased";
  }
  reset(duration = this.reduced ? 0 : 0.7) {
    if (!this.model) return;
    this.userCamera = false;
    this.controls.autoRotate = false;
    this.overlay
      .querySelector("[aria-pressed]")
      ?.setAttribute("aria-pressed", "false");
    this.resize();
    this.camera.zoom = 1;
    this.camera.updateProjectionMatrix();
    const target = this.center,
      offset =
        this.mode === "plane"
          ? new THREE.Vector3(0, 9, 0.001)
          : new THREE.Vector3(5, 3, 7);
    gsap.to(this.controls.target, {
      x: target.x,
      y: target.y,
      z: target.z,
      duration,
      ease: "somna",
      overwrite: true,
      onUpdate: () => {
        this.dirty = true;
      },
    });
    gsap.to(this.camera.position, {
      x: target.x + offset.x,
      y: target.y + offset.y,
      z: target.z + offset.z,
      duration,
      ease: "somna",
      overwrite: true,
      onUpdate: () => {
        this.dirty = true;
      },
    });
    if (!duration) {
      this.controls.update();
      this.render();
    }
  }
  setMode(mode) {
    if (this.mode === mode) return;
    this.mode = mode;
    this.reset();
  }
  focus() {
    this.userCamera = true;
    const points = this.model?.points.filter(
      (p) => p.id === this.focused || (!this.focused && p.selected),
    );
    if (!points?.length) return;
    const center = new THREE.Vector3();
    for (const p of points) center.add(V(p.position));
    center.divideScalar(points.length);
    center.applyMatrix4(this.group.matrixWorld);
    const offset = this.camera.position.clone().sub(this.controls.target);
    const duration = this.reduced ? 0 : 0.65;
    gsap.to(this.controls.target, {
      x: center.x,
      y: center.y,
      z: center.z,
      duration,
      ease: "somna",
      overwrite: true,
    });
    gsap.to(this.camera.position, {
      x: center.x + offset.x,
      y: center.y + offset.y,
      z: center.z + offset.z,
      duration,
      ease: "somna",
      overwrite: true,
    });
    gsap.to(this.camera, {
      zoom: Math.min(2.2, this.camera.zoom * 1.3),
      duration,
      ease: "somna",
      onUpdate: () => {
        this.camera.updateProjectionMatrix();
        this.dirty = true;
      },
    });
  }
  highlight(id) {
    if (this.focused === id && (this.focusMarker || id === null)) return;
    this.focused = id;
    if (this.focusMarker) {
      this.group.remove(this.focusMarker);
      this.focusMarker.geometry.dispose();
      this.focusMarker.material.dispose();
      this.focusMarker = null;
    }
    const p = this.model?.points.find((p) => p.id === id);
    if (p)
      this.focusMarker = this.points(
        [{ ...p, color: "#fff" }],
        13,
        1,
        this.ringTexture,
      );
    this.dirty = true;
  }
  project(position) {
    const p = V(position)
      .applyMatrix4(this.group.matrixWorld)
      .project(this.camera);
    return {
      x: ((p.x + 1) * this.width) / 2,
      y: ((1 - p.y) * this.height) / 2,
      z: p.z,
    };
  }
  pick(e) {
    if (!this.model) return null;
    const r = this.canvas.getBoundingClientRect(),
      x = e.clientX - r.left,
      y = e.clientY - r.top;
    let best = null,
      d = 144;
    for (const p of this.model.points) {
      const q = this.project(p.position),
        delta = (q.x - x) ** 2 + (q.y - y) ** 2;
      if (q.z >= -1 && q.z <= 1 && delta < d) {
        best = p;
        d = delta;
      }
    }
    return best;
  }
  ground(e) {
    if (!this.model?.queryBounds) return null;
    const r = this.canvas.getBoundingClientRect();
    this.pointer.set(
      ((e.clientX - r.left) / r.width) * 2 - 1,
      (-(e.clientY - r.top) / r.height) * 2 + 1,
    );
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.ray.intersectPlane(
      new THREE.Plane(new THREE.Vector3(0, 1, 0), -this.model.queryPlane),
      new THREE.Vector3(),
    );
    if (!hit) return null;
    const [a, b, c, d] = this.model.queryBounds;
    return hit.x >= a && hit.x <= b && hit.z >= c && hit.z <= d
      ? [hit.x, hit.z]
      : null;
  }
  showTip(point) {
    this.tip.hidden = !point;
    if (!point) return;
    this.tip.textContent =
      point.label +
      "\n" +
      point.detail +
      (point.fields?.length
        ? "\n" +
          point.fields
            .map((f) => f.name + " " + Number(f.value.toFixed(3)))
            .join(" · ")
        : "");
    const p = this.project(point.position);
    this.tip.style.transform = `translate(${Math.min(this.width - 228, Math.max(8, p.x + 12))}px,${Math.min(this.height - 70, Math.max(40, p.y - 20))}px)`;
  }
  render() {
    if (!this.width || !this.height) return;
    if (this.traceHeads?.visible) {
      const attr = this.traceHeads.geometry.attributes.position,
        max = Math.max(...this.traceCurves.map((c) => c.level));
      for (let i = 0; i < this.traceCurves.length; i++) {
        const item = this.traceCurves[i],
          phase = Math.max(
            0,
            Math.min(
              1,
              this.traceClock.progress * (max + 1) - (max - item.level),
            ),
          );
        const p = item.curve.getPoint(phase);
        attr.setXYZ(i, p.x, p.y, p.z);
      }
      attr.needsUpdate = true;
    }
    this.composer.render();
    const occupied = [];
    for (const l of this.labels) {
      const p = this.project(l.position);
      l.el.hidden =
        p.z > 1 || p.x < 0 || p.x > this.width || p.y < 0 || p.y > this.height;
      if (l.el.hidden) continue;
      const full = l.el.dataset.fullLabel;
      const label =
        this.width < 500
          ? full.replace(" / SUMMARIES", "").replace(" / ORIGINALS", "")
          : full;
      if (l.el.textContent !== label) {
        l.el.textContent = label;
        l.width = null;
      }
      const width = l.width ?? (l.width = l.el.offsetWidth);
      const x = Math.max(8, Math.min(this.width - width - 8, p.x));
      let y = null;
      for (const offset of [0, -20, 20, -40, 40, -60, 60, -80, 80]) {
        const candidate = { x, y: p.y + offset, w: width, h: 16 };
        if (
          candidate.y >= 8 &&
          candidate.y + 16 < this.height &&
          !occupied.some(
            (o) =>
              candidate.x < o.x + o.w + 8 &&
              candidate.x + candidate.w + 8 > o.x &&
              candidate.y < o.y + o.h + 4 &&
              candidate.y + candidate.h + 4 > o.y,
          )
        ) {
          y = candidate.y;
          break;
        }
      }
      if (y === null) {
        l.el.hidden = true;
        continue;
      }
      occupied.push({ x, y, w: width, h: 16 });
      l.el.style.transform = `translate(${x}px,${y}px)`;
    }
    this.dirty = false;
    this.canvas.dataset.renderCount = String(
      Number(this.canvas.dataset.renderCount || 0) + 1,
    );
  }
  dispose() {
    gsap.ticker.remove(this.ticker);
    this.resizeObserver.disconnect();
    this.observer.disconnect();
    this.controls.dispose();
    gsap.killTweensOf([
      this.framing,
      this.camera.position,
      this.controls.target,
      this.camera,
    ]);
    this.contextGrid.geometry.dispose();
    this.contextGrid.material.dispose();
    this.clear();
    this.glowTexture?.dispose();
    this.ringTexture?.dispose();
    this.composer.dispose();
    this.bloom.dispose();
    this.renderer.dispose();
    this.overlay.remove();
  }
}
export function create(options) {
  if (new URLSearchParams(location.search).get("renderer") === "canvas")
    return null;
  try {
    return new SpatialView(options);
  } catch (error) {
    const clone = options.canvas.cloneNode(true);
    options.canvas.replaceWith(clone);
    clone.dataset.renderer = "canvas";
    console.warn(
      "Spatial view unavailable; using the canvas view.",
      error.message,
    );
    return null;
  }
}
