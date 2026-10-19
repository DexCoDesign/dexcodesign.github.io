#!/usr/bin/env python3
"""Assign one display material to each original Wuji visual mesh.

The source hand has separate visual meshes for the finger-root motor,
proximal shaft, middle assembly, and distal fingertip. The middle assembly
fuses its motor housing to the shaft in one STL, so split that display mesh
at the existing shoulder into two actual submeshes. Each submesh has exactly
one material; no vertex-color mask or source/training asset is changed.
"""

import copy
import json
import struct

from recolor_hand_studio_display import ROOT, chunks_of

MODEL = "wuji_hand_2"
VERSION = "motor-shoulder-submeshes-v7"
BLACK = {
    "name": "Wuji black motor housing and fingertip",
    "pbrMetallicRoughness": {
        "baseColorFactor": [.055, .060, .065, 1.0],
        "metallicFactor": .08,
        "roughnessFactor": .63,
    },
}


def accessor_values(document, binary, accessor_index):
    accessor = document["accessors"][accessor_index]
    view = document["bufferViews"][accessor["bufferView"]]
    width = {"SCALAR": 1, "VEC3": 3}[accessor["type"]]
    kind = {5125: "I", 5123: "H", 5126: "f"}[accessor["componentType"]]
    fmt = "<" + kind * width
    stride = view.get("byteStride", struct.calcsize(fmt))
    offset = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    return [struct.unpack_from(fmt, binary, offset + i * stride) for i in range(accessor["count"])]


def append_accessor(document, binary, values, width, target):
    binary.extend(b"\0" * (-len(binary) % 4))
    offset = len(binary)
    kind = "I" if width == 1 else "f"
    for value in values:
        binary.extend(struct.pack("<" + kind * width, *(value if width == 3 else (value,))))
    view = len(document["bufferViews"])
    document["bufferViews"].append({
        "buffer": 0, "byteOffset": offset, "byteLength": len(binary) - offset,
        "target": target,
    })
    accessor = len(document["accessors"])
    row = {"bufferView": view, "componentType": 5125 if width == 1 else 5126,
           "count": len(values), "type": "SCALAR" if width == 1 else "VEC3"}
    if width == 1:
        row.update(min=[min(values)], max=[max(values)])
    else:
        row.update(min=[min(p[i] for p in values) for i in range(3)],
                   max=[max(p[i] for p in values) for i in range(3)])
    document["accessors"].append(row)
    return accessor


def clip_polygon(vertices, shoulder, keep_lower):
    result = []
    for i, end in enumerate(vertices):
        start = vertices[i - 1]
        start_inside = start[0][2] <= shoulder if keep_lower else start[0][2] >= shoulder
        end_inside = end[0][2] <= shoulder if keep_lower else end[0][2] >= shoulder
        if start_inside != end_inside:
            t = (shoulder - start[0][2]) / (end[0][2] - start[0][2])
            point = tuple(start[0][k] + t * (end[0][k] - start[0][k]) for k in range(3))
            normal = tuple(start[1][k] + t * (end[1][k] - start[1][k]) for k in range(3))
            result.append((point, normal))
        if end_inside:
            result.append(end)
    return result


def split_middle(document, binary, primitive, shoulder, black_material):
    positions = accessor_values(document, binary, primitive["attributes"]["POSITION"])
    normals = accessor_values(document, binary, primitive["attributes"]["NORMAL"])
    indices = [row[0] for row in accessor_values(document, binary, primitive["indices"])]
    if len(indices) % 3:
        raise ValueError("Middle mesh is not triangular")
    result = []
    for lower, material in ((True, black_material), (False, primitive["material"])):
        out_position, out_normal = [], []
        for i in range(0, len(indices), 3):
            triangle = [(positions[j], normals[j]) for j in indices[i:i + 3]]
            polygon = clip_polygon(triangle, shoulder, lower)
            for j in range(1, len(polygon) - 1):
                for point, normal in (polygon[0], polygon[j], polygon[j + 1]):
                    out_position.append(point)
                    out_normal.append(normal)
        if not out_position:
            raise ValueError("Motor/shaft split produced an empty mesh")
        result.append({
            "attributes": {
                "POSITION": append_accessor(document, binary, out_position, 3, 34962),
                "NORMAL": append_accessor(document, binary, out_normal, 3, 34962),
            },
            "indices": append_accessor(document, binary, list(range(len(out_position))), 1, 34963),
            "mode": 4, "material": material,
        })
    return result


def main():
    path = ROOT / f"{MODEL}.glb"
    meta_path = ROOT / f"{MODEL}.json"
    metadata = json.loads(meta_path.read_text())
    if metadata.get("display_segments", {}).get("version") == VERSION:
        print("Wuji whole-mesh display colors already applied")
        return

    chunks = chunks_of(path.read_bytes())
    document = json.loads(chunks[0][1])
    original_binary = chunks[1][1]
    binary = bytearray(original_binary)
    black_material = len(document["materials"])
    document["materials"].append(copy.deepcopy(BLACK))
    parts = {}

    for node in document["nodes"]:
        name = node.get("name", "")
        if not name.startswith("visual__r_") or "mesh" not in node:
            continue
        link = name.removeprefix("visual__").rsplit("__", 1)[0]
        if link in ("r_base_link", "r_wrist"):
            continue
        mesh = document["meshes"][node["mesh"]]
        if len(mesh["primitives"]) != 1:
            raise ValueError(f"Expected one complete source visual mesh: {name}")
        primitive = mesh["primitives"][0]
        # Remove the earlier per-vertex gradient. Its now-orphaned buffer is
        # harmless; no source vertex/index/normal data is changed.
        primitive["attributes"].pop("COLOR_0", None)
        if link.endswith(("_proximal", "_distal")):
            primitive["material"] = black_material
            parts[link] = "black motor / fingertip"
        elif link.endswith("_middle"):
            # This STL contains both the joint motor and its long metal shaft.
            # The original geometry narrows at these measured shoulders.
            shoulder = .007 if "thumb" in link else .0095
            mesh["primitives"] = split_middle(document, binary, primitive, shoulder, black_material)
            parts[link] = "black motor submesh + silver shaft submesh"
        elif link.endswith("_proximal_abd"):
            parts[link] = "silver shaft"
        else:
            raise ValueError(f"Unexpected Wuji visual mesh: {link}")

    if len(parts) != 20 or sum(v.startswith("black motor / fingertip") for v in parts.values()) != 10:
        raise ValueError(f"Expected ten fully black finger meshes: {parts}")
    document["buffers"][0]["byteLength"] = len(binary)
    json_bytes = json.dumps(document, separators=(",", ":")).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    payloads = [(b"JSON", json_bytes), (b"BIN\0", bytes(binary))]
    serialized = [struct.pack("<I4s", len(data), kind) + data for kind, data in payloads]
    result = struct.pack("<4sII", b"glTF", 2, 12 + sum(map(len, serialized))) + b"".join(serialized)
    if bytes(binary[:len(original_binary)]) != original_binary:
        raise AssertionError("Original geometry buffer changed")

    metadata["bytes"] = len(result)
    metadata["display_segments"] = {"version": VERSION, "parts": parts}
    path.write_bytes(result)
    meta_path.write_text(json.dumps(metadata, separators=(",", ":")) + "\n")
    catalog_path = ROOT / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    next(row for row in catalog["records"] if row["id"] == MODEL)["bytes"] = len(result)
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Colored {len(parts)} Wuji visual meshes; middle motors and shafts are separate uniform-color submeshes")


if __name__ == "__main__":
    main()
