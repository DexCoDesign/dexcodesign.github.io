#!/usr/bin/env python3
"""Generate the six-actuator TALON-6 display concept from closed CAD-style lofts.

The source URDF and OBJ meshes are published alongside the site preview. This is
a kinematic concept, not a contact/force-closure or fabrication validation.
"""
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import trimesh


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/models/studio/sources/talon6"
MESHES = OUT / "meshes"
PALETTE = {
    "olive": (.40, .51, .43, 1.0),
    "sage": (.72, .77, .66, 1.0),
    "alloy": (.50, .54, .57, 1.0),
    "graphite": (.13, .15, .17, 1.0),
    "gold": (.78, .56, .24, 1.0),
}


def loft(sections, sides=24, squareness=3.1):
    """Closed, rounded-rectangle rings: (z, x-center, y-center, x-radius, y-radius)."""
    vertices = []
    for z, cx, cy, rx, ry in sections:
        for i in range(sides):
            a = 2 * math.pi * i / sides
            c, s = math.cos(a), math.sin(a)
            vertices.append((cx + rx * math.copysign(abs(c) ** (2 / squareness), c),
                             cy + ry * math.copysign(abs(s) ** (2 / squareness), s), z))
    faces = []
    for ring in range(len(sections) - 1):
        for i in range(sides):
            a, b = ring * sides + i, ring * sides + (i + 1) % sides
            c, d = a + sides, b + sides
            faces.extend(((a, b, d), (a, d, c)))
    vertices.extend((tuple(np.mean(vertices[:sides], axis=0)),
                     tuple(np.mean(vertices[-sides:], axis=0))))
    bottom, top = len(vertices) - 2, len(vertices) - 1
    for i in range(sides):
        faces.append((bottom, (i + 1) % sides, i))
        faces.append((top, (len(sections) - 1) * sides + i,
                      (len(sections) - 1) * sides + (i + 1) % sides))
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    assert mesh.is_watertight and mesh.is_winding_consistent
    return mesh


def front_plate(points, back, front):
    """Extruded convex x/z outline, for a fitted palm panel rather than a box."""
    n = len(points)
    vertices = [(x, back, z) for x, z in points] + [(x, front, z) for x, z in points]
    faces = []
    for i in range(1, n - 1):
        faces += [(0, i + 1, i), (n, n + i, n + i + 1)]
    for i in range(n):
        j = (i + 1) % n
        faces += [(i, j, n + j), (i, n + j, n + i)]
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
    # The x/z outline is counter-clockwise when seen from -Y. Invert the
    # extrusion so the display-facing +Y side has outward normals.
    mesh.invert()
    assert mesh.is_watertight
    return mesh


def visual(link, filename, color, xyz=None, rpy=None):
    v = ET.SubElement(link, "visual")
    if xyz is not None or rpy is not None:
        ET.SubElement(v, "origin", xyz=" ".join(map(str, xyz or (0, 0, 0))),
                      rpy=" ".join(map(str, rpy or (0, 0, 0))))
    m = ET.SubElement(v, "material", name=color)
    ET.SubElement(m, "color", rgba=" ".join(map(str, PALETTE[color])))
    ET.SubElement(ET.SubElement(v, "geometry"), "mesh", filename=f"meshes/{filename}.obj")


def save_meshes():
    MESHES.mkdir(parents=True, exist_ok=True)
    shapes = {
        "palm_shell": loft([(-.014, 0, 0, .037, .016), (-.005, 0, 0, .048, .019),
                             (.017, 0, 0, .062, .021), (.038, 0, 0, .063, .020),
                             (.054, 0, -.001, .059, .017)]),
        "palm_face": front_plate([(-.043, -.004), (.043, -.004), (.052, .014),
                                   (.050, .035), (.039, .044), (-.039, .044),
                                   (-.050, .035), (-.052, .014)], .019, .022),
        "wrist_collar": loft([(-.020, 0, 0, .030, .019), (-.013, 0, 0, .037, .019),
                               (-.004, 0, 0, .041, .018)]),
        "thumb_bridge": loft([(0, 0, 0, .010, .013), (.010, 0, 0, .011, .014),
                                 (.025, 0, 0, .009, .012)]),
        "motor_cover": loft([(-.013, 0, 0, .0090, .012), (-.009, 0, 0, .0100, .013),
                               (.008, 0, 0, .0100, .013), (.013, 0, 0, .0088, .011)]),
        "motor_cap": loft([(.006, 0, .011, .0068, .0018),
                             (.009, 0, .011, .0068, .0018)]),
        "finger": loft([(0, 0, 0, .0088, .0090), (.008, 0, 0, .0092, .0093),
                          (.025, 0, 0, .0082, .0088), (.043, 0, .001, .0074, .0078),
                          (.061, 0, .003, .0065, .0067), (.070, 0, .004, .0058, .0060),
                          (.074, 0, .004, .0037, .0040)]),
        "finger_pad": front_plate([(-.0058, .051), (.0058, .051), (.0050, .068),
                                    (.0036, .073), (-.0036, .073), (-.0050, .068)],
                                   .0086, .0097),
        "finger_spine": front_plate([(-.0030, .012), (.0030, .012), (.0030, .046),
                                      (-.0030, .046)], -.0100, -.0087),
        "thumb": loft([(0, 0, 0, .0095, .0100), (.009, 0, 0, .0100, .0103),
                         (.028, 0, .001, .0086, .0090), (.048, 0, .002, .0074, .0078),
                         (.065, 0, .003, .0063, .0065), (.073, 0, .003, .0042, .0044)]),
        "thumb_pad": front_plate([(-.0054, .053), (.0054, .053), (.0040, .069),
                                   (-.0040, .069)], .0087, .0098),
        "thumb_spine": front_plate([(-.0031, .011), (.0031, .011),
                                     (.0025, .046), (-.0025, .046)], -.0109, -.0095),
        "palm_inlay": front_plate([(-.032, .000), (.032, .000), (.040, .013),
                                   (.035, .024), (-.035, .024), (-.040, .013)], .0222, .0229),
    }
    # This is a thumb, not a fifth full-length finger. Keep its closed shell
    # and inlay, but shorten the distal reach relative to the four fingers.
    for name in ("thumb", "thumb_pad", "thumb_spine"):
        shapes[name].apply_scale((1, 1, .82))
    for name, mesh in shapes.items():
        (MESHES / f"{name}.obj").write_text(mesh.export(file_type="obj").rstrip() + "\n")


def build_urdf():
    root = ET.Element("robot", name="TALON-6-right-hand")
    palm = ET.SubElement(root, "link", name="palm")
    for mesh, color in (("palm_shell", "olive"), ("palm_face", "sage"),
                        ("wrist_collar", "graphite"), ("palm_inlay", "alloy")):
        visual(palm, mesh, color)
    # Only the radial side carries a thumb. The bridge reaches the palm shell,
    # avoiding the unsupported forward stalk of the older TALON concepts.
    visual(palm, "thumb_bridge", "olive", (.050, .015, .052),
           (0, math.pi/2, 0))
    # Four finger drives; the right thumb gets two orthogonal drives at its
    # base (opposition and flexion), for six active joints in five digits.
    digits = [
        ("index", .039, 0, .049, 0),
        ("middle", .013, 0, .049, 0),
        ("ring", -.013, 0, .049, 0),
        ("little", -.039, 0, .049, 0),
    ]
    for name, x, y, z, yaw in digits:
        visual(palm, "motor_cover", "alloy", (x, y, z))
        visual(palm, "motor_cap", "gold", (x, y, z))
        link = ET.SubElement(root, "link", name=f"{name}_digit")
        visual(link, "finger", "sage")
        # The contact face is part of the colored shell, not a black sticker
        # (TALON's earlier design explicitly removed those grip patches).
        visual(link, "finger_pad", "olive")
        visual(link, "finger_spine", "gold")
        joint = ET.SubElement(root, "joint", name=f"{name}_flex", type="revolute")
        ET.SubElement(joint, "parent", link="palm")
        ET.SubElement(joint, "child", link=f"{name}_digit")
        ET.SubElement(joint, "origin", xyz=f"{x} {y} {z}",
                      rpy=f"0 0 {math.radians(yaw)}")
        ET.SubElement(joint, "axis", xyz="-1 0 0")
        ET.SubElement(joint, "limit", lower="0", upper=str(math.radians(85)),
                      effort="1.5", velocity="2.0")

    # The opposition motor is housed in the side bridge. Its rotating hub
    # encloses the perpendicular flexion drive; there is no distal motor.
    visual(palm, "motor_cover", "alloy", (.066, .017, .057),
           (math.pi/2, 0, 0))
    thumb_hub = ET.SubElement(root, "link", name="thumb_hub")
    visual(thumb_hub, "motor_cover", "olive", (0, 0, 0),
           (math.pi/2, 0, 0))
    visual(thumb_hub, "motor_cap", "gold", (0, 0, 0),
           (math.pi/2, 0, 0))
    opposition = ET.SubElement(root, "joint", name="thumb_opposition", type="revolute")
    ET.SubElement(opposition, "parent", link="palm")
    ET.SubElement(opposition, "child", link="thumb_hub")
    ET.SubElement(opposition, "origin", xyz="0.075 0.027 0.065",
                  rpy=f"0 0 {math.radians(70)}")
    ET.SubElement(opposition, "axis", xyz="0 0 1")
    ET.SubElement(opposition, "limit", lower=str(math.radians(-20)),
                  upper=str(math.radians(35)), effort="1.5", velocity="2.0")
    thumb = ET.SubElement(root, "link", name="thumb_digit")
    visual(thumb, "thumb", "olive")
    visual(thumb, "thumb_pad", "sage")
    visual(thumb, "thumb_spine", "gold")
    flex = ET.SubElement(root, "joint", name="thumb_flex", type="revolute")
    ET.SubElement(flex, "parent", link="thumb_hub")
    ET.SubElement(flex, "child", link="thumb_digit")
    # A small outward rest cant makes the neutral silhouette unmistakably
    # thumb-like; flexion sweeps it back toward the index finger.
    ET.SubElement(flex, "origin", xyz="0 0 0", rpy=f"{math.radians(15)} 0 0")
    ET.SubElement(flex, "axis", xyz="-1 0 0")
    ET.SubElement(flex, "limit", lower="0", upper=str(math.radians(85)),
                  effort="1.5", velocity="2.0")
    ET.indent(root, space="  ")
    (OUT / "hand.urdf").write_text(ET.tostring(root, encoding="unicode") + "\n")
    names = [f"{name}_flex" for name, *_ in digits]
    def pose(fingers, opposition, thumb_flexion):
        return {n: fingers for n in names} | {
            "thumb_opposition": opposition, "thumb_flex": thumb_flexion}
    poses = {
        "neutral": pose(8, 0, 8),
        "spread": pose(0, -15, 0),
        "wrap": pose(66, 20, 66),
        "pinch": {n: (15 if n == "index_flex" else 8) for n in names} | {
            "thumb_opposition": 20, "thumb_flex": 40},
    }
    spec = {
        "controls": ([{"name": f"{name}_flex", "label": "Base flex",
                      "group": name.title()} for name, *_ in digits] +
                     [{"name": "thumb_opposition", "label": "Opposition", "group": "Thumb"},
                      {"name": "thumb_flex", "label": "Flex", "group": "Thumb"}]),
        "passive": [], "actuator_couplings": [], "poses": poses,
        "pinch_note": "The right thumb and index fingertip converge in the six-axis preview; grasp forces and force closure are not validated.",
        "concept_note": "Asymmetric right-hand gripper concept · five digits, six direct-drive axes (four fingers × 1 + thumb × 2) · enclosed motors · no passive joints.",
    }
    (OUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")


def validate_pinch():
    """Check the right thumb/index pair approaches without tip overlap."""
    def finger(angle):
        a = math.radians(angle)
        return np.array((.039, .004*math.cos(a)+.074*math.sin(a),
                         .049+.074*math.cos(a)-.004*math.sin(a)))
    def thumb(opposition, angle):
        a = math.radians(angle - 15)
        yaw = math.radians(70 + opposition)
        y = .003*math.cos(a)+.073*.82*math.sin(a)
        return np.array((.075-math.sin(yaw)*y, .027+math.cos(yaw)*y,
                         .065+.073*.82*math.cos(a)-.003*math.sin(a)))
    closed = np.linalg.norm(finger(15)-thumb(20, 40))
    open_ = np.linalg.norm(finger(8)-thumb(0, 8))
    assert .008 < closed < .012 and open_ > .020, (closed, open_)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save_meshes()
    build_urdf()
    validate_pinch()
    print(OUT)
