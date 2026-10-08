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
