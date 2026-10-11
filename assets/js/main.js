const nav = document.querySelector('.site-nav');

const updateNav = () => {
  nav?.classList.toggle('scrolled', window.scrollY > 32);
};

updateNav();
window.addEventListener('scroll', updateNav, { passive: true });

document.querySelectorAll('a[href^="#"]').forEach((link) => {
  link.addEventListener('click', (event) => {
    const target = document.querySelector(link.getAttribute('href'));
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});

const gallery = document.querySelector('#training-gallery');
const status = document.querySelector('#video-status');
const filterButtons = [...document.querySelectorAll('[data-video-filter]')];
const videos = window.DEXCODESIGN_VIDEOS || [];
const datasetNames = {
  taco: 'TACO',
  hocap: 'HOCAP',
  penspin: 'PenSpin',
  oakink2: 'OakInk2',
  arctic: 'ARCTIC',
  dexterhand: 'DexterHand'
};
const pendingDatasets = ['oakink2', 'arctic', 'dexterhand'];

let activeCard = null;
let activeFilter = 'taco';
let galleryResizeFrame = null;
const thumbnailObserver = 'IntersectionObserver' in window
  ? new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting || entry.target.closest('.demo-card')?.hidden) return;
        entry.target.src = entry.target.dataset.src;
        observer.unobserve(entry.target);
      });
    }, { root: gallery, rootMargin: '360px 0px' })
  : null;

const titleFor = (item) => `${datasetNames[item.dataset]} · ${item.sample}`;
const thumbnailFor = (item) => `assets/images/thumbnails/${item.dataset}/${item.file.replace(/\.mp4$/, '.jpg')}`;

const launchButtonFor = (item, card) => {
  const button = document.createElement('button');
  button.className = 'video-launch';
  button.type = 'button';
  button.setAttribute('aria-label', `Load video: ${titleFor(item)}`);

  const thumbnail = document.createElement('img');
  thumbnail.className = 'video-thumbnail';
  thumbnail.dataset.src = thumbnailFor(item);
  thumbnail.alt = '';
  thumbnail.loading = 'lazy';
  thumbnail.decoding = 'async';

  const icon = document.createElement('span');
  icon.className = 'play-icon';
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '▶';

  const label = document.createElement('span');
  label.className = 'video-launch-label';
  label.textContent = 'Click to load video';

  button.append(thumbnail, icon, label);
  button.addEventListener('click', () => loadVideo(item, card));
  return button;
};

const updateStatus = () => {
  if (!status) return;
  const visibleCount = videos.filter((item) => item.dataset === activeFilter).length;
  status.textContent = visibleCount
    ? `Showing ${visibleCount} ${datasetNames[activeFilter]} videos · ${activeCard ? '1 video loaded' : 'none loaded'}`
    : `${datasetNames[activeFilter]} demonstrations · coming soon`;
};

const updateGalleryHeight = () => {
  if (!gallery) return;
  const visibleCards = [...gallery.children].filter((card) => !card.hidden);
  const columns = getComputedStyle(gallery).gridTemplateColumns.split(' ').length;
  const twoRows = columns * 2;

  if (visibleCards.length <= twoRows) {
    gallery.style.maxHeight = 'none';
    return;
  }

  const galleryTop = gallery.getBoundingClientRect().top;
  const secondRowBottom = visibleCards[twoRows - 1].getBoundingClientRect().bottom;
  gallery.style.maxHeight = `${Math.ceil(secondRowBottom - galleryTop + 2)}px`;
};

const scheduleGalleryHeight = () => {
  cancelAnimationFrame(galleryResizeFrame);
  galleryResizeFrame = requestAnimationFrame(updateGalleryHeight);
};

const queueThumbnail = (thumbnail) => {
  if (!thumbnail || thumbnail.hasAttribute('src')) return;
  if (thumbnailObserver) thumbnailObserver.observe(thumbnail);
  else thumbnail.src = thumbnail.dataset.src;
};

const unloadVideo = () => {
  if (!activeCard) return;
  const item = activeCard.videoItem;
  const media = activeCard.querySelector('.demo-media');
  const video = media?.querySelector('video');

  if (video) {
    video.pause();
    video.removeAttribute('src');
    video.load();
  }

  const launchButton = launchButtonFor(item, activeCard);
  media?.replaceChildren(launchButton);
  if (!activeCard.hidden) queueThumbnail(launchButton.querySelector('.video-thumbnail'));
  activeCard = null;
};

const loadVideo = (item, card) => {
  unloadVideo();

  const media = card.querySelector('.demo-media');
  const video = document.createElement('video');
  video.controls = true;
  video.loop = true;
  video.muted = true;
  video.playsInline = true;
  video.preload = 'metadata';
  video.setAttribute('aria-label', titleFor(item));
  video.src = `assets/videos/training/${item.dataset}/${item.file}`;

  media.replaceChildren(video);
  activeCard = card;
  updateStatus();
  video.play().catch(() => {});
};

const renderGallery = () => {
  if (!gallery) return;

  videos.forEach((item) => {
    const card = document.createElement('article');
    card.className = 'demo-card';
    card.dataset.dataset = item.dataset;
    card.videoItem = item;

    const media = document.createElement('div');
    media.className = 'demo-media';
    media.append(launchButtonFor(item, card));

    const copy = document.createElement('div');
    copy.className = 'demo-copy';

    const title = document.createElement('h3');
    title.textContent = titleFor(item);

    const meta = document.createElement('p');
    meta.className = 'demo-meta';
    const tag = document.createElement('span');
    tag.className = 'dataset-tag';
    tag.textContent = datasetNames[item.dataset];
    const hand = document.createElement('span');
    hand.textContent = `${item.hand} hand · successful rollout`;
    meta.append(tag, hand);

    copy.append(title, meta);
    card.append(media, copy);
    gallery.append(card);
  });

  pendingDatasets.forEach((dataset) => {
    const card = document.createElement('article');
    card.className = 'dataset-placeholder dataset-placeholder--gallery';
    card.dataset.dataset = dataset;

    const badge = document.createElement('span');
    badge.textContent = 'Coming soon';
    const title = document.createElement('h4');
    title.textContent = datasetNames[dataset];
    const copy = document.createElement('p');
    copy.textContent = 'Training demonstrations are in progress.';

    card.append(badge, title, copy);
    gallery.append(card);
  });
};

const applyFilter = () => {
  [...gallery.children].forEach((card) => {
    card.hidden = card.dataset.dataset !== activeFilter;
  });

  if (activeCard?.hidden) unloadVideo();
  updateStatus();
  updateGalleryHeight();

  thumbnailObserver?.disconnect();
  gallery.querySelectorAll('.demo-card:not([hidden]) .video-thumbnail:not([src])').forEach(queueThumbnail);
};

filterButtons.forEach((button) => {
  button.addEventListener('click', () => {
    activeFilter = button.dataset.videoFilter;
    filterButtons.forEach((candidate) => candidate.classList.toggle('is-active', candidate === button));

    applyFilter();
  });
});

renderGallery();
applyFilter();
window.addEventListener('resize', scheduleGalleryHeight, { passive: true });
