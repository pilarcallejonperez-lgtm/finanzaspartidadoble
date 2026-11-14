/* Papeles en orden · service worker sencillo: la app se abre al momento (y sin cobertura) con lo guardado.
   Solo guarda los archivos de la propia app; nunca toca lo que va a Supabase (otro origen) ni los datos. */
const CACHE = 'papeles-movil-v2';
const ARCHIVOS = ['index.html', 'estilos.css', 'app.js', 'nube.js', 'config.js', 'manifest.json',
  'icono.svg', 'icono-192.png', 'apple-touch-icon.png'];

self.addEventListener('install', ev => {
  ev.waitUntil(caches.open(CACHE).then(c => c.addAll(ARCHIVOS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', ev => {
  ev.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
// Lo guardado primero (rápido) y, a la vez, se trae la versión nueva para la próxima vez
self.addEventListener('fetch', ev => {
  const req = ev.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin || !url.pathname.startsWith(new URL('./', self.location).pathname)) return;
  const clave = req.mode === 'navigate' ? 'index.html' : req;  // /app/ y /app/index.html son la misma página
  ev.respondWith(caches.open(CACHE).then(async c => {
    const guardado = await c.match(clave, {ignoreSearch: true});
    const red = fetch(req).then(r => { if (r.ok) c.put(clave, r.clone()); return r; }).catch(() => guardado);
    return guardado || red;
  }));
});
