#!/usr/bin/env python3
"""Derive display poses from the published robots' real kinematic chains.

These are visual presets, not grasp/force-closure claims. Spread changes only
lateral joints; pinch minimizes the thumb/index tip separation while leaving
every other finger at neutral. No source URDF or mesh is modified.
"""
import json
import argparse
import re
from pathlib import Path

import numpy as np
import trimesh
from scipy.optimize import differential_evolution
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "assets/models/studio"
TIPS = {
    "wuji_hand_2": ("r_thumb_tip", "r_index_finger_tip", "r_middle_finger_tip", "r_ring_finger_tip", "r_pinky_tip"),
    "sharpa_wave_01": ("right_thumb_fingertip", "right_index_fingertip", "right_middle_fingertip", "right_ring_fingertip", "right_pinky_fingertip"),
    "tesollo_dg5f": ("rl_dg_1_tip", "rl_dg_2_tip", "rl_dg_3_tip", "rl_dg_4_tip", "rl_dg_5_tip"),
    "unitree_dex5_1": ("Link_14R", "Link_24R", "Link_34R", "Link_44R", "Link_54R"),
    "shadow_hand_e": ("rh_thtip", "rh_fftip", "rh_mftip", "rh_rftip", "rh_lftip"),
    "midas_hand": ("thumb_dip", "index_dip_link", "middle_dip_link", "ring_dip_link"),
    "ruka_v2": ("thumb_actual_tip", "index_actual_tip", "middle_actual_tip", "ring_actual_tip", "pinky_actual_tip"),
    "inspire_rh56dfx": ("thumb_distal", "index_intermediate", "middle_intermediate", "ring_intermediate", "pinky_intermediate"),
    "robotera_xhand1_pro": ("right_hand_thumb_top_link", "right_hand_index_top_link", "right_hand_mid_top_link", "right_hand_ring_top_link", "right_hand_pinky_top_link"),
}


def finger(model_id, name):
    n = name.lower()
    if model_id == "unitree_dex5_1":
        match = re.search(r"_(\d)[1-4]r$", n)
        return ("thumb", "index", "middle", "ring", "little")[int(match[1])-1] if match else None
    if model_id == "tesollo_dg5f":
        match = re.search(r"dg_(\d)_", n)
        return ("thumb", "index", "middle", "ring", "little")[int(match[1])-1] if match else None
    if model_id == "shadow_hand_e":
        match = re.search(r"_(th|ff|mf|rf|lf)j", n)
        return dict(th="thumb", ff="index", mf="middle", rf="ring", lf="little").get(match[1]) if match else None
    if model_id == "robotera_xhand1_pro":
        match = re.search(r"_(thumb|index|mid|ring|pinky)_", n)
        return dict(thumb="thumb", index="index", mid="middle", ring="ring", pinky="little").get(match[1]) if match else None
    for word, digit in (("thumb", "thumb"), ("index", "index"), ("middle", "middle"), ("mid_", "middle"),
                        ("ring", "ring"), ("little", "little"), ("pinky", "little")):
        if word in n:
            return digit
    return None


def lateral(model_id, name):
    n = name.lower()
    if model_id == "unitree_dex5_1": return bool(re.search(r"(?:yaw_11r|roll_[2-5]1r)$", n))
    # Tesollo's fifth digit starts with a palm-fold joint. Its lateral
    # finger hinge is joint 2, unlike the other four digits.
    if model_id == "tesollo_dg5f": return bool(re.search(r"dg_[1-4]_1$|dg_5_2$", n))
    if model_id == "shadow_hand_e": return bool(re.search(r"(?:ff|mf|rf|lf)j4$|thj[35]$", n))
    if model_id == "robotera_xhand1_pro": return "_mcp0_joint" in n
    if model_id == "ruka_v2": return "splay" in n or n == "thumb_cmc"
    if model_id == "inspire_rh56dfx": return "thumb_proximal_yaw" in n
    return bool(re.search(r"(?:abd|abad|_aa|splay|side)", n))


class KinematicModel:
    def __init__(self, model_id):
        self.id = model_id
        self.data = json.loads((MODELS / f"{model_id}.json").read_text())
        self.scene = trimesh.load(MODELS / f"{model_id}.glb", force="scene")
        self.parent = self.scene.graph.transforms.parents
        self.edge = self.scene.graph.transforms.edge_data
        self.joints = {j["node"]: j for j in self.data["joints"]}
        self.joint_by_name = {j["name"]: j for j in self.data["joints"]}
        self.controls = self.data["controls"]
        self.neutral = {c["name"]: float(self.data["poses"]["neutral"].get(c["name"], 0)) for c in self.controls}
        self.tips = {}
        for digit, link in zip(("thumb", "index", "middle", "ring", "little"), TIPS[model_id]):
            node = "link__" + link
            assert node in self.scene.graph.nodes, (model_id, node)
            self.tips[digit] = (node, self._local_tip(node, link))
        self.paths = {digit: self._path(node) for digit, (node, _) in self.tips.items()}

    def close_preview_loops(self, q):
        """Constrain MIDAS display joints using the original MJCF four-bars."""
        curves = self.data.get("closed_loop_preview", {}).get("fingers")
        if not curves:
            return q
        result = dict(q)
        for finger, rows in curves.items():
            pip = np.clip(result[f"{finger}_pip_joint"], rows[-1][0], rows[0][0])
            rows = np.asarray(rows)
            result[f"{finger}_dip_joint"] = float(np.interp(pip, rows[::-1, 0], rows[::-1, 1]))
            result[f"{finger}_dip_linkage_joint"] = float(np.interp(pip, rows[::-1, 0], rows[::-1, 2]))
        return result

    def _path(self, node):
        result = []
        while node in self.parent:
            result.append(node)
            node = self.parent[node]
        return list(reversed(result))

    def _local_tip(self, node, link):
        # Published explicit tip frames are the cleanest landmark. For models
        # without one, use the furthest point of the terminal link's own mesh.
        if re.search(r"(?:tip|fingertip)$", link, re.I):
            return np.zeros(3)
        visual_nodes = [child for child, parent in self.parent.items()
                        if parent == node and child in self.scene.graph.nodes_geometry]
        if not visual_nodes:
            return np.zeros(3)
        candidates = []
        for child in visual_nodes:
            edge = self.edge[(node, child)]
            mesh = self.scene.geometry[edge["geometry"]]
            vertices = trimesh.transform_points(mesh.vertices, np.array(edge["matrix"]))
            candidates.append(vertices[::max(1, len(vertices)//500)])
        vertices = np.concatenate(candidates)
        # The mesh's distal point is furthest from the terminal joint origin.
        return vertices[np.argmax(np.linalg.norm(vertices, axis=1))]

    def tip(self, digit, q):
        q = self.close_preview_loops(q)
        node, point = self.tips[digit]
        matrix = np.eye(4)
        for child in self.paths[digit]:
            parent = self.parent[child]
            local = np.array(self.edge[(parent, child)]["matrix"])
            joint = self.joints.get(child)
            if joint:
                if joint.get("mimic"):
                    mimic = joint["mimic"]
                    value = q.get(mimic["source"], 0) * mimic["multiplier"] + mimic["offset"]
                else:
                    value = q.get(joint["name"], 0)
                if joint["type"] == "revolute":
                    turn = np.eye(4)
                    turn[:3, :3] = Rotation.from_rotvec(np.array(joint["axis"]) * value).as_matrix()
                    local = local @ turn
                elif joint["type"] == "prismatic":
                    local[:3, 3] += local[:3, :3] @ np.array(joint["axis"]) * value
            matrix = matrix @ local
        return (matrix @ np.r_[point, 1])[:3]


def derive_spread(model):
    q0 = model.neutral
    spread = dict(q0)
    digits = [d for d in ("index", "middle", "ring", "little") if d in model.tips]
    lateral_axis = model.tip(digits[0], q0) - model.tip(digits[-1], q0)
    lateral_axis /= np.linalg.norm(lateral_axis)
    order = [d for d in ("index", "ring", "little", "thumb") if d in model.tips]
    for digit in order:
        reference = "index" if digit == "thumb" else "middle" if digit != "little" else "ring"
        if reference not in model.tips: continue
        for c in model.controls:
            if finger(model.id, c["name"]) != digit or not lateral(model.id, c["name"]): continue
            name = c["name"]
            candidates = [q0[name], q0[name]+.72*(c["lower"]-q0[name]), q0[name]+.72*(c["upper"]-q0[name])]
            if model.id == "tesollo_dg5f" and name == "rj_dg_5_2":
                # Its unusually large upper limit also serves opposition;
                # a moderate fan, not the end-stop, is the Spread preview.
                candidates = [q0[name], max(c["lower"], q0[name]-.5), min(c["upper"], q0[name]+.5)]
            def separation(value):
                pose = {**spread, name: value}
                if digit == "thumb":
                    return np.linalg.norm(model.tip(digit, pose)-model.tip(reference, pose))
                # Unsigned tip distance can increase after a finger crosses
                # its neighbor. Choose the signed outward motion instead.
                sign = 1.0 if digit == "index" else -1.0
                return sign * np.dot(model.tip(digit, pose)-model.tip(digit, q0), lateral_axis)
            spread[name] = max(candidates, key=separation)

    if model.id == "wuji_hand_2":
        # A pairwise-distance maximum picked the *inward* pinky extreme:
        # it crossed the ring finger despite increasing their 3-D tip gap.
        # On the right hand, positive MCP abduction moves the little tip
        # outward (toward negative world X). Give the ring less abduction
        # than the little finger so *every* adjacent fingertip gap grows.
        for name, fraction in (("r_ring_finger_mcp_abd", .42),
                               ("r_pinky_mcp_abd", .72)):
            control = next(c for c in model.controls if c["name"] == name)
            spread[name] = q0[name] + fraction * (control["upper"] - q0[name])
        digits = ("index", "middle", "ring", "little")
        tips = [model.tip(digit, spread)[0] for digit in digits]
        baseline = [model.tip(digit, q0)[0] for digit in digits]
        assert all(a-b > a0-b0 for a,b,a0,b0 in zip(tips,tips[1:],baseline,baseline[1:])), (tips, baseline)

    tips = np.array([model.tip(digit, spread) for digit in digits])
    signed_gaps = np.diff(-tips @ lateral_axis)
    assert np.all(signed_gaps > 0), (model.id, "Spread crossed neighboring fingers", signed_gaps)
    return spread


def derive(model):
    q0 = model.neutral
    spread = derive_spread(model)

    selected = [c for c in model.controls if finger(model.id, c["name"]) in {"thumb", "index"}
                and "linkage" not in c["name"].lower()
                and not (model.id == "midas_hand" and c["name"] == "index_dip_joint")]
    x0 = np.array([q0[c["name"]] for c in selected])
    bounds = [(c["lower"], c["upper"]) for c in selected]
    def objective(values):
        pose = {**q0, **{c["name"]: value for c, value in zip(selected, values)}}
        gap = np.linalg.norm(model.tip("thumb", pose)-model.tip("index", pose))
        # Mild regularization prevents a contorted end-stop pose when several
        # configurations reach the same gap. The distance remains primary.
        reg = sum(((value-base)/max(upper-lower, .01))**2
                  for value, base, (lower, upper) in zip(values, x0, bounds))
        return gap + .004 * reg
    result = differential_evolution(objective, bounds, seed=23, maxiter=60,
                                    popsize=5, polish=True, tol=.001)
    pinch = model.close_preview_loops({**q0, **{c["name"]: float(value) for c, value in zip(selected, result.x)}})
    neutral_gap = float(np.linalg.norm(model.tip("thumb", q0)-model.tip("index", q0)))
    pinch_gap = float(np.linalg.norm(model.tip("thumb", pinch)-model.tip("index", pinch)))
    assert pinch_gap < neutral_gap, (model.id, neutral_gap, pinch_gap)
    # A wrap preview can use the source's existing flex pose; do not reuse it
    # for Spread or Pinch, where opposite-sign limits are common.
    wrap = model.close_preview_loops(dict(model.data["poses"]["flex"]))
    return {"spread": spread, "wrap": wrap, "pinch": pinch}, {
        "neutral_tip_gap_m": neutral_gap, "pinch_tip_gap_m": pinch_gap,
        "spread_lateral_joints": [c["name"] for c in model.controls
                                   if spread[c["name"]] != q0[c["name"]]],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", choices=TIPS)
    parser.add_argument("--spread-only", action="store_true", help="Update Spread without changing other presets")
    args = parser.parse_args()
    profile_path = MODELS / "robot_pose_profiles.json"
    audit_path = MODELS / "robot_pose_audit.json"
    profiles = json.loads(profile_path.read_text()) if (args.model_id or args.spread_only) and profile_path.exists() else {}
    audit = json.loads(audit_path.read_text()) if (args.model_id or args.spread_only) and audit_path.exists() else {}
    for model_id in ([args.model_id] if args.model_id else TIPS):
        model = KinematicModel(model_id)
        if args.spread_only:
            poses = {"spread": derive_spread(model)}
            checks = {"spread_lateral_joints": [c["name"] for c in model.controls
                       if poses["spread"][c["name"]] != model.neutral[c["name"]]]}
        else:
            poses, checks = derive(model)
        profiles[model_id] = {**profiles.get(model_id, {}), **poses}
        audit[model_id] = {**audit.get(model_id, {}), **checks}
        print(model_id, checks, flush=True)
        model.data["poses"].update(poses)
        if model_id == "midas_hand" and not args.spread_only:
            model.data["poses"]["flex"] = model.close_preview_loops(model.data["poses"]["flex"])
        if not args.spread_only:
            model.data["pinch_note"] = "Thumb/index tip-alignment preview; force closure and contact are not validated."
        (MODELS / f"{model_id}.json").write_text(json.dumps(model.data, separators=(",", ":")) + "\n")
    profile_path.write_text(json.dumps(profiles, indent=2) + "\n")
    audit_path.write_text(json.dumps(audit, indent=2) + "\n")


if __name__ == "__main__":
    main()
