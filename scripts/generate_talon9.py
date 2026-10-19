#!/usr/bin/env python3
"""Generate the nine-actuator TALON-9 display concept from closed CAD-style lofts.

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
OUT = ROOT / "assets/models/studio/sources/talon9"
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


def visual(link, filename, color, xyz=None, rpy=None, scale=None):
    v = ET.SubElement(link, "visual")
    if xyz is not None or rpy is not None:
        ET.SubElement(v, "origin", xyz=" ".join(map(str, xyz or (0, 0, 0))),
                      rpy=" ".join(map(str, rpy or (0, 0, 0))))
    m = ET.SubElement(v, "material", name=color)
    ET.SubElement(m, "color", rgba=" ".join(map(str, PALETTE[color])))
    attrs = {"filename": f"meshes/{filename}.obj"}
    if scale is not None:
        attrs["scale"] = " ".join(map(str, scale))
    ET.SubElement(ET.SubElement(v, "geometry"), "mesh", **attrs)


def save_meshes():
    MESHES.mkdir(parents=True, exist_ok=True)
    shapes = {
        # The right edge is recessed around the thumb bearing and support,
        # then widens again at the finger roots. The left wall stays intact.
        "palm_shell": loft([(-.014, 0, 0, .037, .016), (-.005, 0, 0, .048, .019),
                             (.005, -.004, 0, .058, .020), (.017, -.010, 0, .055, .021),
                             (.038, -.010, 0, .055, .020), (.054, 0, -.001, .059, .017)]),
        "palm_face": front_plate([(-.043, -.004), (.043, -.004), (.034, .014),
                                   (.030, .035), (.039, .044), (-.039, .044),
                                   (-.050, .035), (-.052, .014)], .019, .022),
        "wrist_collar": loft([(-.020, 0, 0, .030, .019), (-.013, 0, 0, .037, .019),
                               (-.004, 0, 0, .041, .018)]),
        "thumb_socket": loft([(-.010, 0, 0, .011, .011), (-.004, 0, 0, .013, .013),
                                 (.007, 0, 0, .013, .013), (.011, 0, 0, .011, .011)]),
        "thumb_rotor": loft([(-.004, 0, 0, .009, .009), (.006, 0, 0, .011, .011),
                                (.014, 0, 0, .009, .009)]),
        "thumb_support": loft([(0, 0, 0, .008, .008), (.009, 0, 0, .010, .010),
                                  (.023, 0, 0, .009, .009), (.031, 0, 0, .0075, .0075)]),
        "thumb_bearing_housing": loft([(-.014, 0, 0, .014, .011),
                                         (-.004, 0, 0, .016, .012),
                                         (.014, 0, 0, .016, .012),
                                         (.020, 0, 0, .013, .010)]),
        "motor_cover": loft([(-.013, 0, 0, .0090, .012), (-.009, 0, 0, .0100, .013),
                               (.008, 0, 0, .0100, .013), (.013, 0, 0, .0088, .011)]),
        "motor_cap": loft([(.006, 0, .011, .0068, .0018),
                             (.009, 0, .011, .0068, .0018)]),
        "proximal_shell": loft([(0, 0, 0, .0094, .0096), (.008, 0, 0, .0098, .0098),
                                  (.026, 0, 0, .0088, .0087), (.040, 0, .001, .0079, .0080),
                                  (.047, 0, .001, .0078, .0079)]),
        "proximal_spine": front_plate([(-.0031, .010), (.0031, .010),
                                        (.0030, .039), (-.0030, .039)], -.0101, -.0088),
        "distal_shell": loft([(0, 0, 0, .0083, .0084), (.008, 0, 0, .0085, .0087),
                                (.023, 0, .001, .0075, .0078), (.034, 0, .003, .0065, .0067),
                                (.041, 0, .003, .0041, .0044)]),
        "distal_pad": front_plate([(-.0054, .018), (.0054, .018), (.0049, .035),
                                     (.0035, .040), (-.0035, .040), (-.0049, .035)],
                                    .0078, .0090),
        "palm_inlay": front_plate([(-.032, .000), (.032, .000), (.035, .013),
                                   (.029, .024), (-.035, .024), (-.040, .013)], .0222, .0229),
    }
    # Three opposing finger bases need only a compact palm, not the previous
    # four-finger plate. Keep the thumb anchored inside its radial edge.
    for name in ("palm_shell", "palm_face", "palm_inlay", "wrist_collar"):
        transform = np.eye(4)
        transform[0, 0] = .50 if name != "wrist_collar" else .60
        transform[0, 3] = .011
        shapes[name].apply_transform(transform)
    for name, mesh in shapes.items():
        (MESHES / f"{name}.obj").write_text(mesh.export(file_type="obj").rstrip() + "\n")


def build_urdf():
    root = ET.Element("robot", name="TALON-9-right-hand")
    palm = ET.SubElement(root, "link", name="palm")
    for mesh, color in (("palm_shell", "olive"), ("palm_face", "sage"),
                        ("wrist_collar", "graphite"), ("palm_inlay", "alloy")):
        visual(palm, mesh, color)
    # Four opposed two-link digits; the thumb has one extra base sweep.
    # The three fingers have NO lateral axis: MCP and PIP both flex forward.
    # The thumb bearing is integrated into the radial side of the palm.
    thumb_root = (.018, .024, .023)
    visual(palm, "thumb_bearing_housing", "olive", thumb_root)
    visual(palm, "thumb_socket", "olive", thumb_root)
    digits = [
        ("index", .027, .003, .048),
        ("middle", .008, .003, .048),
        ("ring", -.011, .003, .048),
    ]
    for name, x, y, z in digits:
        visual(palm, "motor_cover", "olive", (x, y, z), scale=(.82, .82, .82))
        proximal = ET.SubElement(root, "link", name=f"{name}_proximal")
        visual(proximal, "proximal_shell", "sage", scale=(.82, .82, .84))
        visual(proximal, "proximal_spine", "gold", scale=(.82, .82, .84))
        visual(proximal, "motor_cover", "olive", (0, 0, .03948), scale=(.82, .82, .82))
        visual(proximal, "motor_cap", "gold", (0, 0, .03948), scale=(.82, .82, .82))
        mcp = ET.SubElement(root, "joint", name=f"{name}_mcp_flex", type="revolute")
        ET.SubElement(mcp, "parent", link="palm")
        ET.SubElement(mcp, "child", link=f"{name}_proximal")
        ET.SubElement(mcp, "origin", xyz=f"{x} {y} {z}", rpy="0 0 0")
        ET.SubElement(mcp, "axis", xyz="-1 0 0")
        ET.SubElement(mcp, "limit", lower="0", upper=str(math.radians(85)),
                      effort="1.5", velocity="2.0")
        distal = ET.SubElement(root, "link", name=f"{name}_distal")
        visual(distal, "distal_shell", "sage", scale=(.82, .82, .82))
        visual(distal, "distal_pad", "olive", scale=(.82, .82, .82))
        pip = ET.SubElement(root, "joint", name=f"{name}_pip_flex", type="revolute")
        ET.SubElement(pip, "parent", link=f"{name}_proximal")
        ET.SubElement(pip, "child", link=f"{name}_distal")
        ET.SubElement(pip, "origin", xyz="0 0 0.03948", rpy="0 0 0")
        ET.SubElement(pip, "axis", xyz="-1 0 0")
        ET.SubElement(pip, "limit", lower="0", upper=str(math.radians(100)),
                      effort="1.5", velocity="2.0")

    # The Z-axis motor is inside the palm. Its short radial support rotates
    # with the buried bearing and carries a smaller two-link thumb outside.
    thumb_base_hub = ET.SubElement(root, "link", name="thumb_base_hub")
    visual(thumb_base_hub, "thumb_rotor", "alloy")
    visual(thumb_base_hub, "thumb_support", "olive", (0, .017, .011),
           (0, math.pi/2, 0))
    visual(thumb_base_hub, "motor_cover", "olive", (0, 0, 0), scale=(.86, .86, .86))
    visual(thumb_base_hub, "motor_cap", "gold", (0, 0, 0), scale=(.86, .86, .86))
    visual(thumb_base_hub, "motor_cover", "olive", (.031, .017, .011), scale=(.75, .75, .75))
    base_sweep = ET.SubElement(root, "joint", name="thumb_base_sweep", type="revolute")
    ET.SubElement(base_sweep, "parent", link="palm")
    ET.SubElement(base_sweep, "child", link="thumb_base_hub")
    ET.SubElement(base_sweep, "origin", xyz=" ".join(map(str, thumb_root)),
                  rpy="0 0 0")
    ET.SubElement(base_sweep, "axis", xyz="0 0 1")
    ET.SubElement(base_sweep, "limit", lower=str(math.radians(-20)),
                  upper=str(math.radians(86)), effort="1.5", velocity="2.0")
    thumb_proximal = ET.SubElement(root, "link", name="thumb_proximal")
    visual(thumb_proximal, "proximal_shell", "sage", scale=(.74, .74, .7234))
    visual(thumb_proximal, "proximal_spine", "gold", scale=(.74, .74, .7234))
    visual(thumb_proximal, "motor_cover", "olive", (0, 0, .034), scale=(.68, .68, .68))
    visual(thumb_proximal, "motor_cap", "gold", (0, 0, .034), scale=(.68, .68, .68))
    thumb_mcp = ET.SubElement(root, "joint", name="thumb_mcp_flex", type="revolute")
    ET.SubElement(thumb_mcp, "parent", link="thumb_base_hub")
    ET.SubElement(thumb_mcp, "child", link="thumb_proximal")
    ET.SubElement(thumb_mcp, "origin", xyz="0.031 0.017 0.011",
                  rpy="0 0 0")
    ET.SubElement(thumb_mcp, "axis", xyz="-1 0 0")
    ET.SubElement(thumb_mcp, "limit", lower="0", upper=str(math.radians(85)),
                  effort="1.5", velocity="2.0")
    thumb_distal = ET.SubElement(root, "link", name="thumb_distal")
    visual(thumb_distal, "distal_shell", "sage", scale=(.66, .66, .561))
    # Use the same shell/pad profile and orientation as the three fingers.
    # Rotating the thin pad independently left it visibly detached.
    visual(thumb_distal, "distal_pad", "olive", scale=(.66, .66, .561))
    thumb_pip = ET.SubElement(root, "joint", name="thumb_pip_flex", type="revolute")
    ET.SubElement(thumb_pip, "parent", link="thumb_proximal")
    ET.SubElement(thumb_pip, "child", link="thumb_distal")
    ET.SubElement(thumb_pip, "origin", xyz="0 0 0.034", rpy="0 0 0")
    ET.SubElement(thumb_pip, "axis", xyz="-1 0 0")
    ET.SubElement(thumb_pip, "limit", lower="0", upper=str(math.radians(100)),
                  effort="1.5", velocity="2.0")
    ET.indent(root, space="  ")
    (OUT / "hand.urdf").write_text(ET.tostring(root, encoding="unicode") + "\n")
    def pose(finger_mcp, finger_pip, thumb_base, thumb_mcp_angle, thumb_pip_angle):
        return {f"{name}_mcp_flex": finger_mcp for name, *_ in digits} | {
            f"{name}_pip_flex": finger_pip for name, *_ in digits} | {
            "thumb_base_sweep": thumb_base, "thumb_mcp_flex": thumb_mcp_angle,
            "thumb_pip_flex": thumb_pip_angle}
    poses = {
        "neutral": pose(5, 6, 0, 5, 6),
        "spread": pose(0, 0, -20, 0, 0),
        "wrap": pose(58, 52, 75, 56, 48),
        "pinch": pose(12, 12, 38, 0, 17) | {
            "index_mcp_flex": 53, "index_pip_flex": 2},
    }
    spec = {
        "controls": ([{"name": f"{name}_{joint}_flex", "label": "Proximal flex" if joint == "mcp" else "Distal flex",
                      "group": name.title()} for name, *_ in digits for joint in ("mcp", "pip")] +
                     [{"name": "thumb_base_sweep", "label": "Base sweep", "group": "Thumb"},
                      {"name": "thumb_mcp_flex", "label": "Proximal flex", "group": "Thumb"},
                      {"name": "thumb_pip_flex", "label": "Distal flex", "group": "Thumb"}]),
        "passive": [], "actuator_couplings": [], "poses": poses,
        "pinch_note": "The thumb and index fingertip converge in the nine-axis preview; grasp forces and force closure are not validated.",
        "concept_note": "Compact asymmetric four-digit right-hand gripper · three two-link fingers · palm-integrated Z-axis thumb bearing with a short radial support, proportionate proximal/distal links and the same fitted fingertip pad profile as the fingers · nine enclosed direct-drive axes · no passive joints.",
    }
    (OUT / "specification.json").write_text(json.dumps(spec, indent=2) + "\n")


def validate_pinch():
    """Validate that all three opposing fingers have a reachable thumb-tip pair."""
    from scipy.optimize import differential_evolution
    from scipy.spatial.transform import Rotation

    tip = np.array((0.0, .003, .041))
    for x in (.027, .008, -.011):
        def gap(q):
            base, thumb_mcp, thumb_pip, mcp, pip = q
            thumb_tip = (np.array((.018, .024, .023)) +
                         Rotation.from_euler("z", base, degrees=True).apply(
                             np.array((.031, .017, .011)) +
                             Rotation.from_euler("y", 0, degrees=True).apply(
                              Rotation.from_euler("x", -thumb_mcp, degrees=True).apply(
                                 np.array((0, 0, .034)) +
                                 Rotation.from_euler("x", -thumb_pip, degrees=True).apply(tip * .561)))))
            finger_tip = (np.array((x, .003, .048)) +
                          Rotation.from_euler("x", -mcp, degrees=True).apply(
                              np.array((0, 0, .03948)) +
                              Rotation.from_euler("x", -pip, degrees=True).apply(tip * .82)))
            return np.linalg.norm(thumb_tip - finger_tip)

        result = differential_evolution(gap, [(-20, 86), (0, 85), (0, 100),
                                               (0, 85), (0, 100)], seed=9,
                                        maxiter=120, popsize=9, polish=True)
        assert result.fun < .008, (x, result.fun, result.x)
        if x == .027:
            assert gap((38, 0, 17, 53, 2)) < .008


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    save_meshes()
    build_urdf()
    validate_pinch()
    print(OUT)
