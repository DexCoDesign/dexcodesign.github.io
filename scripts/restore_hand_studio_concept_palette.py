#!/usr/bin/env python3
"""Restore authored AI-concept colors in published GLBs without changing geometry.

The exporter groups visual meshes by color in first-seen URDF order. The
metadata retains that order and each original visual color as ``source_rgba``.
"""

import copy
import json
import struct
from collections import defaultdict
from pathlib import Path

from recolor_hand_studio_display import ROOT, chunks_of


def restore(model_id):
    path = ROOT / f"{model_id}.glb"
    metadata_path = ROOT / f"{model_id}.json"
    raw = path.read_bytes()
    chunks = chunks_of(raw)
    document = json.loads(chunks[0][1])
    metadata = json.loads(metadata_path.read_text())
    if metadata["category"] != "ai":
        raise ValueError(f"Not an AI concept: {model_id}")

    groups = defaultdict(list)
    for row in metadata["materials"]:
        rgba = row.get("source_rgba") or row["rgba"]
        if rgba not in groups[row["link"]]:
            groups[row["link"]].append(rgba)

    targets = {}
    for node in document["nodes"]:
        name = node.get("name", "")
        if not name.startswith("visual__") or "mesh" not in node:
            continue
        link, index = name.removeprefix("visual__").rsplit("__", 1)
        palette = groups[link]
        index = int(index)
        if index >= len(palette):
            raise ValueError(f"Missing authored palette entry: {model_id}/{name}")
        targets[name] = palette[index]
    for link, palette in groups.items():
        count = sum(name.startswith(f"visual__{link}__") for name in targets)
        if count != len(palette):
            raise ValueError(f"Grouped visual mismatch: {model_id}/{link}: {count}/{len(palette)}")

    originals = document["materials"][:]
    material_cache = {}
    changed = 0
    for node in document["nodes"]:
        rgba = targets.get(node.get("name"))
        if rgba is None:
            continue
        for primitive in document["meshes"][node["mesh"]]["primitives"]:
            old = primitive["material"]
            pbr = originals[old]["pbrMetallicRoughness"]
            if (pbr.get("baseColorFactor") == rgba and pbr.get("metallicFactor") == .12
                    and pbr.get("roughnessFactor") == .56):
                continue
            key = old, tuple(rgba)
            if key not in material_cache:
                material = copy.deepcopy(originals[old])
                material["pbrMetallicRoughness"].update(
                    baseColorFactor=rgba, metallicFactor=.12, roughnessFactor=.56
                )
                material_cache[key] = len(document["materials"])
                document["materials"].append(material)
            primitive["material"] = material_cache[key]
            changed += 1

    metadata_changed = False
    for row in metadata["materials"]:
        source = row.get("source_rgba") or row["rgba"]
        if row["rgba"] != source or row["origin"] != "urdf" or "display_reference" in row:
            row["rgba"] = source
            row["origin"] = "urdf"
            for key in ("display_reference", "display_metalness", "display_roughness"):
                row.pop(key, None)
            metadata_changed = True
    if not changed and not metadata_changed:
        return 0

    referenced = sorted({p["material"] for mesh in document["meshes"] for p in mesh["primitives"]})
    compact = {old: new for new, old in enumerate(referenced)}
    document["materials"] = [document["materials"][old] for old in referenced]
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            primitive["material"] = compact[primitive["material"]]
    body = json.dumps(document, separators=(",", ":")).encode()
    body += b" " * (-len(body) % 4)
    payloads = [(b"JSON", body), chunks[1]]
    serialized = [struct.pack("<I4s", len(data), kind) + data for kind, data in payloads]
    result = struct.pack("<4sII", b"glTF", 2, 12 + sum(map(len, serialized))) + b"".join(serialized)
    if chunks_of(result)[1] != chunks[1]:
        raise AssertionError("The mesh geometry changed")
    metadata["bytes"] = len(result)
    path.write_bytes(result)
    metadata_path.write_text(json.dumps(metadata, separators=(",", ":")) + "\n")
    return changed


def main():
    catalog_path = ROOT / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    for row in catalog["records"]:
        if row["category"] == "ai":
            count = restore(row["id"])
            row["bytes"] = (ROOT / f"{row['id']}.glb").stat().st_size
            print(f"{row['id']}: restored {count} mesh materials")
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")


if __name__ == "__main__":
    main()
