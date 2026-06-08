# KITTI edge benchmark spec

## Section 1: Input definition

Datasets used:
- KITTI 3D Object Detection: 7,481 training frames, Velodyne lidar + calibration + labels
- Data location: `$GITM_DATA_ROOT/datasets/kitti/object/training/`
- Directory layout:
  - `velodyne/`   — 000000.bin … 007480.bin  (float32 XYZI point clouds)
  - `calib/`      — 000000.txt … 007480.txt  (camera-lidar calibration)
  - `label_2/`    — 000000.txt … 007480.txt  (3D bounding box annotations)
- Manifest: `benchmarks/kitti/manifest.yaml`
  - Every file sha256-verified. Pass/fail gated by `python harness/verify_manifest.py`.

## Section 2: Work unit

One frame processed end-to-end through:

    voxelization → 3D backbone (PointPillars) → BEV head → NMS → detections

Model: OpenPCDet CenterPoint config on PointPillars backbone

Pinned OpenPCDet commit: [TBD — fill in after cloning on RunPod]
Pinned config sha256: [TBD — sha256sum tools/cfgs/kitti_models/pointpillar.yaml]
Checkpoint: `pointpillar_7728.pth`
Checkpoint sha256: c9c84e5cf1059b84fb37a4d47f8e58fc16b22e2c3e9ddf47ed59700d7b0e9ccd

Stage breakdown per frame:
1. Load .bin (np.fromfile) — CPU / data stall
2. Voxelization + H2D copy — CPU / data stall
3. Backbone + BEV head — GPU active
4. NMS + box assembly — CPU / sync stall

## Section 3: Success metric

- Top-line metric: `frames_per_second` (warm window)
- Warm-up: 100 frames discarded before timing begins
- Warm window: 7,381 frames (all training frames minus warmup)
- Three seeds (42, 43, 44) must agree within 2%
- Auxiliary metric: `total_detections` per run (sanity check, not a target)
- GPU active % must be < 85% (saturation check)

Baseline result:

| Seed | fps | GPU active % | Data stall % | Sync % | CPU % |
|------|-----|--------------|-------------|--------|-------|
| 42   | TBD | TBD          | TBD         | TBD    | TBD   |
| 43   | TBD | TBD          | TBD         | TBD    | TBD   |
| 44   | TBD | TBD          | TBD         | TBD    | TBD   |
| Mean | TBD | TBD          | TBD         | TBD    | TBD   |
| Stddev | TBD | TBD        | TBD         | TBD    | TBD   |

3-seed fps within 2%: TBD

## Section 4: Expected stall profile

Expected from architecture analysis (fill in from measured baselines):

| Category | What it is | Expected % | Measured % |
|----------|-----------|------------|------------|
| Data stall | lidar .bin decode + host-side voxelization + H2D copy | 20–35% | TBD |
| Sync stall | NMS serialization on CPU | 10–20% | TBD |
| GPU active | backbone + BEV head forward pass | 50–65% | TBD |
| CPU overhead | Python dispatch, dataloader | ~5% | TBD |

**Critical check:** GPU active must be < 85%. If saturated, flag Adit same day
for 500-frame shard fallback.

**Stream-concurrency check (nsys):** host-side voxelization of frame N+1 should
overlap device-side backbone inference on frame N. Capture nsys timeline and
commit screenshot to `benchmarks/kitti/results.md`. If overlap is absent, the
stream-concurrency invariant has no signal — flag Adit immediately.

## Environment

Machine: [TBD — fill in after RunPod setup]
Driver version: [TBD]
GPU: [TBD]
OpenPCDet commit: [TBD]
Date: [TBD]
