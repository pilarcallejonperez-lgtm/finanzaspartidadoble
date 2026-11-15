/* Papeles en orden · generador de códigos QR sin librerías externas (funciona sin internet).
   Modo byte, corrección de errores M (15 %), versiones 1-40, máscara elegida por penalización.
   Sigue la norma ISO/IEC 18004 y la estructura del generador de Project Nayuki
   (https://www.nayuki.io/page/qr-code-generator-library), publicado con licencia MIT:

   Copyright (c) Project Nayuki. (MIT License)
   Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
   associated documentation files (the "Software"), to deal in the Software without restriction, including
   without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
   copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the
   following conditions: The above copyright notice and this permission notice shall be included in all
   copies or substantial portions of the Software.
   THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
   LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
   IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
   WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
   SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE. */
'use strict';
const QR = (() => {
  // Corrección M: códigos de corrección por bloque y número de bloques (índice = versión)
  const ECC = [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28];
  const BLOQUES = [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49];
  const NIVEL_M = 0;  // bits de formato del nivel M

  function modulosBrutos(v) {
    let r = (16 * v + 128) * v + 64;
    if (v >= 2) { const n = Math.floor(v / 7) + 2; r -= (25 * n - 10) * n - 55; if (v >= 7) r -= 36; }
    return r;
  }
  const palabrasDatos = v => Math.floor(modulosBrutos(v) / 8) - ECC[v] * BLOQUES[v];
  function mul(x, y) { let z = 0; for (let i = 7; i >= 0; i--) { z = (z << 1) ^ ((z >>> 7) * 0x11D); z ^= ((y >>> i) & 1) * x; } return z; }
  function divisor(g) {
    const r = new Array(g).fill(0); r[g - 1] = 1; let raiz = 1;
    for (let i = 0; i < g; i++) { for (let j = 0; j < g; j++) { r[j] = mul(r[j], raiz); if (j + 1 < g) r[j] ^= r[j + 1]; } raiz = mul(raiz, 2); }
    return r;
  }
  function resto(datos, div) {
    const r = div.map(() => 0);
    for (const b of datos) { const f = b ^ r.shift(); r.push(0); div.forEach((c, i) => { r[i] ^= mul(c, f); }); }
    return r;
  }
  function alineacion(v) {
    if (v === 1) return [];
    const n = Math.floor(v / 7) + 2, paso = v === 32 ? 26 : Math.ceil((v * 4 + 4) / (n * 2 - 2)) * 2, r = [6];
    for (let p = v * 4 + 17 - 7; r.length < n; p -= paso) r.splice(1, 0, p);
    return r;
  }
  function penalizacion(m, n) {
    let p = 0, oscuros = 0;
    const lineas = [];
    for (let y = 0; y < n; y++) lineas.push(m[y].map(o => o ? '1' : '0').join(''));
    for (let x = 0; x < n; x++) { let s = ''; for (let y = 0; y < n; y++) s += m[y][x] ? '1' : '0'; lineas.push(s); }
    for (const s of lineas) {
      for (const tramo of s.match(/0+|1+/g)) if (tramo.length >= 5) p += tramo.length - 2;
      for (const patron of ['10111010000', '00001011101']) for (let i = s.indexOf(patron); i >= 0; i = s.indexOf(patron, i + 1)) p += 40;
    }
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      if (m[y][x]) oscuros++;
      if (x < n - 1 && y < n - 1 && m[y][x] === m[y][x + 1] && m[y][x] === m[y + 1][x] && m[y][x] === m[y + 1][x + 1]) p += 3;
    }
    const total = n * n;
    return p + (Math.ceil(Math.abs(oscuros * 20 - total * 10) / total) - 1) * 10;
  }

  function crear(texto) {
    const bytes = [...new TextEncoder().encode(texto)];
    let v = 1;
    while (v <= 40 && 4 + (v < 10 ? 8 : 16) + bytes.length * 8 > palabrasDatos(v) * 8) v++;
    if (v > 40) throw new Error('Texto demasiado largo para un código QR');
    // datos: modo byte (0100) + longitud + bytes + final + relleno
    const bits = [], poner = (val, n) => { for (let i = n - 1; i >= 0; i--) bits.push((val >>> i) & 1); };
    poner(4, 4); poner(bytes.length, v < 10 ? 8 : 16); bytes.forEach(b => poner(b, 8));
    const cap = palabrasDatos(v) * 8;
    poner(0, Math.min(4, cap - bits.length)); poner(0, (8 - bits.length % 8) % 8);
    for (let pad = 0xEC; bits.length < cap; pad ^= 0xEC ^ 0x11) poner(pad, 8);
    const datos = [];
    for (let i = 0; i < bits.length; i += 8) { let b = 0; for (let j = 0; j < 8; j++) b = (b << 1) | bits[i + j]; datos.push(b); }
    // bloques con su corrección de errores, intercalados
    const nb = BLOQUES[v], largoEcc = ECC[v], brutas = Math.floor(modulosBrutos(v) / 8);
    const cortos = nb - brutas % nb, largoCorto = Math.floor(brutas / nb), div = divisor(largoEcc), bloques = [];
    for (let i = 0, k = 0; i < nb; i++) {
      const d = datos.slice(k, k + largoCorto - largoEcc + (i < cortos ? 0 : 1)); k += d.length;
      const e = resto(d, div); if (i < cortos) d.push(0); bloques.push(d.concat(e));
    }
    const final = [];
    for (let i = 0; i < bloques[0].length; i++) bloques.forEach((b, j) => { if (i !== largoCorto - largoEcc || j >= cortos) final.push(b[i]); });
    // matriz y patrones fijos
    const n = v * 4 + 17;
    const m = [...Array(n)].map(() => new Array(n).fill(false)), fijo = [...Array(n)].map(() => new Array(n).fill(false));
    const fijar = (x, y, o) => { m[y][x] = o; fijo[y][x] = true; };
    for (let i = 0; i < n; i++) { fijar(6, i, i % 2 === 0); fijar(i, 6, i % 2 === 0); }
    const buscador = (x, y) => {
      for (let dy = -4; dy <= 4; dy++) for (let dx = -4; dx <= 4; dx++) {
        const d = Math.max(Math.abs(dx), Math.abs(dy)), xx = x + dx, yy = y + dy;
        if (xx >= 0 && xx < n && yy >= 0 && yy < n) fijar(xx, yy, d !== 2 && d !== 4);
      }
    };
    buscador(3, 3); buscador(n - 4, 3); buscador(3, n - 4);
    const al = alineacion(v), na = al.length;
    for (let i = 0; i < na; i++) for (let j = 0; j < na; j++) {
      if ((i === 0 && j === 0) || (i === 0 && j === na - 1) || (i === na - 1 && j === 0)) continue;
      for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) fijar(al[i] + dx, al[j] + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1);
    }
    const formato = mascara => {
      const d = (NIVEL_M << 3) | mascara; let r = d;
      for (let i = 0; i < 10; i++) r = (r << 1) ^ ((r >>> 9) * 0x537);
      const b = ((d << 10) | r) ^ 0x5412, bit = i => ((b >>> i) & 1) === 1;
      for (let i = 0; i <= 5; i++) fijar(8, i, bit(i));
      fijar(8, 7, bit(6)); fijar(8, 8, bit(7)); fijar(7, 8, bit(8));
      for (let i = 9; i < 15; i++) fijar(14 - i, 8, bit(i));
      for (let i = 0; i < 8; i++) fijar(n - 1 - i, 8, bit(i));
      for (let i = 8; i < 15; i++) fijar(8, n - 15 + i, bit(i));
      fijar(8, n - 8, true);
    };
    formato(0);
    if (v >= 7) {
      let r = v; for (let i = 0; i < 12; i++) r = (r << 1) ^ ((r >>> 11) * 0x1F25);
      const b = (v << 12) | r;
      for (let i = 0; i < 18; i++) { const o = ((b >>> i) & 1) === 1, a = n - 11 + i % 3, c = Math.floor(i / 3); fijar(a, c, o); fijar(c, a, o); }
    }
    // datos en zigzag, de abajo a arriba y de derecha a izquierda
    let i = 0;
    for (let der = n - 1; der >= 1; der -= 2) {
      if (der === 6) der = 5;
      for (let vert = 0; vert < n; vert++) for (let j = 0; j < 2; j++) {
        const x = der - j, arriba = ((der + 1) & 2) === 0, y = arriba ? n - 1 - vert : vert;
        if (!fijo[y][x] && i < final.length * 8) { m[y][x] = ((final[i >>> 3] >>> (7 - (i & 7))) & 1) === 1; i++; }
      }
    }
    // máscara: la que menos penaliza
    const invierte = (k, x, y) => [(x + y) % 2 === 0, y % 2 === 0, x % 3 === 0, (x + y) % 3 === 0,
      (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0, x * y % 2 + x * y % 3 === 0,
      (x * y % 2 + x * y % 3) % 2 === 0, ((x + y) % 2 + x * y % 3) % 2 === 0][k];
    const aplicar = k => { for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) if (!fijo[y][x] && invierte(k, x, y)) m[y][x] = !m[y][x]; };
    let mejor = 0, menor = Infinity;
    for (let k = 0; k < 8; k++) { aplicar(k); formato(k); const p = penalizacion(m, n); if (p < menor) { menor = p; mejor = k; } aplicar(k); }
    aplicar(mejor); formato(mejor);
    return {tam: n, modulos: m, version: v, mascara: mejor};
  }

  // SVG con 4 módulos de margen blanco (lo que piden los lectores)
  function svg(texto, etiqueta) {
    const q = crear(texto), b = 4, t = q.tam + b * 2;
    let d = '';
    for (let y = 0; y < q.tam; y++) for (let x = 0; x < q.tam; x++) if (q.modulos[y][x]) d += `M${x + b} ${y + b}h1v1h-1z`;
    return `<svg class="qr" viewBox="0 0 ${t} ${t}" shape-rendering="crispEdges" role="img" aria-label="${etiqueta || 'Código QR'}"><rect width="${t}" height="${t}" fill="#fff"/><path d="${d}" fill="#111"/></svg>`;
  }
  return {crear, svg};
})();
