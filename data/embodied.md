## Embodied Motion Recovery & Robot Tracking

From **human/hand reconstruction** to **robot-executable motion**: video or XR sensing → human motion (SMPL/SMPL-X/MANO or joints) → robot retargeting → tracking/control. Entries are marked **Recovery**, **Retargeting**, or **Tracking** so downstream robotics methods are not mistaken for mesh-recovery algorithms. XR/MoCap- and language-driven systems are explicitly identified. This is a manually curated bridge to embodied AI, maintained in [`data/embodied.md`](data/embodied.md) (curated 2026-11-23), and is not included in the automatically harvested paper count above.

### Whole-Body: Human Motion to Humanoid Robots

1. **GVHMR: World-Grounded Human Motion Recovery via Gravity-View Coordinates** — SIGGRAPH Asia 2024 / TPAMI 2026. **Recovery:** monocular video to world-grounded human motion, useful upstream of robot retargeting. [Paper](https://arxiv.org/abs/2409.06662) · [Code](https://github.com/zju3dv/GVHMR)
2. **OnlineHMR: Video-based Online World-Grounded Human Mesh Recovery** — CVPR 2026. **Recovery:** causal, streaming video-to-SMPL motion; a perception component, **not** a demonstrated robot tracking policy. [Paper](https://arxiv.org/abs/2603.17355) · [Code](https://github.com/Tsukasane/Video-OnlineHMR)
3. **ExMR: Extremity Motion Refinement for Monocular Human Motion Capture** — 2026. **Recovery → Retargeting:** monocular body/hand/foot motion in SMPL-X, with humanoid export through GMR. [Paper](https://arxiv.org/abs/2610.26213) · [Code](https://github.com/twehrbein/ExMR)
4. **GMR: General Motion Retargeting** — ICRA 2026. **Retargeting:** maps human motion (including GVHMR outputs) onto multiple humanoid embodiments, including Unitree G1; it is a bridge, not an HMR method. [Paper](https://arxiv.org/abs/2510.02252) · [Code](https://github.com/YanjieZe/GMR)
5. **TWIST: Teleoperated Whole-Body Imitation System** — CoRL 2025. **Tracking:** a whole-body humanoid reference tracker trained with RL/BC from retargeted human MoCap data. [Paper](https://arxiv.org/abs/2505.02833) · [Code](https://github.com/YanjieZe/TWIST)
6. **TWIST2: Scalable, Portable, and Holistic Humanoid Data Collection System** — ICRA 2026. **XR Teleoperation → Tracking:** PICO 4 Ultra human-motion input, retargeting and whole-body tracking on Unitree G1; not camera-based mesh recovery. [Paper](https://arxiv.org/abs/2511.02832) · [Code](https://github.com/amazon-far/TWIST2)

### Hand-Object Recovery to Dexterous Robot Control

1. **Hand2Robot: Object-Centric 4D Hand Reconstruction from Human Demonstrations for Robotics** — 2026. **Recovery → Retargeting:** contact-aware hand/object reconstruction from human video, producing supervision for robot policy post-training. [Paper](https://arxiv.org/abs/2610.15769)
2. **OmniHOI: Dexterous Hand-Object Interaction from Monocular Human Video** — 2026. **Recovery → Retargeting → Physics:** video-based hand-object interaction recovery and physically refined robot-hand trajectories. [Paper](https://arxiv.org/abs/2610.10855)
3. **VideoManip: Dexterous Manipulation Policies from RGB Human Videos via 4D Hand-Object Trajectory Reconstruction** — 2026. **Recovery → Robot Learning:** reconstructs hand/object trajectories and retargets them to dexterous hands, including LEAP Hand experiments. [Paper](https://arxiv.org/abs/2602.09013) · [Code (reconstruction pipeline released)](https://github.com/hychen-naza/VideoManip)
4. **Do as I Do: Dexterous Manipulation Data from Everyday Human Videos** — 2026. **Recovery → Retargeting → Execution:** reconstructs monocular hand-object demonstrations, optimizes robot-hand actions and supports real-world replay. [Paper](https://arxiv.org/abs/2606.19333) · [Code](https://github.com/malik-group/do-as-i-do)
5. **UniDex: A Robot Foundation Suite for Universal Dexterous Hand Control from Egocentric Human Videos** — CVPR 2026. **Hand Tracking → Retargeting → Policy:** converts egocentric human-hand data to multiple robot hands for policy learning; focuses on the downstream robot learning suite. [Paper](https://arxiv.org/abs/2603.22264) · [Code](https://github.com/unidex-ai/UniDex)
6. **AdaDexTrack: Dynamic Modulation for Adaptive and Generalizable Dexterous Manipulation Tracking** — CVPR 2026. **Downstream Tracking:** tracks and corrects retargeted, language-generated hand-object references on robot hardware; **not** a hand mesh reconstruction method. [Paper](https://arxiv.org/abs/2610.33852) · [Code](https://github.com/Janebek/AdaDexTrack)

### Retargeting Toolkit

- **dex-retargeting (AnyTeleop)** — **Retargeting:** reusable optimizers translating estimated human-hand motion into robot-hand joint targets; supports video- and dataset-based examples. [Code](https://github.com/dexsuite/dex-retargeting)
