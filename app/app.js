/* Papeles en orden · app del móvil.
   Lee el resumen cifrado que sube el ordenador y manda papeles cifrados a su buzón.
   La llave llega en el código QR (#k=…, el fragmento no viaja nunca al servidor web) y se guarda solo en este móvil. */
'use strict';
const CFG = window.PAPELES_MOVIL || {};
const $ = id => document.getElementById(id);
const K = {llave: 'pp-llave', cache: 'pp-resumen', visto: 'pp-recibido', enviados: 'pp-enviados', vista: 'pp-vista'};
const L = {
  get: k => { try { return localStorage.getItem(k); } catch (e) { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* modo privado: solo en memoria */ } },
  del: k => { try { localStorage.removeItem(k); } catch (e) { /* nada */ } },
};
const MAX_MB = 25;
const S = {llave: null, carpeta: null, al: null, datos: null};

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
function ir(v) {
  document.querySelectorAll('.vista').forEach(s => { s.hidden = s.id !== 'v-' + v; });
  document.querySelectorAll('nav.menu button').forEach(b => b.setAttribute('aria-current', b.dataset.ir === v));
  $('menu').hidden = v === 'conectar';
  window.scrollTo(0, 0);
  if (v !== 'conectar') L.set(K.vista, v);
  if (v === 'mandar') pintarEnviados();
}
document.querySelectorAll('[data-ir]').forEach(b => { b.onclick = () => ir(b.dataset.ir); });

/* ------------------------------------------------ la llave */
function leerFragmento() {
  const m = location.hash.match(/k=([A-Za-z0-9_-]{43})/);
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);  // fuera de la barra de direcciones
  return m ? m[1] : null;
}
async function usarLlave(llave) {
  if (llave !== L.get(K.llave)) { [K.cache, K.visto, K.enviados].forEach(L.del); S.datos = null; }
  S.llave = llave; L.set(K.llave, llave);
  S.carpeta = await Nube.carpeta(llave);
  S.al = Nube.almacen({url: CFG.supabaseUrl, anon: CFG.anonKey, bucket: CFG.bucket});
}
function olvidar(motivo) {
  [K.llave, K.cache, K.visto, K.enviados].forEach(L.del);
  S.llave = S.carpeta = S.al = S.datos = null;
  pantallaConectar(motivo);
}
function pantallaConectar(motivo) {
  $('conAviso').hidden = !motivo; $('conAviso').textContent = motivo || '';
  $('conTitulo').textContent = motivo ? 'Vuelve a escanear el código' : 'Escanea el código de tu ordenador';
  linea('Finanzas Partida Doble');
  ir('conectar');
}
$('formCodigo').onsubmit = async e => {
  e.preventDefault();
  const llave = Nube.llaveDeTexto($('codigo').value);
  if (!llave) return avisar('msgCodigo', 'Ese código no es válido. Cópialo entero desde tu ordenador.', true);
  $('codigo').value = ''; avisar('msgCodigo', '');
  await usarLlave(llave);
  $('conAviso').hidden = true;
  ir('inicio'); pintarSinDatos(); actualizar();
};
$('btnOlvidar').onclick = () => {
  if (confirm('¿Desconecto este móvil? Para volver a ver tus papeles tendrás que escanear el código otra vez.')) olvidar('');
};

/* ------------------------------------------------ el resumen */
async function actualizar() {
  if (!S.al) return;
  linea('Poniéndome al día…');
  try {
    const bytes = await S.al.bajar(S.carpeta + '/resumen.enc');
    const datos = await Nube.descifrarJSON(S.llave, bytes, 'resumen');
    L.set(K.cache, Nube.aB64(bytes)); L.set(K.visto, '1');
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
  for (const [i, f] of lista.entries()) {
    avisar('msgMandar', lista.length > 1 ? `Enviando ${i + 1} de ${lista.length}…` : 'Enviando…');
    try { if (await mandar(f)) bien++; }
    catch (e) { avisar('msgMandar', 'No he podido enviarlo. Mira si tienes conexión y vuelve a probar.', true); pintarEnviados(); return; }
  }
  if (bien) avisar('msgMandar', `✓ ${bien === 1 ? 'Enviado' : bien + ' enviados'}. Tu ordenador ${bien === 1 ? 'lo' : 'los'} ordenará en cuanto esté encendido.`);
  pintarEnviados(); comprobarEnviados();
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

/* ------------------------------------------------ arranque */
async function arrancar() {
  const delQR = leerFragmento(), guardada = L.get(K.llave);
  const llave = delQR || (Nube.llaveValida(guardada) ? guardada : null);
  if (!CFG.supabaseUrl || !CFG.anonKey) { if (delQR) L.set(K.llave, delQR); pantallaConectar('La aplicación aún no está activada. Avísanos, por favor.'); return; }
  if (!llave) return olvidar('');
  await usarLlave(llave);
  const vista = delQR ? 'inicio' : (L.get(K.vista) || 'inicio');
  ir(document.getElementById('v-' + vista) && vista !== 'conectar' ? vista : 'inicio');
  const cache = L.get(K.cache);  // lo último que llegó, para que se vea al momento
  if (cache) { try { pintar(await Nube.descifrarJSON(S.llave, Nube.deB64(cache), 'resumen')); } catch (e) { L.del(K.cache); } }
  else pintarSinDatos();
  pintarEnviados();
  await actualizar();
}
window.addEventListener('hashchange', () => { if (/k=/.test(location.hash)) arrancar(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') actualizar(); });
setInterval(() => { if (document.visibilityState === 'visible') actualizar(); }, 2 * 60 * 1000);
arrancar().catch(e => { linea('No he podido arrancar'); console.error(e); });
if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
