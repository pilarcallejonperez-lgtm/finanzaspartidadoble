/* Papeles en orden · nube cifrada de extremo a extremo (fase 2).
   ESTE ARCHIVO ES IGUAL EN web/nube.js (ordenador) Y EN MOVIL/nube.js (móvil): si cambias uno, copia el otro.
   - La llave son 32 bytes aleatorios (256 bits) en base64url. Solo la tienen el ordenador y el móvil.
   - Carpeta en el servidor = SHA-256 de la llave en hexadecimal (no revela la llave).
   - Cada archivo: 1 byte de versión + 12 bytes de IV aleatorio + AES-GCM 256 (texto cifrado + etiqueta).
     Datos asociados «papeles:resumen» o «papeles:buzon», para que no se pueda dar uno por otro.
   - Paquete del buzón (antes de cifrar): 4 bytes con la longitud de la ficha + ficha JSON + el archivo. */
'use strict';
const Nube = (() => {
  const VERSION = 1, te = new TextEncoder(), td = new TextDecoder();

  const aB64 = bytes => { let s = ''; for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000)); return btoa(s); };
  const deB64 = s => { const bin = atob(s); const r = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) r[i] = bin.charCodeAt(i); return r; };
  const aB64u = bytes => aB64(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const deB64u = s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; return deB64(s); };
  const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');

  const llaveValida = s => /^[A-Za-z0-9_-]{43}$/.test(s || '');
  function nuevaLlave() { const k = new Uint8Array(32); crypto.getRandomValues(k); return aB64u(k); }
  // Acepta el enlace entero (…#k=XXXX) o solo el código
  function llaveDeTexto(t) {
    t = String(t || '').trim();
    const m = t.match(/[#&?]k=([A-Za-z0-9_-]{43})(?![A-Za-z0-9_-])/);
    if (m) return m[1];
    const limpio = t.replace(/\s+/g, '');
    return llaveValida(limpio) ? limpio : null;
  }
  const carpeta = async llave => hex(await crypto.subtle.digest('SHA-256', deB64u(llave)));
  const claves = new Map();
  function clave(llave) {
    if (!claves.has(llave)) claves.set(llave, crypto.subtle.importKey('raw', deB64u(llave), {name: 'AES-GCM'}, false, ['encrypt', 'decrypt']));
    return claves.get(llave);
  }
  async function cifrar(llave, datos, uso) {
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = new Uint8Array(await crypto.subtle.encrypt({name: 'AES-GCM', iv, additionalData: te.encode('papeles:' + uso)}, await clave(llave), datos));
    const out = new Uint8Array(13 + ct.length);
    out[0] = VERSION; out.set(iv, 1); out.set(ct, 13);
    return out;
  }
  async function descifrar(llave, bytes, uso) {
    bytes = new Uint8Array(bytes);
    if (bytes.length < 29 || bytes[0] !== VERSION) { const e = new Error('Formato desconocido'); e.name = 'OperationError'; throw e; }
    return new Uint8Array(await crypto.subtle.decrypt({name: 'AES-GCM', iv: bytes.slice(1, 13), additionalData: te.encode('papeles:' + uso)},
      await clave(llave), bytes.slice(13)));
  }
  const cifrarJSON = (llave, obj, uso) => cifrar(llave, te.encode(JSON.stringify(obj)), uso);
  const descifrarJSON = async (llave, bytes, uso) => JSON.parse(td.decode(await descifrar(llave, bytes, uso)));

  function empaquetar(ficha, archivo) {
    const f = te.encode(JSON.stringify(ficha)), out = new Uint8Array(4 + f.length + archivo.length);
    new DataView(out.buffer).setUint32(0, f.length);
    out.set(f, 4); out.set(archivo, 4 + f.length);
    return out;
  }
  function desempaquetar(bytes) {
    const n = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength).getUint32(0);
    if (n > bytes.length - 4) throw new Error('Paquete roto');
    return {ficha: JSON.parse(td.decode(bytes.subarray(4, 4 + n))), archivo: bytes.subarray(4 + n)};
  }

  // Supabase Storage (o el simulador local, que imita los mismos puntos de entrada)
  function almacen(cfg) {
    const base = String(cfg.url || '').replace(/\/+$/, '') + '/storage/v1', cubo = cfg.bucket || 'papeles';
    const cab = extra => {
      // clave pública de Supabase (anon o «publishable»): en apikey y en Authorization, como hace supabase-js
      const h = Object.assign({apikey: cfg.anon, Authorization: 'Bearer ' + cfg.anon}, extra || {});
      return h;
    };
    const ruta = p => p.split('/').map(encodeURIComponent).join('/');
    async function fallo(r) {
      let t = ''; try { t = await r.text(); } catch (e) { /* sin cuerpo */ }
      const e = new Error('El servidor ha contestado ' + r.status);
      e.status = r.status; e.detalle = t.slice(0, 300);
      // solo «ese archivo no está» (no «no existe el bucket», que es un fallo de configuración)
      e.noExiste = (r.status === 404 || r.status === 400) && /"not_found"|Object not found|NoSuchKey/i.test(t) && !/bucket/i.test(t);
      return e;
    }
    return {
      async subir(p, bytes, sobrescribir) {
        const r = await fetch(`${base}/object/${cubo}/${ruta(p)}`, {method: 'POST', body: bytes,
          headers: cab({'Content-Type': 'application/octet-stream', 'x-upsert': sobrescribir ? 'true' : 'false', 'cache-control': 'max-age=0'})});
        if (!r.ok) throw await fallo(r);
      },
      async bajar(p) {
        const r = await fetch(`${base}/object/authenticated/${cubo}/${ruta(p)}`, {headers: cab(), cache: 'no-store'});
        if (!r.ok) throw await fallo(r);
        return new Uint8Array(await r.arrayBuffer());
      },
      async listar(prefijo) {
        const r = await fetch(`${base}/object/list/${cubo}`, {method: 'POST', cache: 'no-store', headers: cab({'Content-Type': 'application/json'}),
          body: JSON.stringify({prefix: prefijo, limit: 100, offset: 0, sortBy: {column: 'name', order: 'asc'}})});
        if (!r.ok) throw await fallo(r);
        return (await r.json()).filter(o => o && o.id && o.name && !o.name.startsWith('.'));
      },
      async borrar(rutas) {
        if (!rutas.length) return;
        const r = await fetch(`${base}/object/${cubo}`, {method: 'DELETE', headers: cab({'Content-Type': 'application/json'}), body: JSON.stringify({prefixes: rutas})});
        if (!r.ok) throw await fallo(r);
      },
    };
  }

  return {llaveValida, nuevaLlave, llaveDeTexto, carpeta, cifrar, descifrar, cifrarJSON, descifrarJSON,
          empaquetar, desempaquetar, almacen, aB64, deB64};
})();
