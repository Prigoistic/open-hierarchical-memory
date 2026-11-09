# Rendering dependencies

Three.js0.187.0 provides the WebGL renderer and OrbitControls. Source: https://github.com/mrdoob/three.js. MIT license retained in licenses/THREE.txt and the bundled source.

GSAP3.15.1 and CustomEase provide camera and view transitions. Source: https://github.com/greensock/GSAP. Standard No Charge license: https://gsap.com/standard-license/. The library's proprietary notices remain in the bundle. This research interface is not a visual animation authoring tool.

The package lock pins downloaded npm artifacts. Run `npm ci --ignore-scripts` followed by `npm run build` here. The generated assets are served locally by the two Python apps; no runtime CDN requests are made. Esbuild0.28.2 is a build dependency. Camera motion is presentation only; rendering does not change experimental data or provide a numerical GPU backend.
