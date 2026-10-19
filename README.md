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

The catalog has 21 right-side models: MANO under **Hand**, nine real embodiments
under **Robot hand**, ten generated concepts under **AI gen**, and the SUPR foot
under **Others**. The active/coupled counts describe the project's direct-motor
simulation assets, not necessarily the manufacturer's original transmission.
AI concepts are reflected into the same right-hand convention; both transforms
and axial vectors are reflected, not just the mesh.

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
