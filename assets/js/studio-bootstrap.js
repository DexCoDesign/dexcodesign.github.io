// Keep Three.js, WebGL and model downloads out of the initial document load.
const studio = document.getElementById('hand-studio');
const viewport = document.getElementById('studio-viewport');
const category = document.getElementById('studio-category');
const select = document.getElementById('studio-model');
const poster = document.getElementById('studio-poster');
const message = document.getElementById('studio-loading-text');
const progress = document.getElementById('studio-progress');
const assetVersion = '71';
const params = new URLSearchParams(location.search);
let records = [], started = false, observer;

function preview(preferred) {
  const options = records.filter(record => record.category === category.value);
  select.replaceChildren(...options.map(record => new Option(record.name, record.id)));
  const record = options.find(record => record.id === preferred) || options[0];
  if (!record) return;
  select.value = record.id;
  showPoster(record);
}

function showPoster(record) {
  viewport.dataset.requestedModel = record.id;
  document.getElementById('studio-name').textContent = record.name;
  poster.src = `assets/images/studio/posters/${record.id}.jpg?v=${assetVersion}`;
  poster.hidden = false;
  poster.onerror = () => { poster.hidden = true; };
}

async function start() {
  if (started) return;
  started = true;
  observer?.disconnect();
  viewport.dataset.studioBoot = 'loading';
  progress.hidden = false;
  message.textContent = 'Starting interactive preview…';
  studio.removeEventListener('pointerdown', start);
  studio.removeEventListener('keydown', start);
  try {
    await import('./hand-studio.js?v=72');
    category.removeEventListener('change', changeCategory);
    select.removeEventListener('change', changeModel);
    viewport.dataset.studioBoot = 'started';
  } catch (error) {
    message.textContent = 'Preview could not start. Reload this page to retry.';
    console.error(error);
  }
}

function changeCategory() { preview(); start(); }
function changeModel() {
  const record = records.find(record => record.id === select.value);
  if (record) showPoster(record);
  start();
}

if (studio && location.protocol !== 'file:') {
  // The small catalog and a single poster are enough for an immediate preview.
  // Reuse this promise in the interactive module instead of fetching it twice.
  viewport.studioCatalog = fetch('assets/models/studio/catalog.json?v=72')
    .then(response => {
      if (!response.ok) throw new Error('Catalog unavailable');
      return response.json();
    });
  viewport.studioCatalog.then(data => {
    records = data.records;
    if (started) {
      const requested = records.find(record => record.id === (viewport.dataset.requestedModel || params.get('model')))
        || records.find(record => record.category === category.value);
      if (requested) showPoster(requested);
      return;
    }
    const requested = records.find(record => record.id === params.get('model'));
    const collection = requested?.category || params.get('collection') || 'manipulator';
    if ([...category.options].some(option => option.value === collection)) category.value = collection;
    preview(requested?.id || (category.value === 'manipulator' ? 'dexmate_vega' : undefined));
  }).catch(error => { if (!started) message.textContent = error.message; });
  category.addEventListener('change', changeCategory);
  select.addEventListener('change', changeModel);
  studio.addEventListener('pointerdown', start, { passive: true });
  studio.addEventListener('keydown', start);
  if ('IntersectionObserver' in window) {
    observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) start();
    });
    observer.observe(viewport);
  } else start();
}
