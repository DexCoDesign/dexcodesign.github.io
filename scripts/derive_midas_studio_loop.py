#!/usr/bin/env python3
"""Bake the original MIDAS fingertip four-bar closure for the web preview.

The direct-motor URDF used by the studio omits the upstream MJCF's equality
constraints. This sampled table restores only the visual kinematics; it does
not modify the URDF or claim that a training simulation has the same closure.
"""
import argparse
import json
from pathlib import Path

import mujoco
import numpy as np
from scipy.optimize import least_squares


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "assets/models/studio/midas_hand.json"
DEFAULT_MJCF = (ROOT.parent / "DexCoDesign/assets/robot_hands/midas_hand/source/assets/"
                "midas_description/midas_whole_hand.xml")
FINGERS = ("index", "middle", "ring")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mjcf", type=Path, default=DEFAULT_MJCF)
    args = parser.parse_args()
    model = mujoco.MjModel.from_xml_path(str(args.mjcf))
    data = mujoco.MjData(model)
    curves = {}
    for finger in FINGERS:
        names = [f"{finger}_pip_joint", f"{finger}_dip_joint",
                 f"{finger}_dip_linkage_joint"]
        addresses = [model.jnt_qposadr[model.joint(name).id] for name in names]
        site_a = model.site(f"{finger}_dip_pin").id
        site_b = model.site(f"{finger}_linkage_pin").id
        last = np.zeros(2)
        samples = []
        for pip in np.linspace(0, -1.45, 59):
            def residual(free):
                data.qpos[:] = model.qpos0
                data.qpos[addresses] = (pip, *free)
                mujoco.mj_forward(model, data)
                return data.site_xpos[site_a] - data.site_xpos[site_b]
            fit = least_squares(residual, last, bounds=(-3.14, 3.14),
                                xtol=1e-13, ftol=1e-13, gtol=1e-13)
            mismatch = float(np.linalg.norm(residual(fit.x)))
            if mismatch > 1e-4:
                raise ValueError(f"{finger} loop mismatch {mismatch:.6g} m at PIP {pip:.3f}")
            last = fit.x
            samples.append([round(float(pip), 7), *[round(float(v), 7) for v in last]])
        curves[finger] = samples
    metadata = json.loads(METADATA.read_text())
    metadata["closed_loop_preview"] = {
        "source": "original MIDAS MJCF equality/connect fingertip loops",
        "scope": "visual preview only; direct-motor training URDF is unchanged",
        "columns": ["pip_rad", "dip_rad", "linkage_rad"],
        "fingers": curves,
    }
    METADATA.write_text(json.dumps(metadata, separators=(",", ":")) + "\n")
    print("Wrote MIDAS visual loop lookup to", METADATA)


if __name__ == "__main__":
    main()
