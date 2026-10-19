#!/usr/bin/env python3
"""Recolor published Studio GLBs without touching their binary geometry.

The published source snapshot is unavailable for some robot hands, so this
updates only GLB JSON materials and matching display-color metadata.
"""

import copy
import json
import struct
from pathlib import Path

from studio_display_palette import PHOTO_REFERENCES, display_rgba, display_surface

ROOT = Path(__file__).resolve().parents[1] / "assets/models/studio"


def chunks_of(raw):
    magic, version, total = struct.unpack_from("<4sII", raw)
    if (magic, version, total) != (b"glTF", 2, len(raw)):
        raise ValueError("Unexpected GLB header")
    chunks = []
    offset = 12
    while offset < len(raw):
        length, kind = struct.unpack_from("<I4s", raw, offset)
        offset += 8
        chunks.append((kind, raw[offset:offset + length]))
        offset += length
    if offset != len(raw) or [kind for kind, _ in chunks] != [b"JSON", b"BIN\x00"]:
        raise ValueError("Unexpected GLB chunks")
    return chunks


def recolor(model_id):
    path = ROOT / f"{model_id}.glb"
    meta_path = ROOT / f"{model_id}.json"
    source_chunks = chunks_of(path.read_bytes())
    document = json.loads(source_chunks[0][1])
    metadata = json.loads(meta_path.read_text())
    if metadata["id"] != model_id:
        raise ValueError(f"Metadata mismatch: {model_id}")
    if model_id == "wuji_hand_2" and metadata.get("display_segments"):
        # This model has narrow per-triangle black joint/tip regions. A
        # link-wide recolor would erase them; rebuild via the segment painter
        # if its base palette changes in the future.
        return len(path.read_bytes()), 0
    # Several source visuals may have been exported as separate meshes and
    # later given the same display color. Keep targeting every exported mesh,
    # even after the metadata colors have already collapsed to one group.
    uniform_targets = {}
    nonuniform_links = set()
    for row in metadata["materials"]:
        source_color = row.get("source_rgba") or row["rgba"]
        selected = display_rgba(model_id, row["link"], row["visual"], source_color)
        if selected is None:
            continue
        target = (selected[0], *display_surface(model_id, row["link"]))
        link = row["link"]
        if link in uniform_targets and uniform_targets[link] != target:
            nonuniform_links.add(link)
        else:
            uniform_targets[link] = target
    for link in nonuniform_links:
        del uniform_targets[link]
    pending = False
    for row in metadata["materials"]:
        selected = display_rgba(model_id, row["link"], row["visual"], row.get("source_rgba") or row["rgba"])
        metalness, roughness = display_surface(model_id, row["link"])
        if selected is not None and (
            row["rgba"] != selected[0]
            or row["origin"] != selected[1]
            or row.get("display_metalness") != metalness
            or row.get("display_roughness") != roughness
        ):
            pending = True
            break
    if not pending:
        for node in document["nodes"]:
            name = node.get("name", "")
            if not name.startswith("visual__") or "mesh" not in node:
                continue
            link = name.removeprefix("visual__").rsplit("__", 1)[0]
            target = uniform_targets.get(link)
            if target is None:
                continue
            rgba, metalness, roughness = target
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                pbr = document["materials"][primitive["material"]]["pbrMetallicRoughness"]
                if (pbr.get("baseColorFactor") != rgba
                    or pbr.get("metallicFactor") != metalness
                    or pbr.get("roughnessFactor") != roughness):
                    pending = True
                    break
            if pending:
                break
    if not pending:
        return len(path.read_bytes()), 0
    groups = {}
    for row in metadata["materials"]:
        key = row["link"]
        old_color = tuple(round(float(x), 6) for x in row["rgba"])
        unique = groups.setdefault(key, {})
        if old_color not in unique:
            unique[old_color] = len(unique)
        source_color = row.get("source_rgba") or row["rgba"]
        selected = display_rgba(model_id, key, row["visual"], source_color)
        if selected is None:
            continue
        new_color, provenance = selected
        metalness, roughness = display_surface(model_id, key)
        row["rgba"] = new_color
        row["origin"] = provenance
        row["display_metalness"] = metalness
        row["display_roughness"] = roughness
        row["display_reference"] = PHOTO_REFERENCES.get(model_id, "authored-concept-palette")
        mapping = groups.setdefault("__targets__", {})
        target_key = (key, unique[old_color])
        target = (new_color, metalness, roughness)
        if target_key in mapping and mapping[target_key] != target:
            raise ValueError(f"One merged mesh has conflicting colors: {model_id}/{key}")
        mapping[target_key] = target

    target_by_node = {
        f"visual__{link}__{index}": target
        for (link, index), target in groups.get("__targets__", {}).items()
    }
    for node in document["nodes"]:
        name = node.get("name", "")
        if name.startswith("visual__"):
            link = name.removeprefix("visual__").rsplit("__", 1)[0]
            if link in uniform_targets:
                target_by_node[name] = uniform_targets[link]
    used_meshes = set()
    originals = document["materials"][:]
    material_cache = {}
    changed_nodes = 0
    for node in document["nodes"]:
        target = target_by_node.get(node.get("name"))
        if target is None:
            continue
        rgba, metalness, roughness = target
        mesh_index = node.get("mesh")
        if mesh_index is None or mesh_index in used_meshes:
            raise ValueError(f"Unexpected shared/missing mesh: {model_id}/{node.get('name')}")
        used_meshes.add(mesh_index)
        for primitive in document["meshes"][mesh_index]["primitives"]:
            original_index = primitive["material"]
            key = (original_index, tuple(rgba), metalness, roughness)
            if key not in material_cache:
                material = copy.deepcopy(originals[original_index])
                material["pbrMetallicRoughness"]["baseColorFactor"] = rgba
                material["pbrMetallicRoughness"]["metallicFactor"] = metalness
                material["pbrMetallicRoughness"]["roughnessFactor"] = roughness
                material_cache[key] = len(document["materials"])
                document["materials"].append(material)
            primitive["material"] = material_cache[key]
        changed_nodes += 1
    if changed_nodes != len(target_by_node):
        raise ValueError(f"Missing visual nodes: {model_id}: {changed_nodes}/{len(target_by_node)}")

    # Discard superseded material entries so repeated palette revisions do
    # not accumulate unused JSON. Vertex/index buffers stay byte-for-byte.
    referenced = sorted({primitive["material"] for mesh in document["meshes"] for primitive in mesh["primitives"]})
    compact = {old: new for new, old in enumerate(referenced)}
    document["materials"] = [document["materials"][index] for index in referenced]
    for mesh in document["meshes"]:
        for primitive in mesh["primitives"]:
            primitive["material"] = compact[primitive["material"]]

    json_bytes = json.dumps(document, separators=(",", ":")).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    payloads = [(b"JSON", json_bytes), source_chunks[1]]
    serialized = [struct.pack("<I4s", len(body), kind) + body for kind, body in payloads]
    result = struct.pack("<4sII", b"glTF", 2, 12 + sum(map(len, serialized))) + b"".join(serialized)
    if chunks_of(result)[1] != source_chunks[1]:
        raise AssertionError("GLB binary geometry changed")
    metadata["bytes"] = len(result)
    path.write_bytes(result)
    meta_path.write_text(json.dumps(metadata, separators=(",", ":")) + "\n")
    return len(result), changed_nodes


def main():
    catalog_path = ROOT / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    count = 0
    for record in catalog["records"]:
        model_id = record["id"]
        if model_id == "robotera_xhand1_pro":
            continue  # approved reference appearance
        if model_id not in PHOTO_REFERENCES:
            continue
        size, nodes = recolor(model_id)
        record["bytes"] = size
        count += 1
        print(f"{model_id}: {nodes} display mesh colors, {size} bytes")
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Updated {count} Studio models; all BIN geometry chunks preserved")


if __name__ == "__main__":
    main()
