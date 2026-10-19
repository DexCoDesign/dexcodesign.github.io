"""Display-only colors for the Hand Studio's untextured visual meshes.

These are approximate material colors based on the linked manufacturer or
project photographs and the owner's visual review, not measured spectral values. They never change the
source URDF, mesh geometry, joint kinematics, or simulation assets.
"""

PHOTO_REFERENCES = {
    "wuji_hand_2": "https://wuji.tech/en/hand2",
    "sharpa_wave_01": "https://www.sharpa.com/pages/w01",
    "tesollo_dg5f": "https://en.tesollo.com/news/?mod=document&uid=94",
    "unitree_dex5_1": "https://www.unitree.com/Dex5-1/",
    "shadow_hand_e": "https://shadowrobot.com/dexterous-hand-series/",
    "midas_hand": "https://www.robotis.us/midas-hand-bundle/",
    "ruka_v2": "https://ruka-hand-v2.github.io/",
    "inspire_rh56dfx": "https://en.inspire-robots.com/product/rh56dfx",
}


def display_rgba(model_id, link, visual_index, source_rgba):
    """Return (RGBA, provenance) or None to retain the authored color."""
    if model_id == "wuji_hand_2":
        if "wrist" in link:
            rgb = (.44, .47, .50)  # this visual mesh is the broad palm shell
        elif "base" in link:
            rgb = (.08, .09, .10)  # the lower mounting flange
        elif any(word in link for word in ("proximal", "middle", "distal")):
            rgb = (.46, .49, .52)
        else:
            return None
    elif model_id == "sharpa_wave_01":
        rgb = (.43, .46, .49)
    elif model_id == "tesollo_dg5f":
        if "mount" in link or "tip" in link:
            rgb = (.12, .13, .14)
        elif "base" in link or "palm" in link:
            rgb = (.70, .72, .73) if visual_index == 0 else (.47, .49, .51)
        else:
            rgb = (.47, .50, .52)
    elif model_id == "unitree_dex5_1":
        rgb = (.085, .09, .095)  # uniform printed black, slightly lighter than XHand
    elif model_id == "shadow_hand_e":
        rgb = (.34, .36, .38) if "knuckle" in link or "wrist" in link else (.10, .11, .12)
    elif model_id == "midas_hand":
        rgb = (.11, .115, .12) if "dip" in link else (.085, .09, .095)
    elif model_id == "ruka_v2":
        rgb = (.085, .09, .095)
    elif model_id == "inspire_rh56dfx":
        if link.startswith("thumb_proximal") or "intermediate" in link or "distal" in link:
            rgb = (.12, .13, .14)
        elif link == "base":
            rgb = (.96, .97, .96)  # brighter gray-white palm casing
        else:
            rgb = (.84, .85, .84)  # warm gray-white, not neutral gray
    else:
        return None
    return [*rgb, 1.0], "studio-photo-approximation"


def display_surface(model_id, link):
    """(metalness, roughness); plastic matches the approved XHand baseline."""
    if model_id == "sharpa_wave_01":
        return .62, .26
    if model_id == "wuji_hand_2" and "base" not in link:
        return .60, .28
    if model_id == "tesollo_dg5f" and not any(word in link for word in ("mount", "tip", "base", "palm")):
        return .34, .36
    if model_id in {"unitree_dex5_1", "midas_hand", "ruka_v2"}:
        return .06, .66  # dark 3D-printed shell, shared renderer lighting
    return .12, .56
