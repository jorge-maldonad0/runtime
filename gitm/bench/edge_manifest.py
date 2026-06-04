"""Build the edge/robotics ``manifest.jsonl`` — one row per keyframe.

The edge benchmark combines two datasets with different on-disk shapes into a
single flat work-list: ``{scene_id, frame_id, lidar_path, gt_path}`` per
keyframe, ~47 k rows across nuScenes (full) + KITTI (object). The runtime then
iterates rows without caring which dataset a frame came from.

Both readers are metadata-only — they enumerate keyframes from the standard
directory layout and JSON tables, with no nuScenes devkit or KITTI SDK
dependency, so this runs anywhere the staged dataset is visible. Paths are
emitted relative to the dataset root so the manifest is location-independent.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class KeyframeRow:
    scene_id: str
    frame_id: str
    lidar_path: str  # relative to the edge dataset root
    gt_path: str  # KITTI: label file; nuScenes: sample token (annotation key)
    source: str  # "nuscenes" | "kitti"


def iter_nuscenes(root: str | Path, *, version: str = "v1.0-trainval") -> Iterator[KeyframeRow]:
    """Enumerate nuScenes keyframes from the metadata JSON tables.

    Joins ``sample`` (keyframe) -> ``scene`` (name) and selects the matching
    ``LIDAR_TOP`` ``sample_data``. nuScenes stores annotations per *sample*
    rather than per file, so ``gt_path`` carries the sample token — the lookup
    key into ``sample_annotation`` — keeping every row's shape uniform.
    """
    meta = Path(root) / version
    if not meta.is_dir():
        raise NotADirectoryError(f"nuScenes metadata not found: {meta}")

    scenes = {s["token"]: s["name"] for s in _load_table(meta / "scene.json")}
    samples = _load_table(meta / "sample.json")
    sample_data = _load_table(meta / "sample_data.json")

    # Keyframe LIDAR_TOP files, indexed by their sample token.
    lidar_by_sample: dict[str, str] = {}
    for sd in sample_data:
        if not sd.get("is_key_frame"):
            continue
        fn = sd.get("filename", "")
        # Conventional layout: samples/LIDAR_TOP/<scene>__LIDAR_TOP__<ts>.pcd.bin
        if "LIDAR_TOP" in fn and fn.startswith("samples/"):
            lidar_by_sample[sd["sample_token"]] = fn

    for s in samples:
        token = s["token"]
        lidar = lidar_by_sample.get(token)
        if lidar is None:
            continue
        scene_name = scenes.get(s["scene_token"], s["scene_token"])
        yield KeyframeRow(
            scene_id=scene_name,
            frame_id=token,
            lidar_path=lidar,
            gt_path=token,  # annotation lookup key
            source="nuscenes",
        )


def iter_kitti(root: str | Path, *, split: str = "training") -> Iterator[KeyframeRow]:
    """Enumerate KITTI object frames from ``velodyne/`` + ``label_2/``.

    KITTI object frames are zero-padded numeric ids; each has a ``.bin`` point
    cloud and (in ``training``) a ``label_2/<id>.txt`` ground-truth file.
    """
    base = Path(root) / split
    velo = base / "velodyne"
    if not velo.is_dir():
        raise NotADirectoryError(f"KITTI velodyne dir not found: {velo}")
    labels = base / "label_2"

    for bin_path in sorted(velo.glob("*.bin")):
        fid = bin_path.stem
        gt = labels / f"{fid}.txt"
        yield KeyframeRow(
            scene_id=f"kitti_{split}",
            frame_id=fid,
            lidar_path=bin_path.relative_to(root).as_posix(),
            gt_path=(gt.relative_to(root).as_posix() if gt.exists() else ""),
            source="kitti",
        )


def build_manifest(
    edge_root: str | Path,
    *,
    nuscenes_subdir: str = "nuscenes",
    kitti_subdir: str = "kitti",
    nuscenes_version: str = "v1.0-trainval",
    kitti_split: str = "training",
) -> list[KeyframeRow]:
    """Build the combined keyframe list across both datasets.

    Either dataset may be absent (a pair can land nuScenes before KITTI) — a
    missing subdir is skipped with no row, not an error, so the manifest grows
    monotonically as data lands.
    """
    edge_root = Path(edge_root)
    rows: list[KeyframeRow] = []

    nusc = edge_root / nuscenes_subdir
    if (nusc / nuscenes_version).is_dir():
        rows.extend(iter_nuscenes(nusc, version=nuscenes_version))

    kitti = edge_root / kitti_subdir
    if (kitti / kitti_split / "velodyne").is_dir():
        rows.extend(iter_kitti(kitti, split=kitti_split))

    return rows


def write_manifest(rows: list[KeyframeRow], out: str | Path) -> Path:
    out = Path(out)
    with open(out, "w") as fh:
        for row in rows:
            fh.write(json.dumps(asdict(row)) + "\n")
    return out


def _load_table(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(f"nuScenes table missing: {path}")
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a JSON list table")
    return data
