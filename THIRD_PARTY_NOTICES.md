# Third-party notices

Our numerical implementation, research adapters and dashboard source are Apache 2.0 under [LICENSE](LICENSE). This does not relicense third-party dependencies, fonts, data or bundled libraries.

| Component | Use | Notice / source |
| --- | --- | --- |
| Zyphra Hierarchical Attention paper | Method reference and attribution; independent implementation | [Paper](https://arxiv.org/abs/2610.42112), [method map](docs/METHOD.md) |
| Three.js | Local WebGL rendering and OrbitControls | MIT; [retained license](web/visuals/licenses/THREE.txt), [source](https://github.com/mrdoob/three.js) |
| GSAP / CustomEase | Camera and presentation transitions | [Standard No Charge license](https://gsap.com/standard-license/); proprietary notices remain in bundled assets. GSAP is not relicensed as Apache 2.0. |
| Geist fonts | Dashboard typography | SIL OFL 1.1; [retained notice](web/somna-live/fonts/OFL.txt) |
| Boxoban levels | Official puzzle fixtures | Apache 2.0; [retained license](data/boxoban/LICENSE), [attribution](data/boxoban/README.md) |
| MiniGrid | Official partial-observation task environments | Installed benchmark dependency; [source and upstream license](https://github.com/Farama-Foundation/Minigrid) |
| GPT-2 / Transformers / PyTorch | Optional captured-layer experiments and numerical execution | Dependencies/models retain their upstream licenses; revisions and artifacts are recorded per experiment. Model weights are not distributed in the numerical package. |

The wheel and core source distribution exclude research datasets, browser bundles and experiment archives. The Git checkout retains them with their evidence and notices. See [rendering dependencies](web/visuals/THIRD_PARTY.md) for pinned renderer versions and rebuild instructions.
