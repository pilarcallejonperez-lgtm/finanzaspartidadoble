/* Papeles en orden · service worker.
   RED PRIMERO para la página y los scripts (index.html, app.js, nube.js, config.js, estilos.css, manifest.json, jsqr.js):
   así un arreglo publicado llega en cuanto se abre la app. Lo guardado solo se usa sin cobertura (o si la red tarda
   más de 4 s). Iconos: lo guardado primero. Nunca toca lo que va a Supabase (otro origen) ni los datos.
   Si cambias este archivo, sube CACHE: el nuevo toma el control y la app se recarga sola una vez. */
const CACHE = 'papeles-movil-v3';
const ARCHIVOS = ['./', 'estilos.css', 'app.js', 'nube.js', 'config.js', 'manifest.json', 'jsqr.js',
  'icono.svg', 'icono-192.png', 'apple-touch-icon.png'];
const RED_PRIMERO = /^(|index\.html|app\.js|nube\.js|config\.js|estilos\.css|manifest\.json|jsqr\.js)$/;
const VIEJAS = /^papeles-movil-v[12]$/;  // versiones que no sabían recargarse solas
const BASE = new URL('./', self.location);

self.addEventListener('install', ev => {
  ev.waitUntil(caches.open(CACHE)
    .then(c => Promise.all(ARCHIVOS.map(a => fetch(new Request(a, {cache: 'reload'}))
      .then(r => { if (r.ok) return c.put(a === './' ? 'index.html' : a, r); }).catch(() => {}))))
    .then(() => self.skipWaiting()));
});
self.addEventListener('activate', ev => {
  const hecho = (async () => {
    const ks = await caches.keys();
    const habiaVieja = ks.some(k => VIEJAS.test(k));
    await Promise.all(ks.filter(k => k !== CACHE && k.startsWith('papeles-movil')).map(k => caches.delete(k)));
    await self.clients.claim();
    return habiaVieja;
  })();
  ev.waitUntil(hecho);
  // Las páginas abiertas con la versión vieja (v1/v2) no saben recargarse: las recargo yo una vez.
  // Fuera del waitUntil: la recarga pasa por este mismo service worker, que antes tiene que terminar de activarse.
  hecho.then(vieja => {
    if (vieja) self.clients.matchAll({type: 'window'}).then(cs => cs.forEach(c => { if (c.navigate) c.navigate(c.url).catch(() => {}); }));
  }).catch(() => {});
});

const espera = ms => new Promise(ok => setTimeout(() => ok('tarde'), ms));
async function redPrimero(destino, clave, nav) {
  const c = await caches.open(CACHE);
  const red = fetch(destino, {cache: 'no-cache', credentials: 'same-origin'}).then(r => {
    if (r.ok && r.type === 'basic') c.put(clave, r.clone()).catch(() => {});
    return r;
  });
  let r = await Promise.race([red.catch(() => null), espera(4000)]);
  if (r === 'tarde') r = (await c.match(clave, {ignoreSearch: true})) || await red.catch(() => null);
  if (!r || !r.ok) r = (await c.match(clave, {ignoreSearch: true})) || r;
  // Safari no acepta en una navegación una respuesta que venga de una redirección
  if (r && nav && r.redirected) r = new Response(await r.blob(), {status: r.status, headers: r.headers});
  return r || new Response('Sin conexión. Vuelve a probar en un momento.', {status: 503, headers: {'Content-Type': 'text/plain; charset=utf-8'}});
}
self.addEventListener('fetch', ev => {
  const req = ev.request, url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin || !url.pathname.startsWith(BASE.pathname)) return;
  const nombre = url.pathname.slice(BASE.pathname.length);
  if (nombre === 'sw.js') return;
  if (req.mode === 'navigate') { ev.respondWith(redPrimero(BASE.href, 'index.html', true)); return; }  // /app/ y /app/index.html son la misma página
  if (RED_PRIMERO.test(nombre)) { ev.respondWith(redPrimero(req, nombre || 'index.html', false)); return; }
  ev.respondWith(caches.open(CACHE).then(async c => (await c.match(req, {ignoreSearch: true})) || fetch(req).then(r => {
    if (r.ok && r.type === 'basic') c.put(req, r.clone()).catch(() => {});
    return r;
  })));
});
