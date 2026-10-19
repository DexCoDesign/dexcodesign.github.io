#!/usr/bin/env python3
"""Split Wuji's wrist display mesh into silver palm and black finger-root collars.

The other black bands are complete distal and proximal motor meshes, plus the
already-separated middle motor submesh. Metal shafts stay silver. This edits
only the website GLB; source URDF, collision, and training assets stay intact.
"""

import json
import math
import struct

from paint_wuji_studio_display import accessor_values, append_accessor, clip_polygon
from recolor_hand_studio_display import ROOT, chunks_of

MODEL = "wuji_hand_2"
VERSION = "three-black-bands-with-root-collars-v4"
FINGERS = ("thumb", "index_finger", "middle_finger", "ring_finger", "pinky")
BLACK_FACTOR = [.055, .060, .065, 1.0]
SILVER_FACTOR = [.46, .49, .52, 1.0]
PALM_FACTOR = [.44, .47, .50, 1.0]
BASE_FACTOR = [.08, .09, .10, 1.0]
SOURCE_ACCESSORS = {
    "thumb_proximal_abd": (7, 8, 6), "thumb_middle": (10, 11, 9),
    "index_finger_proximal_abd": (19, 20, 18), "index_finger_middle": (22, 23, 21),
    "middle_finger_proximal_abd": (19, 20, 18), "middle_finger_middle": (22, 23, 21),
    "ring_finger_proximal_abd": (19, 20, 18), "ring_finger_middle": (22, 23, 21),
    "pinky_proximal_abd": (31, 32, 30), "pinky_middle": (34, 35, 33),
}


def material(document, factor):
    hits = [i for i, row in enumerate(document["materials"])
            if row.get("pbrMetallicRoughness", {}).get("baseColorFactor") == factor
            and not row.get("name", "").startswith("Wuji review only")]
    if not hits:
        raise ValueError(f"Original material missing: {factor}")
    return hits[0]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def quaternion_axes(quat):
    x, y, z, w = quat  # scipy/metadata xyzw order
    return (
        (1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y)),
        (2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x)),
        (2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)),
    )


def collar_planes(joint, finger):
    center = joint["position"]
    width = .011 if finger == "thumb" else .009
    # The root motor bottoms lie at local z ~= -7 mm. The visible metal
    # finger socket belongs to the wrist mesh and reaches above that plane.
    # Cut below the socket and color only the socket surface above the cut.
    lower, upper = -.007, .011
    planes = []
    for axis, extent in zip(quaternion_axes(joint["quaternion"]), (width, width, None)):
        offset = dot(axis, center)
        if extent is None:
            planes.extend(((axis, offset + upper), (tuple(-v for v in axis), -offset - lower)))
        else:
            planes.extend(((axis, offset + extent), (tuple(-v for v in axis), -offset + extent)))
    return planes


def halfspace(polygon, plane, inside):
    normal, limit = plane
    result = []
    for i, end in enumerate(polygon):
        start = polygon[i - 1]
        ds = dot(normal, start[0]) - limit
        de = dot(normal, end[0]) - limit
        start_ok = ds <= 0 if inside else ds >= 0
        end_ok = de <= 0 if inside else de >= 0
        if start_ok != end_ok and abs(ds - de) > 1e-12:
            t = ds / (ds - de)
            point = tuple(start[0][k] + t * (end[0][k] - start[0][k]) for k in range(3))
            n = tuple(start[1][k] + t * (end[1][k] - start[1][k]) for k in range(3))
            size = math.sqrt(dot(n, n)) or 1
            result.append((point, tuple(v / size for v in n)))
        if end_ok:
            result.append(end)
    return result


def triangles(polygons):
    points, normals = [], []
    for polygon in polygons:
        for i in range(1, len(polygon)-1):
            for point, normal in (polygon[0], polygon[i], polygon[i+1]):
                points.append(point)
                normals.append(normal)
    return points, normals


def segment_primitive(document, binary, polygons, material_index):
    points, normals = triangles(polygons)
    if not points:
        raise ValueError("Axial split produced an empty material region")
    return {
        "attributes": {
            "POSITION": append_accessor(document, binary, points, 3, 34962),
            "NORMAL": append_accessor(document, binary, normals, 3, 34962),
        },
        "indices": append_accessor(document, binary, list(range(len(points))), 1, 34963),
        "mode": 4,
        "material": material_index,
    }


def split_finger_shaft(document, binary, link, joints, silver, black):
    key = link.removeprefix("r_")
    position, normal, index = SOURCE_ACCESSORS[key]
    vertices = accessor_values(document, binary, position)
    normals = accessor_values(document, binary, normal)
    indices = [row[0] for row in accessor_values(document, binary, index)]
    if len(indices) % 3:
        raise ValueError(f"Unexpected finger mesh indices: {link}")
    finger = next(value for value in FINGERS if key.startswith(value + "_"))
    primitive_polygons = [[(vertices[j], normals[j]) for j in indices[i:i+3]]
                          for i in range(0, len(indices), 3)]
    if link.endswith("_proximal_abd"):
        joint = "r_thumb_mcp" if finger == "thumb" else f"r_{finger}_pip"
        upper_motor_start = joints[joint]["position"][2] - .006
        metal, motor = [], []
        for polygon in primitive_polygons:
            metal.append(clip_polygon(polygon, upper_motor_start, True))
            motor.append(clip_polygon(polygon, upper_motor_start, False))
        return [segment_primitive(document, binary, [p for p in metal if len(p) >= 3], silver),
                segment_primitive(document, binary, [p for p in motor if len(p) >= 3], black)]
    joint = "r_thumb_ip" if finger == "thumb" else f"r_{finger}_dip"
    lower_motor_end = .007 if finger == "thumb" else .0095
    tip_motor_start = joints[joint]["position"][2] - .006
    lower, middle, upper = [], [], []
    for polygon in primitive_polygons:
        low = clip_polygon(polygon, lower_motor_end, True)
        rest = clip_polygon(polygon, lower_motor_end, False)
        if len(low) >= 3:
            lower.append(low)
        if len(rest) >= 3:
            mid = clip_polygon(rest, tip_motor_start, True)
            high = clip_polygon(rest, tip_motor_start, False)
            if len(mid) >= 3:
                middle.append(mid)
            if len(high) >= 3:
                upper.append(high)
    return [segment_primitive(document, binary, lower, black),
            segment_primitive(document, binary, middle, silver),
            segment_primitive(document, binary, upper, black)]


def split_wrist(document, binary, primitives, joints, silver, black):
    silver_polygons = []
    for primitive in primitives:
        positions = accessor_values(document, binary, primitive["attributes"]["POSITION"])
        normals = accessor_values(document, binary, primitive["attributes"]["NORMAL"])
        indices = [row[0] for row in accessor_values(document, binary, primitive["indices"])]
        if len(indices) % 3:
            raise ValueError("Wrist geometry must be triangular")
        silver_polygons.extend([[(positions[j], normals[j]) for j in indices[i:i+3]]
                                for i in range(0, len(indices), 3)])
    black_polygons = []
    counts = {}
    for finger in FINGERS:
        joint_name = "r_thumb_cmc_flex" if finger == "thumb" else f"r_{finger}_mcp_flex"
        planes = collar_planes(joints[joint_name], finger)
        remaining = []
        selected = []
        for polygon in silver_polygons:
            candidate = polygon
            for plane in planes:
                outside = halfspace(candidate, plane, False)
                if len(outside) >= 3:
                    remaining.append(outside)
                candidate = halfspace(candidate, plane, True)
                if len(candidate) < 3:
                    break
            if len(candidate) >= 3:
                selected.append(candidate)
        if not selected:
            raise ValueError(f"No wrist surface below the {finger} root motor")
        black_polygons.extend(selected)
        silver_polygons = remaining
        counts[finger] = len(selected)
    result = []
    for polygons, material_index in ((silver_polygons, silver), (black_polygons, black)):
        points, out_normals = triangles(polygons)
        if not points:
            raise ValueError("Wrist split produced an empty color region")
        result.append({
            "attributes": {
                "POSITION": append_accessor(document, binary, points, 3, 34962),
                "NORMAL": append_accessor(document, binary, out_normals, 3, 34962),
            },
            "indices": append_accessor(document, binary, list(range(len(points))), 1, 34963),
            "mode": 4,
            "material": material_index,
        })
    return result, counts


def main():
    path = ROOT / f"{MODEL}.glb"
    meta_path = ROOT / f"{MODEL}.json"
    metadata = json.loads(meta_path.read_text())
    if metadata.get("display_segments", {}).get("version") == VERSION:
        print("Wuji three-band display colors already applied")
        return
    if metadata.get("display_segments", {}).get("version") not in (
            "five-full-fingers-black-v1", "three-black-bands-with-root-collars-v1",
            "three-black-bands-with-root-collars-v2", "three-black-bands-with-root-collars-v3"):
        raise ValueError("Expected the current Wuji finger preview")
    chunks = chunks_of(path.read_bytes())
    document = json.loads(chunks[0][1])
    old_binary = chunks[1][1]
    binary = bytearray(old_binary)
    black = material(document, BLACK_FACTOR)
    silver = material(document, SILVER_FACTOR)
    palm = material(document, PALM_FACTOR)
    base = material(document, BASE_FACTOR)
    joints = {joint["name"]: joint for joint in metadata["joints"]}
    seen = set()
    collars = None
    for node in document["nodes"]:
        name = node.get("name", "")
        if not name.startswith("visual__r_") or "mesh" not in node:
            continue
        link = name.removeprefix("visual__").rsplit("__", 1)[0]
        mesh = document["meshes"][node["mesh"]]
        parts = mesh["primitives"]
        if link == "r_base_link":
            parts[0]["material"] = base
        elif link == "r_wrist":
            if len(parts) not in (1, 2):
                raise ValueError("Unexpected palm mesh segmentation")
            # The original palm accessors are still intact in the GLB binary.
            # Start from them so repeated display revisions do not compound
            # old triangle cuts or alter the surface.
            source = metadata.get("display_segments", {}).get("wrist_source_primitive")
            if source is None:
                source = {"attributes": {"POSITION": 40, "NORMAL": 41}, "indices": 39}
            if document["accessors"][source["indices"]]["count"] != 19392:
                raise ValueError("Original wrist geometry accessor changed")
            mesh["primitives"], collars = split_wrist(document, binary, [source], joints, palm, black)
        else:
            finger = next((value for value in FINGERS if link.startswith(f"r_{value}_")), None)
            if finger is None:
                raise ValueError(f"Unexpected finger mesh: {link}")
            seen.add(link)
            if link.endswith(("_proximal_abd", "_middle")):
                mesh["primitives"] = split_finger_shaft(document, binary, link, joints, silver, black)
            else:
                for part in parts:
                    part["attributes"].pop("COLOR_0", None)
                    part["material"] = black
    if len(seen) != 20 or collars is None or len(collars) != 5:
        raise ValueError("Incomplete five-finger segmentation")
    document["buffers"][0]["byteLength"] = len(binary)
    json_bytes = json.dumps(document, separators=(",", ":")).encode()
    json_bytes += b" " * (-len(json_bytes) % 4)
    payloads = [(b"JSON", json_bytes), (b"BIN\0", bytes(binary))]
    serialized = [struct.pack("<I4s", len(data), kind) + data for kind, data in payloads]
    result = struct.pack("<4sII", b"glTF", 2, 12 + sum(map(len, serialized))) + b"".join(serialized)
    if bytes(binary[:len(old_binary)]) != old_binary:
        raise AssertionError("Original geometry buffer was modified")
    metadata["bytes"] = len(result)
    metadata["display_segments"] = {
        "version": VERSION,
        "description": "Three full black bands: fingertip, middle joint, finger root/socket; shaft centers and main palm silver",
        "wrist_collar_polygon_counts": collars,
        "wrist_source_primitive": source,
    }
    metadata.pop("review_palette", None)
    path.write_bytes(result)
    meta_path.write_text(json.dumps(metadata, separators=(",", ":")) + "\n")
    catalog_path = ROOT / "catalog.json"
    catalog = json.loads(catalog_path.read_text())
    next(row for row in catalog["records"] if row["id"] == MODEL)["bytes"] = len(result)
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n")
    print(f"Wuji three black bands applied; palm collar polygons: {collars}")


if __name__ == "__main__":
    main()
