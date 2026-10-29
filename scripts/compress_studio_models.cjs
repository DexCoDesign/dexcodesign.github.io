// Lossless delivery copies only: source GLBs, meshes and joint metadata stay intact.
const fs = require('fs'), path = require('path'), zlib = require('zlib'), crypto = require('crypto');
const root = path.resolve(__dirname, '..');
const catalogPath = path.join(root, 'assets/models/studio/catalog.json');
const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));
const folder = path.join(root, 'assets/models/studio/compressed');
if (process.argv.includes('--check')) {
  let checkedModels = 0;
  for (const record of catalog.records) {
    if (!record.compressed_glb) continue;
    const metadata = JSON.parse(fs.readFileSync(path.join(root, record.metadata), 'utf8'));
    const original = fs.readFileSync(path.join(root, metadata.glb));
    const delivered = fs.readFileSync(path.join(root, record.compressed_glb));
    const revision = crypto.createHash('sha256').update(delivered).digest('hex').slice(0, 16);
    if (!zlib.gunzipSync(delivered).equals(original) || delivered.length !== record.compressed_bytes || revision !== record.compressed_revision) {
      throw new Error(`Stale delivery copy: ${record.id}. Run scripts/compress_studio_models.cjs`);
    }
    checkedModels++;
  }
  console.log(JSON.stringify({checkedModels, lossless: true}));
  process.exit(0);
}
fs.mkdirSync(folder, {recursive: true});
let originalBytes = 0, deliveryBytes = 0, compressedModels = 0;
for (const record of catalog.records) {
  const metadata = JSON.parse(fs.readFileSync(path.join(root, record.metadata), 'utf8'));
  const original = fs.readFileSync(path.join(root, metadata.glb));
  const compressed = zlib.gzipSync(original, {level: 9});
  const destination = path.join(folder, `${record.id}.glb.gz`);
  originalBytes += original.length;
  if (original.length >= 128 * 1024 && compressed.length < original.length * .9) {
    if (!zlib.gunzipSync(compressed).equals(original)) throw new Error(`Round-trip mismatch: ${record.id}`);
    if (!fs.existsSync(destination) || !fs.readFileSync(destination).equals(compressed)) fs.writeFileSync(destination, compressed);
    record.compressed_glb = path.relative(root, destination).split(path.sep).join('/');
    record.compressed_bytes = compressed.length;
    record.compressed_revision = crypto.createHash('sha256').update(compressed).digest('hex').slice(0, 16);
    deliveryBytes += compressed.length;
    compressedModels++;
  } else {
    delete record.compressed_glb;
    delete record.compressed_bytes;
    delete record.compressed_revision;
    deliveryBytes += original.length;
  }
}
fs.writeFileSync(catalogPath, JSON.stringify(catalog, null, 2) + '\n');
console.log(JSON.stringify({compressedModels, originalBytes, deliveryBytes, savedPercent: 100 * (1 - deliveryBytes / originalBytes)}));
