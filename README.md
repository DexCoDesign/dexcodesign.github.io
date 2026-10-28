# DexCoDesign Project Page

Static research project page for <https://dexcodesign.github.io>, organized like the EgoEngine project website but intentionally populated with replaceable placeholders.

## Replace the placeholders

1. Update the title, authors, affiliations, venue, links, abstract, and section copy in `index.html`.
2. Put figures and posters in `assets/images/`.
3. Put the paper or supplementary PDF in `assets/pdfs/`.
4. Put videos in the matching subdirectories under `assets/videos/`.
5. Replace each `.media-placeholder` block with an `<img>` or `<video>` element.
6. Update the BibTeX entry in the Citation section.

Example video markup:

```html
<video
  src="assets/videos/demos/demo-01.mp4"
  autoplay
  muted
  loop
  playsinline
  preload="metadata">
</video>
```

## Media structure

```text
assets/
├── css/
├── images/
├── js/
├── pdfs/
└── videos/
    ├── hero/
    ├── teaser/
    ├── demos/
    └── results/
```

Empty media directories are retained with `.gitkeep` files.

## Hand Studio (static, no simulation server)

The studio near the top of the page runs visual forward kinematics in the browser.
Three.js 0.180.0 is vendored under `assets/vendor/three` (MIT); only one model is
loaded at a time. No Python, GPU server, WebSocket, or CDN is required in production.
GitHub Pages serves the meshes, joint metadata, and scripts as ordinary files.

The catalog has 21 hand/foot models plus eight bimanual manipulators:
MANO under **Hand**, nine real embodiments under **Robot hand**, ten generated
concepts under **AI Hand**, Dexmate Vega, Rainbow RB-Y1, Gento Luna, DYNA Taku,
Franka FR3, Kinova Gen3, ALOHA 2 and OpenArm 2.0 under **Manipulator**, and the SUPR foot under **Others**.
The active/coupled counts describe the project's direct-motor
simulation assets, not necessarily the manufacturer's original transmission.
AI concepts are reflected into the same right-hand convention; both transforms
and axial vectors are reflected, not just the mesh. TALON-9's authored source
is left-sided; its exported browser GLB and the reconstructed physical right
asset use the reflected geometry. Its physical left asset is mirrored from the
right with Skynet's existing routine.

Authoritative real geometry and kinematics come from the Skynet snapshot at
`3fc9c1f26882f4baee43c419d247ece9fb4a3109`. Each model JSON records source URDF/mesh
SHA-256 hashes. No training results, datasets, checkpoints, or raw source meshes
are part of this website update. Display meshes are reduced only for browser size.
Do not regenerate real assets from an unrelated Mac training checkout.

Rebuild with a right-side-only copy of Skynet's `assets/robot_hands` and the local
AI concept source:

```sh
python scripts/export_hand_studio.py --ai-root /path/to/ArcusHand \
  --skynet-root /path/to/snapshot/robot_hands \
  --snapshot-commit <Skynet-commit>
python -m http.server 8767 --bind 127.0.0.1
```

Dependencies for the exporter: NumPy, SciPy, trimesh, and fast-simplification.
`scripts/qa_hand_studio.cjs` tests all categories, controls, pose buttons, orbiting,
and mobile layout using a local Playwright installation. Point `PLAYWRIGHT_MODULE`
at that package and optionally set `CHROME_PATH`. `QA_MODELS` accepts comma-separated
model IDs for a focused check. QA images are not published. Run
`scripts/refresh_hand_studio_posters.cjs` against the same local server after
changing display colors or meshes, so the loading posters match the live model.
Run
`scripts/validate_hand_studio.py` with the same `--ai-root` and `--skynet-root`
arguments to compare exported joint transforms against the authoritative URDFs.

### Appearance and limitations

The source converter's MJCF route drops mesh colors (`include_color=False`) and
does not write a URDF material. Shadow's plastic/metal and Inspire's visual default
are recovered from the original MJCF. MANO's source has no authored skin material;
its neutral MuJoCo default is retained. Tesollo has missing/placeholder materials;
its neutral metal, light housing, and dark tips are a display-only approximation
of the [manufacturer's DG-5F images](https://www.tesollo.com/products/grippers/dg-5f-m).
Sharpa's bright-green elastomer comes from its source CAD, not from a new exporter
bug; the display uses a subdued elastomer approximation, informed by the
[manufacturer's Wave page](https://www.sharpa.com/pages/w01). Unitree's translucent casing
is displayed opaque. Existing XHAND Pro, Wuji, Ruka, and MIDAS colors are retained.
Per-visual metadata distinguishes recovered values, original values, and approximations.
No authoritative Skynet training geometry, collision, mass, or joint settings were changed.

Passive springs are shown at rest in the browser; mimic joints follow their active
masters. Pinch presets are joint configurations, not contact or force-closure tests.
Original license notices accompany the display assets under
`assets/models/studio/licenses`; no manufacturer endorsement is implied.

### Manipulator collection

`Manipulator` sits between `AI Hand` and `Others`. Its eight models are Vega,
RB-Y1, Gento Luna, Taku, Franka FR3, Kinova Gen3, ALOHA 2 and OpenArm 2.0. The initial view is Dexmate Vega with LYRA-10. One **EEF** selector
attaches the chosen human, robot or AI hand to both arms; **None** removes both.
The opposite hand is a mirrored instance of the same original geometry.
Changing manipulator models preserves the selected EEF, including an explicit
None selection. Reloading restores the Dexmate/LYRA-10 initial view.
Changing EEFs shows the loading preview and pauses joint motion, orbit controls,
sliders, pose buttons and the EEF selector until the new hands are rendered.
Cached hands also paint this loading state before cloning/uploading geometry.
Model and collection selectors remain available to cancel the pending load;
a failed replacement restores the previous hands and controls.

All four models share three virtual base controls: Base X, Base Y (±50 mm),
and Base yaw (±20 degrees). Wheel and steering motor coordinates are fixed and
absent from the controls and Slow motion. The complete robot and both mounted
hands move rigidly with the virtual base; no wheel rolling or drive model is used.

Gento Luna now uses the vendor V3.0 M6SLite package supplied on 2026-10-26.
It includes the separate shoulder housings absent from the April source model.
The original arm frames and limits are from V3; canonical joint names remain
stable and Home/Spread/Fold were refitted to the previous physical flange poses.
Factory grippers are removed. Base yaw spans ±20 degrees. MANO uses an explicit
natural skin display color; its original mesh and kinematics remain unchanged.

Home keeps the upper body vertical while bending the lower torso/support chain
to reduce height, with forward-facing hands at tabletop working height. Spread restores the upright, straight-arm pose. Fold lowers the
torso substantially and keeps the forearms forward in a bent working pose.
These joint values are maintained in the local library's `preview_poses.json`
and shared with the native MuJoCo launcher. Vega faces source +X, toward the
protruding base; its physical left/right use vendor L/R.

Slow motion animates every movable independent joint within its limits. Mirror
signs and offsets come from the source joint axes; paired arms and hands share
one motion track. Mimic followers, MIDAS fingertip loops and KESTREL's passive
palm response retain their existing visual relationships. Pose transitions use
elapsed time so their duration is independent of rendering frame rate.

Hand meshes and materials are loaded once and reused for each combination;
there are no combination-specific GLBs. `attachment_profiles.json` records wrist
roots and visual adapters. RUKA and Unitree are centered on their actual base plates. RUKA's
base center is about 33 mm from its source origin. Shadow retains `rh_forearm` and
its complete base, wrist and finger geometry. World/floating standalone motion
is excluded. Per-hand sliders and Open/Close hands remain available.

The four mobile models use `body/robot.urdf` with original end effectors removed.
Source visual materials are retained for Vega, RB-Y1 and Taku. Luna's warm gray
shell and black visor approximate official photos, replacing vendor RGB
placeholders. Taku is a public-web reconstruction with placeholder limits.
The viewer validates neither contacts nor dynamics.

```sh
python scripts/export_manipulator_studio.py \
  --asset-root /path/to/DexCoDesign/assets/mobile_manipulators
python scripts/export_attachment_profiles.py
python scripts/validate_manipulator_studio.py \
  --asset-root /path/to/DexCoDesign/assets/mobile_manipulators
```

The independent FK validator checks Home, Spread, Fold and two sampled poses.
`qa_manipulator_attachments.cjs` checks all 20 selectable hands, both mount graphs,
actual joint motion and symmetry, rapid replacement/removal, RUKA/Shadow/Unitree base
centering, and mobile layout. `qa_hand_studio.cjs` covers the original collections.
`qa_eef_loading.cjs` checks delayed/cached loading, frozen controls, error recovery
and cancellation while another model is loading.
`qa_planar_base.cjs` checks all three base controls and the rigid motion of every
robot link and both mounted hands, including Gento Luna.
Existing authoritative hand/foot GLBs and JSON are preserved byte-for-byte.

Refresh posters with `POSTER_MODELS=dexmate_vega,rby1,gento_luna,dyna_taku`.
Open `?collection=manipulator&model=dyna_taku#hand-studio` for the collection.
The deployed site needs static hosting only.

### Fixed-lift bimanual arms

Franka FR3, Kinova Gen3, ALOHA 2 (dual ViperX), and OpenArm 2.0 use the same fixed lift and 45° mount. The base adds no controls. The final mount has thicker U-cradle walls, a narrow inner housing in the same dark gray, and five upper-rim screw caps per side. Native left/right arm limits, joint frames and Home configurations are retained. Per-flange fixed adapters align the mirrored EEFs; sampled arm IK keeps the tools symmetric during Slow motion without imposing equal joint angles.

```sh
python scripts/export_bimanual_studio.py --project-root /path/to/DexCoDesign
```

This adds the four arms without regenerating existing mobile or hand models.
