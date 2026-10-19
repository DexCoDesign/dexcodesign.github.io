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
    for name, mesh in shapes.items():
        (MESHES / f"{name}.obj").write_text(mesh.export(file_type="obj").rstrip() + "\n")


def build_urdf():
    root = ET.Element("robot", name="TALON-6-dual-opposition")
    palm = ET.SubElement(root, "link", name="palm")
    for mesh, color in (("palm_shell", "olive"), ("palm_face", "sage"),
                        ("wrist_collar", "graphite"), ("palm_inlay", "alloy")):
        visual(palm, mesh, color)
    for side in (-1, 1):
        # Short closed side spars carry the two opposing drives; neither
        # thumb hangs from an unsupported stalk ahead of the palm.
        visual(palm, "thumb_bridge", "olive", (side*.050, .015, .052),
               (0, side*math.pi/2, 0))
    # Six compact rotary actuators sit inside these flush shrouds; none needs
    # an exposed fingertip motor or an extra passive finger joint.
    digits = [
        ("index", .039, 0, .049, 0),
        ("middle", .013, 0, .049, 0),
        ("ring", -.013, 0, .049, 0),
        ("little", -.039, 0, .049, 0),
        ("radial_thumb", .075, .027, .065, 90),
        ("ulnar_thumb", -.075, .027, .065, -90),
    ]
    for name, x, y, z, yaw in digits:
        thumb = "thumb" in name
        # Thumb motors lie within the side spars, rather than protruding
        # beyond a distal fingertip.
        motor_rpy = (math.pi/2, 0, 0) if thumb else None
        visual(palm, "motor_cover", "alloy", (x, y, z), motor_rpy)
        visual(palm, "motor_cap", "gold", (x, y, z), motor_rpy)
        link = ET.SubElement(root, "link", name=f"{name}_digit")
        visual(link, "thumb" if thumb else "finger", "olive" if thumb else "sage")
        # The contact face is part of the colored shell, not a black sticker
        # (TALON's earlier design explicitly removed those grip patches).
        visual(link, "thumb_pad" if thumb else "finger_pad", "sage" if thumb else "olive")
        visual(link, "thumb_spine" if thumb else "finger_spine", "gold")
        joint = ET.SubElement(root, "joint", name=f"{name}_flex", type="revolute")
        ET.SubElement(joint, "parent", link="palm")
        ET.SubElement(joint, "child", link=f"{name}_digit")
        ET.SubElement(joint, "origin", xyz=f"{x} {y} {z}",
                      rpy=f"0 0 {math.radians(yaw)}")
        ET.SubElement(joint, "axis", xyz="-1 0 0")
        ET.SubElement(joint, "limit", lower="0", upper=str(math.radians(85)),
                      effort="1.5", velocity="2.0")
    ET.indent(root, space="  ")
    (OUT / "hand.urdf").write_text(ET.tostring(root, encoding="unicode") + "\n")
    names = [f"{name}_flex" for name, *_ in digits]
    def pose(main, thumbs):
        return {n: (thumbs if "thumb" in n else main) for n in names}
    poses = {
        "neutral": pose(8, 8),
        "spread": pose(0, 0),
        "wrap": pose(66, 66),
        "pinch": {n: (15 if n in ("index_flex", "little_flex") else
                       30 if "thumb" in n else 8)
                  for n in names},
    }
    spec = {
        "controls": [{"name": f"{name}_flex", "label": "Base flex",
                      "group": name.replace("_", " ").title()} for name, *_ in digits],
        "passive": [], "actuator_couplings": [], "poses": poses,
        "pinch_note": "Two opposed fingertip pairs converge in the six-axis preview; grasp forces and force closure are not validated.",
        "concept_note": "Six-digit gripper concept · six direct-drive base axes · enclosed motors · no passive joints.",
    }
    (OUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")


def validate_pinch():
    """Check both independent opposing pairs approach without tip overlap."""
    def finger(side, angle):
        a = math.radians(angle)
        return np.array((side*.039, .004*math.cos(a)+.074*math.sin(a),
                         .049+.074*math.cos(a)-.004*math.sin(a)))
    def thumb(side, angle):
        a = math.radians(angle)
        return np.array((side*(.075-.003*math.cos(a)-.073*math.sin(a)), .027,
                         .065+.073*math.cos(a)-.003*math.sin(a)))
    for side in (-1, 1):
        closed = np.linalg.norm(finger(side, 15)-thumb(side, 30))
        open_ = np.linalg.norm(finger(side, 8)-thumb(side, 8))
        assert .008 < closed < .012 and open_ > .020, (side, closed, open_)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save_meshes()
    build_urdf()
    validate_pinch()
    print(OUT)
