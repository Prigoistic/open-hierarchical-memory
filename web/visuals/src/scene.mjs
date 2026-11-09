import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { gsap } from "gsap";
import { CustomEase } from "gsap/CustomEase";
export { memoryModel, hierarchyModel } from "./models.mjs";
gsap.registerPlugin(CustomEase);
CustomEase.create("somna", "0.22,1,0.36,1");
const V = (p) => new THREE.Vector3(...p);
export class SpatialView {
  constructor({ canvas, onPick, onQuery, onHover }) {
    this.canvas = canvas;
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
    this.renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x000000);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.camera = new THREE.OrthographicCamera(-4, 4, 3, -3, 0.01, 100);
    this.camera.position.set(5, 5, 7);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.target.set(0, 1, 0);
    this.controls.enableDamping = !this.reduced;
    this.controls.dampingFactor = 0.12;
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
        gsap.isTweening(this.controls.target)
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
    const aspect = r.width / r.height;
    this.fitSpan(aspect);
    const span = this.span || 5.5;
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
    this.span = Math.max(2, height, width / aspect) * 1.35;
  }
  clear() {
    this.group.traverse((o) => {
      o.geometry?.dispose();
      if (o.material) {
        for (const m of Array.isArray(o.material) ? o.material : [o.material])
          m.dispose();
      }
    });
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
    el.textContent = text;
    el.style.color = color;
    this.overlay.append(el);
    this.labels.push({ el, position: V(position) });
  }
  setData(model) {
    if (this.model?.key === model.key) return;
    const first = !this.model;
    this.model = model;
    this.clear();
    this.glowTexture ??= this.texture("glow");
    this.ringTexture ??= this.texture("ring");
    const box = new THREE.Box3();
    for (const p of model.points) box.expandByPoint(V(p.position));
    for (const plane of model.planes) {
      const [a, b, c, d] = plane.bounds,
        y = plane.y,
        grid = [];
      for (let j = 0; j <= 8; j++) {
        const x = a + ((b - a) * j) / 8,
          z = c + ((d - c) * j) / 8;
        grid.push(
          { from: [x, y, c], to: [x, y, d] },
          { from: [a, y, z], to: [b, y, z] },
        );
      }
      this.line(grid, plane.color, 0.085);
      this.line(
        [
          { from: [a, y, c], to: [b, y, c] },
          { from: [b, y, c], to: [b, y, d] },
          { from: [b, y, d], to: [a, y, d] },
          { from: [a, y, d], to: [a, y, c] },
        ],
        plane.color,
        0.38,
      );
      const mesh = new THREE.Mesh(
        new THREE.PlaneGeometry(b - a, d - c),
        new THREE.MeshBasicMaterial({
          color: plane.color,
          transparent: true,
          opacity: 0.018,
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
      this.label(plane.label, [a - 0.02, y, d + 0.06], plane.color);
    }
    const top = Math.max(...model.planes.map((p) => p.y)),
      bottom = Math.min(...model.planes.map((p) => p.y));
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
        0x738582,
        0.13,
      );
    }
    for (const kind of ["stem", "transition", "cue", "read", "prediction"]) {
      const source = model.segments.filter((s) => s.kind === kind),
        colors = [...new Set(source.map((s) => s.color))];
      for (const color of colors) {
        const group = source.filter((s) => s.color === color);
        this.line(
          group.filter((s) => !s.dim),
          color,
          kind === "prediction"
            ? 1
            : kind === "read"
              ? 0.4
              : kind === "cue"
                ? 0.5
                : kind === "stem"
                  ? 0.13
                  : 0.18,
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
    const selected = model.points.filter((p) => p.selected);
    this.points(
      model.points.filter((p) => p.dim),
      2.7,
      0.2,
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
      18,
      0.24,
      this.glowTexture,
    );
    this.points(selected, 5.1, 1);
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
    for (const a of model.anchors) {
      this.points(
        [{ position: a.position, color: "#edece4" }],
        18,
        1,
        this.ringTexture,
      );
      this.label(a.label, a.position, "#edece4");
    }
    const changedBounds = !this.box || !this.box.equals(box);
    this.box = box;
    this.center = box.getCenter(new THREE.Vector3());
    this.status.textContent =
      model.sourceCount +
      " " +
      (model.kind === "memory" ? "OBSERVATIONS" : "INDEXED ORIGINALS") +
      " / " +
      model.readCount +
      " IN READ";
    this.caption.textContent = model.heightLabel;
    this.canvas.dataset.sourceCount = model.sourceCount;
    this.canvas.dataset.readCount = model.readCount;
    this.canvas.dataset.modelKey = model.key;
    this.canvas.dataset.geometryPoints = model.points.length;
    if (first || (changedBounds && !this.userCamera)) this.reset(0);
    else this.resize();
    this.highlight(this.focused);
    this.render();
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
    const p = V(position).project(this.camera);
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
    this.tip.textContent = point.label + "\n" + point.detail;
    const p = this.project(point.position);
    this.tip.style.transform = `translate(${Math.min(this.width - 228, Math.max(8, p.x + 12))}px,${Math.min(this.height - 70, Math.max(40, p.y - 20))}px)`;
  }
  render() {
    if (!this.width || !this.height) return;
    this.renderer.render(this.scene, this.camera);
    for (const l of this.labels) {
      const p = this.project(l.position);
      l.el.hidden =
        p.z > 1 || p.x < 0 || p.x > this.width || p.y < 0 || p.y > this.height;
      l.el.style.transform = `translate(${p.x}px,${p.y}px)`;
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
    this.clear();
    this.glowTexture?.dispose();
    this.ringTexture?.dispose();
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
