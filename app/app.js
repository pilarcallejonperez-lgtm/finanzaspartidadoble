/* Papeles en orden · app del móvil.
   Lee el resumen cifrado que sube el ordenador y manda papeles cifrados a su buzón.
   La llave llega en el código QR (#k=…, el fragmento no viaja nunca al servidor web) y se guarda solo en este móvil.
   Flujo para conectar (igual para todas): abrir finanzaspartidadoble.es/app → ponerla en la pantalla de inicio →
   abrir el icono → «Escanear el código» → apuntar al QR del ordenador. Plan B: pegar el enlace. */
'use strict';
const VERSION_APP = '2026-11-14.3';  // súbela al publicar un cambio (sale en la pantalla de soporte)
const CFG = window.PAPELES_MOVIL || {};
const $ = id => document.getElementById(id);
const K = {llave: 'pp-llave', cache: 'pp-resumen', visto: 'pp-recibido', enviados: 'pp-enviados', vista: 'pp-vista',
  usadas: 'pp-k-usadas', recibidoEn: 'pp-recibido-en', enNavegador: 'pp-en-navegador'};
const L = {
  get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* modo privado: solo en memoria */ } },
  del: k => { try { localStorage.removeItem(k); } catch (e) { /* nada */ } },
};
const MAX_MB = 25;
const S = {llave: null, carpeta: null, al: null, datos: null, vista: 'inicio', enviando: false, recargar: false};

/* ------------------------------------------------ dónde estamos: iPhone o Android, Safari o Chrome, navegador o app del icono */
const ENT = (() => {
  const ua = navigator.userAgent || '';
  const ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const ipad = /iPad/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const android = /Android/i.test(ua);
  const enApp = window.navigator.standalone === true || matchMedia('(display-mode: standalone)').matches || matchMedia('(display-mode: fullscreen)').matches;
  let navegador = 'otro';
  if (ios) navegador = /CriOS/.test(ua) ? 'Chrome' : /FxiOS/.test(ua) ? 'Firefox' : /EdgiOS/.test(ua) ? 'Edge'
    : /Instagram|FBAN|FBAV|FB_IAB|GSA\/|Line\/|Twitter|WhatsApp|LinkedInApp|Snapchat|TikTok|musical_ly/.test(ua) ? 'dentro' : /Safari\//.test(ua) ? 'Safari' : 'dentro';
  else navegador = /SamsungBrowser/.test(ua) ? 'Samsung' : /EdgA|Edg\//.test(ua) ? 'Edge' : /Firefox/.test(ua) ? 'Firefox' : /Chrome/.test(ua) ? 'Chrome' : /Safari/.test(ua) ? 'Safari' : 'otro';
  const iosVer = ios ? ((ua.match(/OS (\d+)[._](\d+)/) || []).slice(1, 3).join('.') || '') : '';
  const safariVer = ios ? Number((ua.match(/Version\/(\d+)/) || [])[1] || 0) : 0;
  return {ios, ipad, android, movil: ios || android || /Mobi/i.test(ua), enApp, navegador, iosVer, safariVer};
})();

const eur = n => (Number(n) || 0).toLocaleString('es-ES', {style: 'currency', currency: 'EUR'});
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fCorta = s => s ? new Date(String(s).slice(0, 10) + 'T12:00').toLocaleDateString('es-ES', {day: 'numeric', month: 'short', year: 'numeric'}) : '';
const horaTxt = s => {
  const d = new Date(s); if (isNaN(d)) return '';
  const h = d.toLocaleTimeString('es-ES', {hour: '2-digit', minute: '2-digit'}), hoy = new Date(), ayer = new Date(Date.now() - 864e5);
  if (d.toDateString() === hoy.toDateString()) return 'hoy a las ' + h;
  if (d.toDateString() === ayer.toDateString()) return 'ayer a las ' + h;
  return d.toLocaleDateString('es-ES', {day: 'numeric', month: 'short'}) + ' a las ' + h;
};
function avisar(id, texto, error) { const el = $(id); if (!el) return; el.textContent = texto; el.classList.toggle('error', !!error); }
function linea(t) { $('estadoLinea').textContent = t; }

/* ------------------------------------------------ navegación */
const SIN_MENU = ['conectar', 'instalar', 'diag'];
function ir(v) {
  if (v !== 'conectar') cerrarCamara();
  if (v !== 'diag') S.vista = v;
  document.querySelectorAll('.vista').forEach(s => { s.hidden = s.id !== 'v-' + v; });
  document.querySelectorAll('nav.menu button').forEach(b => b.setAttribute('aria-current', b.dataset.ir === v));
  $('menu').hidden = SIN_MENU.includes(v) || !S.llave;
  $('flecha').hidden = v !== 'instalar' || !$('flecha').dataset.donde;
  pintarAvisoNavegador(v);
  window.scrollTo(0, 0);
  if (!SIN_MENU.includes(v)) L.set(K.vista, v);
  if (v === 'mandar') pintarEnviados();
  if (v === 'diag') pintarDiag();
}
document.querySelectorAll('[data-ir]').forEach(b => { b.onclick = () => ir(b.dataset.ir); });

/* ------------------------------------------------ la llave */
const huella = async llave => (await Nube.carpeta(llave)).slice(0, 16);
const usadas = () => { try { return JSON.parse(L.get(K.usadas) || '[]'); } catch (e) { return []; } };
async function leerFragmento() {
  const m = location.hash.match(/k=([A-Za-z0-9_-]{43})/);
  // En el navegador NO se quita: así «Añadir a pantalla de inicio» guarda el enlace con la llave
  // (en iPhone la app del icono no comparte memoria con Safari/Chrome). Dentro de la app del icono sí se quita.
  if (location.hash && ENT.enApp) history.replaceState(null, '', location.pathname + location.search);
  if (!m) return null;
  // Un enlace con llave vale una sola vez en cada sitio: el icono se abre SIEMPRE con el enlace con el que se creó,
  // y si luego se conecta otro código (o el ordenador desconecta este móvil) la llave vieja no debe volver.
  if (usadas().includes(await huella(m[1]))) return null;
  return m[1];
}
// En el navegador del móvil, la barra de direcciones lleva siempre la llave: si la ponen en la pantalla de inicio
// desde aquí, el icono nace ya conectado.
function marcarDireccion(llave) {
  if (ENT.enApp || !ENT.movil) return;
  const quiere = llave ? '#k=' + llave : '';
  if (location.hash !== quiere) history.replaceState(null, '', location.pathname + location.search + quiere);
}
async function usarLlave(llave) {
  if (llave !== L.get(K.llave)) { [K.cache, K.visto, K.enviados, K.recibidoEn].forEach(L.del); S.datos = null; }
  S.llave = llave; L.set(K.llave, llave);
  const h = await huella(llave), u = usadas();
  if (!u.includes(h)) L.set(K.usadas, JSON.stringify([h, ...u].slice(0, 20)));
  S.carpeta = await Nube.carpeta(llave);
  S.al = Nube.almacen({url: CFG.supabaseUrl, anon: CFG.anonKey, bucket: CFG.bucket});
  marcarDireccion(llave);
}
function olvidar(motivo) {
  [K.llave, K.cache, K.visto, K.enviados, K.recibidoEn].forEach(L.del);
  S.llave = S.carpeta = S.al = S.datos = null;
  marcarDireccion(null);
  pantallaConectar(motivo);
}
function pantallaConectar(motivo) {
  $('conAviso').hidden = !motivo; $('conAviso').textContent = motivo || '';
  $('conTitulo').textContent = motivo ? 'Vuelve a escanear el código' : 'Conecta tu móvil';
  avisoCamara('');
  $('irInstalar').hidden = !(ENT.movil && !ENT.enApp);
  linea('Finanzas Partida Doble');
  ir('conectar');
}
async function conectarCon(llave) {
  await usarLlave(llave);
  $('conAviso').hidden = true; $('planB').open = false;
  ir('inicio'); pintarSinDatos(); pintarEnviados();
  avisar('msgConectada', '✓ Conectada con tu ordenador.');
  await actualizar();
}
$('formCodigo').onsubmit = async e => {
  e.preventDefault();
  const llave = Nube.llaveDeTexto($('codigo').value);
  if (!llave) return avisar('msgCodigo', 'Ese enlace no es válido. Cópialo entero desde tu ordenador.', true);
  $('codigo').value = ''; avisar('msgCodigo', '');
  await conectarCon(llave);
};
$('btnOlvidar').onclick = () => {
  if (confirm('¿Desconecto este móvil? Para volver a ver tus papeles tendrás que escanear el código otra vez.')) olvidar('');
};

/* ------------------------------------------------ ponerla en la pantalla de inicio */
const IC_COMPARTIR = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.6 7.6 7l1.4 1.4 2-2V15h2V6.4l2 2L16.4 7z"/><path d="M6 10h3v2H7v8h10v-8h-2v-2h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V11a1 1 0 0 1 1-1z"/></svg>';
const IC_ANADIR = '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h12a3 3 0 0 1 3 3v12a3 3 0 0 1-3 3H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3zm0 2a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1zm5 3h2v3h3v2h-3v3h-2v-3H8v-2h3z"/></svg>';
let avisoInstalar = null;  // Android/Chrome: el aviso de instalar que da el propio navegador
window.addEventListener('beforeinstallprompt', ev => { ev.preventDefault(); avisoInstalar = ev; if (!$('v-instalar').hidden) pintarInstalar(); });
function pasosInstalar() {
  const n = ENT.navegador;
  if (ENT.ios && n === 'dentro') return {donde: '', pasos: [
    'Estás dentro de otra app. Toca <b>···</b> o el icono de la brújula y elige <b>Abrir en Safari</b>.',
    `En Safari: <b>Compartir</b> ${IC_COMPARTIR} → <b>Añadir a pantalla de inicio</b>.`]};
  if (ENT.ios && n === 'Safari' && ENT.ipad) return {donde: 'arriba', pasos: [
    `Toca <b>Compartir</b> ${IC_COMPARTIR}, arriba a la derecha.`,
    `Toca <b>Añadir a pantalla de inicio</b> ${IC_ANADIR}.`, 'Toca <b>Añadir</b>.']};
  if (ENT.ios && n === 'Safari' && ENT.safariVer >= 26) return {donde: 'abajo-dcha', pasos: [
    'Toca <b>···</b>, abajo a la derecha.', `Toca <b>Compartir</b> ${IC_COMPARTIR}.`,
    `Baja y toca <b>Añadir a pantalla de inicio</b> ${IC_ANADIR}.`, 'Toca <b>Añadir</b>.']};
  if (ENT.ios && n === 'Safari') return {donde: 'abajo', pasos: [
    `Toca <b>Compartir</b> ${IC_COMPARTIR}, abajo en el centro.`,
    `Baja y toca <b>Añadir a pantalla de inicio</b> ${IC_ANADIR}.`, 'Toca <b>Añadir</b>, arriba a la derecha.']};
  if (ENT.ios) return {donde: 'arriba', pasos: [
    `Toca <b>Compartir</b> ${IC_COMPARTIR}, arriba a la derecha, junto a la dirección.`,
    `Toca <b>Añadir a pantalla de inicio</b> ${IC_ANADIR} (si no sale, toca <b>Más</b>).`, 'Toca <b>Añadir</b>.']};
  if (ENT.android) return {donde: 'arriba', pasos: [
    'Toca <b>⋮</b>, arriba a la derecha.', 'Toca <b>Añadir a pantalla de inicio</b> o <b>Instalar aplicación</b>.', 'Toca <b>Añadir</b> o <b>Instalar</b>.']};
  return {donde: '', pasos: [`En el menú del navegador, busca <b>Añadir a pantalla de inicio</b> ${IC_ANADIR}.`]};
}
function pintarInstalar() {
  const p = pasosInstalar();
  $('pasosInstalar').innerHTML = p.pasos.map(t => `<li>${t}</li>`).join('');
  $('btnInstalarAndroid').hidden = !avisoInstalar;
  const f = $('flecha'); f.dataset.donde = p.donde; f.className = 'flecha ' + p.donde;
  $('flechaTxt').textContent = p.donde === 'arriba' ? 'Compartir está aquí arriba' : p.donde === 'abajo-dcha' ? 'Los ··· están aquí abajo' : 'Compartir está aquí abajo';
  if (ENT.android) $('flechaTxt').textContent = 'El menú ⋮ está aquí arriba';
  $('instalarConectada').hidden = !S.llave;
  $('instalarDespues').hidden = !!S.llave;
  $('btnSinInstalar').textContent = S.llave ? 'Volver a mis cuentas' : 'Prefiero usarla aquí, en el navegador';
}
function pantallaInstalar() { pintarInstalar(); linea('Finanzas Partida Doble'); ir('instalar'); }
$('btnSinInstalar').onclick = () => {
  if (S.llave) return ir('inicio');
  L.set(K.enNavegador, '1');
  pantallaConectar('');
};
$('btnVerInstalar').onclick = () => pantallaInstalar();
$('btnVerInstalar2').onclick = () => pantallaInstalar();
$('btnInstalarAndroid').onclick = async () => {
  if (!avisoInstalar) return;
  avisoInstalar.prompt();
  try { await avisoInstalar.userChoice; } catch (e) { /* nada */ }
  avisoInstalar = null; pintarInstalar();
};
// «Ya estás conectada en el navegador»: solo en el navegador del móvil, con llave
function pintarAvisoNavegador(v) { $('avisoNavegador').hidden = !(S.llave && ENT.movil && !ENT.enApp && !SIN_MENU.includes(v || S.vista)); }

/* ------------------------------------------------ escanear el código con la cámara (dentro de la app) */
// Lector: jsQR (Apache-2.0), copiado en jsqr.js dentro de la propia app. Se carga al tocar «Escanear el código».
const ESC = {stream: null, timer: 0, lienzo: null, ctx: null, vuelta: 0, cargando: null, empezo: 0, ultimoMalo: '', pista: false};
function cargarLector() {
  if (window.jsQR) return Promise.resolve();
  if (!ESC.cargando) ESC.cargando = new Promise((ok, mal) => {
    const s = document.createElement('script');
    s.src = 'jsqr.js'; s.onload = () => (window.jsQR ? ok() : mal(new Error('lector')));
    s.onerror = () => { ESC.cargando = null; s.remove(); mal(new Error('lector')); };
    document.head.appendChild(s);
  });
  return ESC.cargando;
}
// Lee un QR de una imagen (ImageData). Devuelve el texto o null.
function leerQR(img, invertir) {
  const r = window.jsQR(img.data, img.width, img.height, {inversionAttempts: invertir ? 'attemptBoth' : 'dontInvert'});
  return r && r.data ? r.data : null;
}
function avisoCamara(t, error) {
  const el = $('msgCamara'); el.hidden = !t; el.textContent = t || ''; el.classList.toggle('error', !!error);
}
function botonEscanear(ocupado) {
  const b = $('btnEscanear'); b.disabled = !!ocupado;
  $('btnEscanearTxt').textContent = ocupado ? 'Abriendo la cámara…' : 'Escanear el código';
}
function sinCamara(texto) {
  cerrarCamara();
  avisoCamara(texto, true);
  $('planB').open = true;
}
async function pedirCamara() {
  const md = navigator.mediaDevices;
  try {
    return await md.getUserMedia({audio: false, video: {facingMode: {ideal: 'environment'}, width: {ideal: 1280}, height: {ideal: 720}}});
  } catch (e) {
    if (['OverconstrainedError', 'ConstraintNotSatisfiedError', 'TypeError'].includes(e.name)) return md.getUserMedia({audio: false, video: true});
    throw e;
  }
}
async function abrirCamara() {
  if (ESC.stream) return;
  avisoCamara('');
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia)
    return sinCamara('Aquí no puedo usar la cámara. Pega el enlace de tu ordenador aquí abajo.');
  botonEscanear(true);
  let stream;
  try {
    stream = await pedirCamara();
  } catch (e) {
    botonEscanear(false);
    if (e.name === 'NotAllowedError' || e.name === 'SecurityError' || e.name === 'PermissionDeniedError')
      return sinCamara(ENT.ios
        ? 'No tengo permiso para usar la cámara. Vuelve a tocar «Escanear el código» y elige «Permitir». Si no sale, pega el enlace aquí abajo.'
        : 'No tengo permiso para usar la cámara. Permítelo en el candado de la barra de arriba o pega el enlace aquí abajo.');
    if (e.name === 'NotReadableError' || e.name === 'TrackStartError' || e.name === 'AbortError')
      return sinCamara('La cámara está ocupada con otra app. Ciérrala y vuelve a probar, o pega el enlace aquí abajo.');
    return sinCamara('No encuentro la cámara de este móvil. Pega el enlace de tu ordenador aquí abajo.');
  }
  try { await cargarLector(); } catch (e) {
    stream.getTracks().forEach(t => t.stop()); botonEscanear(false);
    return sinCamara('No he podido preparar el lector. Mira si tienes internet y vuelve a probar, o pega el enlace aquí abajo.');
  }
  if ($('v-conectar').hidden || document.visibilityState === 'hidden') { stream.getTracks().forEach(t => t.stop()); botonEscanear(false); return; }
  ESC.stream = stream; ESC.empezo = Date.now(); ESC.ultimoMalo = ''; ESC.pista = false;
  const v = $('video');
  v.setAttribute('playsinline', ''); v.setAttribute('muted', ''); v.muted = true; v.setAttribute('autoplay', '');
  v.srcObject = stream;
  $('escaner').hidden = false; $('btnEscanear').hidden = true; botonEscanear(false);
  avisar('msgEscaner', 'Apunta al código de tu ordenador');
  try { await v.play(); } catch (e) { /* iOS a veces ya lo ha empezado solo */ }
  $('escaner').scrollIntoView({block: 'center', behavior: 'smooth'});
  clearTimeout(ESC.timer); ESC.timer = setTimeout(fotograma, 150);
}
function cerrarCamara() {
  clearTimeout(ESC.timer);
  if (ESC.stream) { ESC.stream.getTracks().forEach(t => t.stop()); ESC.stream = null; }
  const v = $('video'); if (v) { try { v.pause(); } catch (e) { /* nada */ } v.srcObject = null; }
  if ($('escaner')) { $('escaner').hidden = true; $('btnEscanear').hidden = false; botonEscanear(false); }
  if (S.recargar && !S.enviando) recargarUnaVez();
}
// Cada fotograma se mira de una manera distinta, por turnos: la imagen entera, el centro ampliado (código lejos)
// y la imagen entera más pequeña (al reducir se suaviza el grano de la cámara con poca luz).
const VARIANTES = [{centro: false, max: 720}, {centro: true, max: 720}, {centro: false, max: 420}];
function leerVariante(fuente, ancho, alto, n) {
  if (!ESC.lienzo) { ESC.lienzo = document.createElement('canvas'); ESC.ctx = ESC.lienzo.getContext('2d', {willReadFrequently: true}); }
  const o = VARIANTES[n % VARIANTES.length];
  let sx = 0, sy = 0, sw = ancho, sh = alto;
  if (o.centro) { const lado = Math.min(ancho, alto) * 0.62; sx = (ancho - lado) / 2; sy = (alto - lado) / 2; sw = sh = lado; }
  const escala = Math.min(1, o.max / Math.max(sw, sh)), w = Math.max(1, Math.round(sw * escala)), h = Math.max(1, Math.round(sh * escala));
  if (ESC.lienzo.width !== w || ESC.lienzo.height !== h) { ESC.lienzo.width = w; ESC.lienzo.height = h; }
  ESC.ctx.imageSmoothingEnabled = true; ESC.ctx.imageSmoothingQuality = 'high';
  ESC.ctx.drawImage(fuente, sx, sy, sw, sh, 0, 0, w, h);
  return leerQR(ESC.ctx.getImageData(0, 0, w, h), n % 7 === 6);  // de vez en cuando, también en negativo
}
// Lo mismo que hace la cámara, de una vez, sobre una imagen o un lienzo (para las pruebas)
function leerImagen(fuente) {
  const w = fuente.videoWidth || fuente.naturalWidth || fuente.width, h = fuente.videoHeight || fuente.naturalHeight || fuente.height;
  for (let n = 0; n < 7; n++) { const t = leerVariante(fuente, w, h, n); if (t) return t; }
  return null;
}
function fotograma() {
  const v = $('video');
  if (!ESC.stream) return;
  if (v.readyState >= 2 && v.videoWidth && v.videoHeight) {
    let texto = null;
    try { texto = leerVariante(v, v.videoWidth, v.videoHeight, ESC.vuelta++); } catch (e) { /* fotograma aún no listo */ }
    if (texto && alLeer(texto)) return;
    if (!ESC.pista && Date.now() - ESC.empezo > 20000) {
      ESC.pista = true; avisar('msgEscaner', 'Acércate un poco: que el código se vea entero, sin brillos.');
    }
  }
  ESC.timer = setTimeout(fotograma, 120);
}
function alLeer(texto) {
  const llave = Nube.llaveDeTexto(texto);
  if (!llave) {
    if (ESC.ultimoMalo !== texto) { ESC.ultimoMalo = texto; avisar('msgEscaner', 'Ese código no es el de tu ordenador. Busca el de Ajustes › Conectar mi móvil.', true); }
    return false;
  }
  cerrarCamara();
  try { if (navigator.vibrate) navigator.vibrate(60); } catch (e) { /* nada */ }
  conectarCon(llave).catch(e => { console.error(e); avisoCamara('No he podido conectar. Vuelve a probar.', true); });
  return true;
}
$('btnEscanear').onclick = () => { abrirCamara().catch(e => { console.error(e); sinCamara('No he podido abrir la cámara. Pega el enlace aquí abajo.'); }); };
$('btnCerrarCam').onclick = () => cerrarCamara();

/* ------------------------------------------------ el resumen */
async function actualizar() {
  if (!S.al) return;
  linea('Poniéndome al día…');
  try {
    const bytes = await S.al.bajar(S.carpeta + '/resumen.enc');
    const datos = await Nube.descifrarJSON(S.llave, bytes, 'resumen');
    L.set(K.cache, Nube.aB64(bytes)); L.set(K.visto, '1'); L.set(K.recibidoEn, new Date().toISOString());
    pintar(datos);
  } catch (e) {
    if (e.noExiste && L.get(K.visto)) return olvidar('Tu ordenador ha desconectado este móvil. Si quieres volver a verlo, escanea el código otra vez.');
    if (e.name === 'OperationError') return olvidar('Este código ya no vale. Escanea el que sale ahora en tu ordenador.');
    if (e.noExiste) { pintarSinDatos(); linea('Esperando a tu ordenador'); }
    else linea(S.datos ? 'Sin conexión · lo último del ' + horaTxt(S.datos.generado) : 'Sin conexión ahora mismo');
  }
  comprobarEnviados();
}
function pintarSinDatos() { if (!S.datos) { $('sinDatos').hidden = false; $('conDatos').hidden = true; } }

function filaVenc(v) {
  const chip = v.dias < 0 ? '<span class="chip mal">Ya venció</span>' : v.avisar ? `<span class="chip aviso">En ${v.dias} días</span>` : `<span class="chip ok">${fCorta(v.vencimiento)}</span>`;
  return `<div class="fila"><div class="txt"><b>${esc(v.texto)}</b><small>${esc(v.emisor || '')} · ${esc(v.tipo_txt)}</small></div>${chip}</div>`;
}
const filaFijo = f => `<div class="fila"><div class="txt"><b>${esc(f.nombre)}</b><small>${esc(f.periodo_txt)} · hacia el ${fCorta(f.proxima)}</small></div><span class="imp g">≈ ${eur(f.importe_medio)}</span></div>`;

function pintar(d) {
  S.datos = d;
  linea('Al día: ' + horaTxt(d.generado));
  $('sinDatos').hidden = true; $('conDatos').hidden = false;
  // Inicio
  $('mesTxt').textContent = d.mes_txt;
  $('gastoMes').textContent = eur(d.gasto);
  $('gastoAnt').textContent = d.hay_anterior ? eur(d.gasto_anterior) : 'Sin datos';
  $('gastoPas').textContent = d.hay_anio_pasado ? eur(d.gasto_anio_pasado) : 'Sin datos';
  const semana = d.disponible_semana != null;
  $('bloqueSemana').hidden = !semana;
  if (semana) {
    $('semanaTxt').textContent = `Disponible esta semana (hasta el ${d.semana_hasta})`;
    $('dispSemana').textContent = eur(d.disponible_semana);
    $('dispMes').textContent = 'En todo el mes: ' + eur(d.disponible_mes);
  }
  const avisan = d.vencimientos.filter(v => v.avisar);
  const avisos = avisan.slice(0, 3).map(v => `<div class="alerta">${esc(v.texto)}</div>`);
  d.subidas.slice(0, 2).forEach(s => avisos.push(`<div class="alerta">↑ ${esc(s)}</div>`));
  const p = d.pendientes || {};
  if (p.en_duda) avisos.push(`<div class="alerta verde">${p.en_duda === 1 ? 'Un movimiento del banco está' : p.en_duda + ' movimientos del banco están'} en duda: dímelo en tu ordenador y lo recuerdo.</div>`);
  $('avisosInicio').innerHTML = avisos.join('');
  const g = $('globoAvisos'); g.hidden = !avisan.length; g.textContent = avisan.length;
  const max = Math.max(1, ...d.categorias.map(c => Math.max(c.actual, c.anterior)));
  $('grafCat').innerHTML = d.categorias.length ? d.categorias.map(c => {
    const pct = c.pct_anterior == null ? '' : ` · ${c.pct_anterior > 0 ? '+' : ''}${c.pct_anterior} %`;
    return `<div class="cat"><div class="top"><span>${esc(c.nombre)}</span><b class="imp g">${eur(c.actual)}</b></div>
      <div class="barra" role="img" aria-label="${esc(c.nombre)}: ${eur(c.actual)}, mes anterior ${eur(c.anterior)}"><i class="${c.sube ? 'sube' : ''}" style="width:${(c.actual / max * 100).toFixed(1)}%"></i>${c.anterior ? `<em style="left:calc(${(c.anterior / max * 100).toFixed(1)}% - 1px)"></em>` : ''}</div>
      <small>Mes anterior ${eur(c.anterior)}${pct}</small></div>`;
  }).join('') : '<p class="vacio">Aún no hay gastos este mes.</p>';
  $('proxCargos').innerHTML = d.proximos_cargos.length ? d.proximos_cargos.map(filaFijo).join('') : '<p class="vacio">Sin recibos previstos en los próximos 30 días.</p>';
  // Avisos
  $('notaDias').textContent = `Te aviso ${d.dias_aviso} días antes de que venzan.`;
  $('listaVenc').innerHTML = d.vencimientos.length ? d.vencimientos.map(filaVenc).join('') : '<p class="vacio">Nada vence pronto. Todo en orden.</p>';
  $('listaFijos').innerHTML = d.fijos.length ? d.fijos.map(filaFijo).join('') + `<div class="fila"><div class="txt"><b>En total, al mes</b></div><span class="imp g">${eur(d.total_fijos_mes)}</span></div>` : '<p class="vacio">Con unos meses de recibos los detecto solos.</p>';
  $('listaSus').innerHTML = d.suscripciones.length ? d.suscripciones.map(filaFijo).join('') + `<p class="alerta verde">Tus suscripciones suman ${eur(d.total_suscripciones_mes)} al mes, ${eur(d.total_suscripciones_anio)} al año. ¿Las usas todas?</p>` : '<p class="vacio">No he visto suscripciones que se repitan.</p>';
  pintarPapeles();
}
function pintarPapeles() {
  if (!S.datos) return;
  const b = $('buscar').value.trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const plano = s => String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  const lista = S.datos.papeles.filter(p => !b || plano([p.concepto, p.emisor, p.categoria_txt, p.tipo_txt].join(' ')).includes(b));
  $('listaPapeles').innerHTML = lista.length ? lista.map(p => `<div class="fila"><div class="txt"><b>${esc(p.concepto || p.tipo_txt)}</b>
      <small>${fCorta(p.fecha)} · ${esc(p.emisor || 'Sin emisor')} · ${esc(p.categoria_txt)}${p.vencimiento ? ' · vence ' + fCorta(p.vencimiento) : ''}</small></div>
      ${p.importe != null ? `<span class="imp g">${eur(p.importe)}</span>` : `<span class="chip neutro">${esc(p.tipo_txt)}</span>`}</div>`).join('')
    : `<p class="vacio">${b ? 'No encuentro nada con esa palabra.' : 'Aún no hay papeles.'}</p>`;
}
$('buscar').oninput = pintarPapeles;

/* ------------------------------------------------ mandar un papel */
const enviados = () => { try { return JSON.parse(L.get(K.enviados) || '[]'); } catch (e) { return []; } };
const guardarEnviados = l => L.set(K.enviados, JSON.stringify(l.slice(0, 30)));
const nuevoId = () => {
  if (crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16)); b[6] = (b[6] & 15) | 64; b[8] = (b[8] & 63) | 128;
  const h = [...b].map(x => x.toString(16).padStart(2, '0')).join('');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
};
async function mandar(f) {
  if (f.size > MAX_MB * 1024 * 1024) { avisar('msgMandar', `«${f.name}» es demasiado grande (más de ${MAX_MB} MB).`, true); return false; }
  const nombre = f.name || (f.type === 'application/pdf' ? 'papel.pdf' : 'foto.jpg');
  const ficha = {nombre, tipo: f.type || '', tam: f.size, enviado: new Date().toISOString()};
  const id = nuevoId();
  const bytes = await Nube.cifrar(S.llave, Nube.empaquetar(ficha, new Uint8Array(await f.arrayBuffer())), 'buzon');
  await S.al.subir(`${S.carpeta}/buzon/${id}.enc`, bytes, false);
  const l = enviados(); l.unshift({id, nombre, cuando: ficha.enviado, recogido: false}); guardarEnviados(l);
  return true;
}
$('archivo').onchange = async () => {
  const lista = [...$('archivo').files]; $('archivo').value = '';
  if (!lista.length || !S.al) return;
  ir('mandar');
  let bien = 0;
  S.enviando = true;
  try {
    for (const [i, f] of lista.entries()) {
      avisar('msgMandar', lista.length > 1 ? `Enviando ${i + 1} de ${lista.length}…` : 'Enviando…');
      try { if (await mandar(f)) bien++; }
      catch (e) { avisar('msgMandar', 'No he podido enviarlo. Mira si tienes conexión y vuelve a probar.', true); pintarEnviados(); return; }
    }
    if (bien) avisar('msgMandar', `✓ ${bien === 1 ? 'Enviado' : bien + ' enviados'}. Tu ordenador ${bien === 1 ? 'lo' : 'los'} ordenará en cuanto esté encendido.`);
    pintarEnviados(); comprobarEnviados();
  } finally {
    S.enviando = false;
    if (S.recargar && !ESC.stream) setTimeout(recargarUnaVez, 2500);
  }
};
function pintarEnviados() {
  const l = enviados();
  $('tarjetaEnviados').hidden = !l.length;
  $('listaEnviados').innerHTML = l.map(e => `<div class="fila enviado"><div class="txt"><b>${esc(e.nombre)}</b><small>${horaTxt(e.cuando)}</small></div>
    ${e.recogido ? '<span class="chip ok estado">✓ En tu ordenador</span>' : '<span class="chip aviso estado">Esperando</span>'}</div>`).join('');
  const espera = l.filter(e => !e.recogido).length;
  $('esperando').hidden = !espera;
  $('esperando').textContent = espera ? `${espera === 1 ? 'Un papel espera' : espera + ' papeles esperan'} a que abras la aplicación en tu ordenador.` : '';
}
// ¿Lo ha recogido ya el ordenador? (si ya no está en el buzón de internet, sí)
async function comprobarEnviados() {
  const l = enviados();
  if (!S.al || !l.some(e => !e.recogido)) return pintarEnviados();
  try {
    const hay = new Set((await S.al.listar(S.carpeta + '/buzon')).map(o => o.name));
    l.forEach(e => { if (!hay.has(e.id + '.enc')) e.recogido = true; });
    guardarEnviados(l);
  } catch (e) { /* sin conexión: se mira la próxima vez */ }
  pintarEnviados();
}

/* ------------------------------------------------ pantalla de soporte (toca 5 veces el logo) */
const TOQUES = {n: 0, t: 0};
$('logo').addEventListener('click', () => {
  const ahora = Date.now();
  TOQUES.n = ahora - TOQUES.t < 1500 ? TOQUES.n + 1 : 1; TOQUES.t = ahora;
  if (TOQUES.n >= 5) { TOQUES.n = 0; ir('diag'); }
});
async function pintarDiag() {
  const sistema = ENT.ios ? (ENT.ipad ? 'iPad' : 'iPhone') + (ENT.iosVer ? ' · iOS ' + ENT.iosVer : '') : ENT.android ? 'Android' : 'Ordenador';
  const nav = {Safari: 'Safari', Chrome: 'Chrome', Firefox: 'Firefox', Edge: 'Edge', Samsung: 'Samsung Internet', dentro: 'dentro de otra app'}[ENT.navegador] || 'otro navegador';
  let cache = 'no';
  try { const ks = (await caches.keys()).filter(k => k.startsWith('papeles-movil')); cache = ks.join(', ') || 'no'; } catch (e) { /* sin caches */ }
  const filas = [
    ['Versión de la app', VERSION_APP],
    ['Modo', ENT.enApp ? 'App de la pantalla de inicio' : 'Navegador (' + nav + ')'],
    ['Móvil', sistema],
    ['Llave guardada', S.llave ? 'Sí' : 'No'],
    ['Último resumen', S.datos ? 'hecho ' + horaTxt(S.datos.generado) : 'ninguno todavía'],
    ['Recibido en el móvil', L.get(K.recibidoEn) ? horaTxt(L.get(K.recibidoEn)) : '—'],
    ['Internet', navigator.onLine ? 'Sí' : 'No'],
    ['Cámara', navigator.mediaDevices && navigator.mediaDevices.getUserMedia ? 'Se puede usar' : 'No disponible'],
    ['Actualizaciones', navigator.serviceWorker && navigator.serviceWorker.controller ? 'Activas · ' + cache : 'No activas · ' + cache],
  ];
  $('diagLista').innerHTML = filas.map(([a, b]) => `<div><dt>${esc(a)}</dt><dd>${esc(b)}</dd></div>`).join('');
}
$('btnDiagCerrar').onclick = () => {
  if (S.llave) return ir(S.vista && !SIN_MENU.includes(S.vista) ? S.vista : 'inicio');
  if (S.vista === 'instalar') return pantallaInstalar();
  pantallaConectar('');
};
$('btnDiagRecargar').onclick = async () => {
  try { for (const k of await caches.keys()) if (k.startsWith('papeles-movil')) await caches.delete(k); } catch (e) { /* nada */ }
  try { const r = await navigator.serviceWorker.getRegistration(); if (r) await r.update(); } catch (e) { /* nada */ }
  location.reload();
};

/* ------------------------------------------------ arranque */
async function arrancar() {
  const delQR = await leerFragmento(), guardada = L.get(K.llave);
  const llave = delQR || (Nube.llaveValida(guardada) ? guardada : null);
  if (!CFG.supabaseUrl || !CFG.anonKey) { if (delQR) L.set(K.llave, delQR); pantallaConectar('La aplicación aún no está activada. Avísanos, por favor.'); return; }
  if (!llave) {
    // En el navegador del móvil, lo primero es ponerla en la pantalla de inicio; en la app del icono, escanear.
    if (ENT.movil && !ENT.enApp && !L.get(K.enNavegador)) return pantallaInstalar();
    return olvidar('');
  }
  await usarLlave(llave);
  const vista = delQR ? 'inicio' : (L.get(K.vista) || 'inicio');
  ir(document.getElementById('v-' + vista) && !SIN_MENU.includes(vista) ? vista : 'inicio');
  const cache = L.get(K.cache);  // lo último que llegó, para que se vea al momento
  if (cache) { try { pintar(await Nube.descifrarJSON(S.llave, Nube.deB64(cache), 'resumen')); } catch (e) { L.del(K.cache); } }
  else pintarSinDatos();
  pintarEnviados();
  await actualizar();
}
window.addEventListener('hashchange', () => { if (/k=/.test(location.hash)) arrancar(); });
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') { actualizar(); buscarVersionNueva(); }
  else cerrarCamara();  // al salir de la app, la cámara se apaga
});
setInterval(() => { if (document.visibilityState === 'visible') actualizar(); }, 2 * 60 * 1000);
arrancar().catch(e => { linea('No he podido arrancar'); console.error(e); });

/* ------------------------------------------------ versiones nuevas: llegan solas */
// El service worker trae siempre de la red la página y los scripts (lo guardado solo sin cobertura). Si cambia el
// propio sw.js, el nuevo toma el control y la página se recarga UNA vez (nunca con la cámara abierta o enviando).
function recargarUnaVez() {
  if (ESC.stream || S.enviando) { S.recargar = true; return; }
  let antes = 0; try { antes = Number(sessionStorage.getItem('pp-recarga')) || 0; } catch (e) { /* nada */ }
  if (Date.now() - antes < 30000) return;
  try { sessionStorage.setItem('pp-recarga', String(Date.now())); } catch (e) { /* nada */ }
  location.reload();
}
function buscarVersionNueva() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.getRegistration().then(r => r && r.update()).catch(() => {});
}
if ('serviceWorker' in navigator) {
  const habiaControl = !!navigator.serviceWorker.controller;
  navigator.serviceWorker.addEventListener('controllerchange', () => { if (habiaControl) recargarUnaVez(); });
  navigator.serviceWorker.register('sw.js', {updateViaCache: 'none'}).catch(() => {});
}
