"""Papeles en orden · capturas de pantalla de la app del banco.
Lee el texto de la imagen EN ESTE ORDENADOR (la imagen nunca sale de aquí):
  - Windows: OCR de Windows (Windows.Media.Ocr) con ocr_windows.ps1, en español si está instalado.
  - Mac: framework Vision de Apple con ocr_mac.js (JavaScript for Automation, viene con macOS; sin instalar nada).
  - Si no hay OCR, la captura se trata como cualquier foto («Por revisar»).
Después saca de cada movimiento la fecha, el concepto (comercio) y el importe con su signo.
"""
import json, os, queue, re, shutil, subprocess, sys, tempfile, threading, time
from datetime import date, timedelta
from pathlib import Path

from lector import plano

BASE = Path(__file__).resolve().parent
_CACHE = {}
SIN_VENTANA = 0x08000000  # CREATE_NO_WINDOW: en Windows no se ve ninguna ventana de PowerShell

MESES = {"ene": 1, "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3, "abr": 4, "abril": 4, "may": 5, "mayo": 5,
         "jun": 6, "junio": 6, "jul": 7, "julio": 7, "ago": 8, "agosto": 8, "sep": 9, "sept": 9, "set": 9,
         "septiembre": 9, "setiembre": 9, "oct": 10, "octubre": 10, "nov": 11, "noviembre": 11, "dic": 12, "diciembre": 12}
_M = "|".join(sorted(MESES, key=len, reverse=True))
RE_FECHA = re.compile(
    r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{4}|\d{2}))?\b"                          # 12/11/2026, 12/11/26, 12/11
    r"|\b(\d{1,2})\s*(?:de\s+)?(" + _M + r")\b\.?(?:\s*(?:de\s+|,\s*)?(\d{4}))?"      # 12 nov, 12 de noviembre de 2026
    r"|\b(hoy|ayer|anteayer)\b")
# Importe: signo opcional (el OCR lee el menos como -, −, – o —) delante o detrás del símbolo de la moneda; la moneda
# (€, EUR, $, USD, £, GBP) delante o detrás; dos decimales con coma o con punto (y miles con el otro signo).
# «-$29,54», «$-29,54», «-29,54 €», «29,54 € -», «- 1.234,56 EUR», «-USD 12.50», «£3.20».
_SIG = r"[+\-−–—]"
_DIV = r"(?:€|eur(?:os?)?\b|us\$|usd\b|\$|£|gbp\b)"
RE_IMPORTE = re.compile(
    r"(?<![\w,.])(?P<s1>" + _SIG + r")?\s?"
    r"(?:(?P<c1>" + _DIV + r")\s?(?P<s2>" + _SIG + r")?\s?)?"
    r"(?P<ent>\d{1,3}(?:[.,]\d{3})+|\d+)(?P<sep>[.,])(?P<dec>\d{2})(?!\d|[.,]\d|\s?%)"
    r"(?:\s?(?P<c2>" + _DIV + r"))?"
    r"(?:\s?(?P<s3>" + _SIG + r")(?![\s\w]*\d))?", re.I)
DIVISAS = {"€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR", "$": "USD", "us$": "USD", "usd": "USD",
           "£": "GBP", "gbp": "GBP"}
RE_CIFRA_OCR = re.compile(r"(?<![\w])(?=[\doO.]*\d)[\doO][\doO.]*,[\doO]{2}(?![\w])")
PAL_TICKET =re.compile(r"\b(ticket|factura|iva|total|cambio|entregado|base imponible|uds|unidades|subtotal|cajer[oa] n)\b")
PAL_INGRESO = re.compile(r"\b(nomina|salario|pension|prestacion|sepe|abono|ingreso|devolucion|reembolso|"
                         r"transferencia recibida|bizum recibido|bizum de)\b")
# Lo que lleva importe pero no es un movimiento: saldos, totales, premios y recompensas de la tarjeta, intereses…
NO_ES_MOVIMIENTO = re.compile(r"\b(saldo|disponible|retenido|limite|total|resumen|ingresos del mes|gastos del mes|"
                              r"canjear|canjea|premios?|recompensas?|cashback|puntos|millas|al ano|tae|tin|"
                              r"rentabilidad|reservar|ahorro acumulado|gastado este mes)\b")
# Números de tarjeta o de cuenta (enmascarados o enteros): nunca se guardan
RE_TARJETA = re.compile(r"[*•·xX]{1,}\s?\d{3,4}\b|\b\d{4}\s?[*xX•]{4,}[\s*xX•]*\d{0,4}\b|(?<!\d)\d(?:[ -]?\d){11,18}(?!\d)")
# los últimos dígitos detrás de «Tarjeta», «Visa», «Cuenta»… aunque el OCR se haya comido los asteriscos («Tarjeta 5678»)
RE_TRAS_TARJETA = re.compile(r"\b(tarjeta|visa|mastercard|master card|maestro|amex|card|cuenta|terminada en|acabada en)"
                             r"([\s*•·xX.:#-]*(?:n[ºo°]\s*)?)\d{3,4}\b", re.I)
RE_HORA =re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]\.?\s?m\.?|\s*h\b)?", re.I)
RE_REF_TARJETA = re.compile(r"\b(?:de|con|desde|en)?\s*(?:tu\s+|la\s+)?(?:visa|mastercard|master card|maestro|amex|"
                            r"american express|tarjeta|card)\b\s*(?:\*+)?\s*$", re.I)


# ---------------------------------------------------------------- OCR local
class _ServicioOCR:
    """PowerShell con el motor de OCR ya cargado, abierto mientras se usa (desde el 15/11/2026).
    Arrancar PowerShell y cargar el OCR en frío costaba ~0,7 s por lectura (y una captura oscura pide hasta 3).
    Se cierra solo tras 2 minutos sin trabajo para no ocupar memoria. Si algo falla, se lee como antes (en frío)."""
    REPOSO = 120

    def __init__(self):
        self.candado = threading.Lock()
        self.proc = None
        self.cola = None
        self.ultimo = 0.0

    def _arrancar(self):
        self.proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(BASE / "ocr_windows.ps1"),
             "-Servicio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, creationflags=SIN_VENTANA)
        self.cola = queue.Queue()
        proc, cola = self.proc, self.cola

        def lector():
            for linea in proc.stdout:
                cola.put(linea.decode("ascii", "replace").strip())
            cola.put(None)
        threading.Thread(target=lector, daemon=True).start()
        threading.Thread(target=self._vigilar, args=(proc,), daemon=True).start()

    def _vigilar(self, proc):
        while proc.poll() is None:
            time.sleep(10)
            with self.candado:
                if self.proc is proc and time.monotonic() - self.ultimo > self.REPOSO:
                    self._cerrar()
                    return

    def _cerrar(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            try:
                p.stdin.close()
                p.wait(5)
            except (OSError, subprocess.TimeoutExpired):
                p.kill()

    def leer(self, ruta, variante, salida):
        with self.candado:
            self.ultimo = time.monotonic()
            if not self.proc or self.proc.poll() is not None:
                self._arrancar()
            orden = json.dumps({"ruta": str(ruta), "salida": salida, "variante": variante}, ensure_ascii=True) + "\n"
            try:
                self.proc.stdin.write(orden.encode("ascii"))
                self.proc.stdin.flush()
                r = self.cola.get(timeout=90)
            except (OSError, queue.Empty):
                r = None
            self.ultimo = time.monotonic()
            if not r or not r.startswith("LISTO"):
                p, self.proc = self.proc, None
                if p:
                    p.kill()
                raise OSError("el servicio de OCR no ha contestado")


    def precalentar(self):
        """Arranca el servicio sin esperar (cuando ha llegado una imagen que se va a leer en un momento)."""
        if not self.candado.acquire(blocking=False):
            return
        try:
            self.ultimo = time.monotonic()
            if not self.proc or self.proc.poll() is not None:
                self._arrancar()
        except OSError:
            pass
        finally:
            self.candado.release()


_SERVICIO = _ServicioOCR()


def precalentar_ocr():
    if sys.platform.startswith("win") and os.environ.get("PAPELES_OCR_SERVICIO", "1") != "0" and ocr_disponible():
        _SERVICIO.precalentar()


def _ocr_windows(ruta, variante="normal"):
    script = BASE / "ocr_windows.ps1"
    fd, salida = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        hecho = False
        if os.environ.get("PAPELES_OCR_SERVICIO", "1") != "0":
            try:
                _SERVICIO.leer(Path(ruta).resolve(), variante, salida)
                hecho = True
            except OSError as e:
                print("OCR: sin servicio, leo en frío:", e)
        if not hecho:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
                            "-Ruta", str(Path(ruta).resolve()), "-Salida", salida, "-Variante", variante],
                           capture_output=True, timeout=90, creationflags=SIN_VENTANA)
        return json.loads(Path(salida).read_text(encoding="utf-8-sig") or "{}")
    finally:
        try:
            os.remove(salida)
        except OSError:
            pass


def _ocr_mac(ruta):
    r = subprocess.run(["osascript", "-l", "JavaScript", str(BASE / "ocr_mac.js"), str(Path(ruta).resolve())],
                       capture_output=True, text=True, timeout=90)
    return json.loads(r.stdout.strip() or "{}")


def ocr_disponible():
    if sys.platform.startswith("win"):
        return bool(shutil.which("powershell"))
    if sys.platform == "darwin":
        return bool(shutil.which("osascript"))
    return False


def leer_ocr(ruta, variante="normal"):
    """{lineas: [{t, x, y, w, h}], brillo} o None si no se ha podido leer (sin OCR, o error).
    variante: «normal», o en Windows «invertida» / «gris» (imagen preparada para capturas en modo oscuro)."""
    try:
        est = os.stat(ruta)
    except OSError:
        return None
    clave = (str(ruta), est.st_mtime, est.st_size, variante)
    if clave in _CACHE:
        return _CACHE[clave]
    lect = None
    try:
        if ocr_disponible() and (variante == "normal" or sys.platform.startswith("win")):
            res = _ocr_windows(ruta, variante) if sys.platform.startswith("win") else _ocr_mac(ruta)
            if isinstance(res, dict) and not res.get("error"):
                lin = res.get("lineas") or []
                brillo = res.get("brillo")
                lect = {"lineas": [lin] if isinstance(lin, dict) else list(lin),
                        "brillo": brillo if isinstance(brillo, (int, float)) and brillo >= 0 else None}
    except (OSError, ValueError, subprocess.SubprocessError) as e:
        print("OCR no disponible:", e)
    _CACHE[clave] = lect
    return lect


def leer_texto_imagen(ruta, variante="normal"):
    """Lista de líneas [{t, x, y, w, h}] o None si no se ha podido leer (sin OCR, o error)."""
    lect = leer_ocr(ruta, variante)
    return lect["lineas"] if lect else None


# ---------------------------------------------------------------- filas y movimientos
def agrupar_filas(lineas):
    """Junta en una fila lo que está a la misma altura (concepto a la izquierda, importe a la derecha)."""
    ls = sorted((l for l in lineas if (l.get("t") or "").strip()), key=lambda l: (l["y"] + l["h"] / 2, l["x"]))
    filas = []
    for l in ls:
        yc = l["y"] + l["h"] / 2
        if filas:
            f = filas[-1]
            if abs(yc - f["yc"]) < 0.55 * min(f["h"], l["h"]):
                f["partes"].append(l)
                f["h"] = max(f["h"], l["h"])
                continue
        filas.append({"yc": yc, "h": l["h"], "partes": [l]})
    return ["   ".join(p["t"].strip() for p in sorted(f["partes"], key=lambda p: p["x"])) for f in filas]


def _fechas(texto_p, ref):
    """Fechas que aparecen en un texto (plano). ref: fecha de la captura, para el año y para «hoy»/«ayer»."""
    out = []
    for m in RE_FECHA.finditer(texto_p):
        try:
            if m.group(7):
                out.append((m.start(), m.end(), ref - timedelta(days={"hoy": 0, "ayer": 1, "anteayer": 2}[m.group(7)])))
                continue
            if m.group(1):
                d, mo, a = int(m.group(1)), int(m.group(2)), m.group(3)
            else:
                d, mo, a = int(m.group(4)), MESES[m.group(5)], m.group(6)
            if a:
                a = int(a) + (2000 if len(a) == 2 else 0)
                f = date(a, mo, d)
            else:  # sin año: el de la captura (o el anterior si saldría en el futuro)
                f = date(ref.year, mo, d)
                if f > ref + timedelta(days=2):
                    f = date(ref.year - 1, mo, d)
            if 2000 <= f.year <= 2100:
                out.append((m.start(), m.end(), f))
        except (ValueError, KeyError):
            pass
    return out


def _signo(m):
    s = "".join((m.group(g) or "") for g in ("s1", "s2", "s3")).strip()
    return "+" if "+" in s else "-" if s else ""


def _divisa(m):
    d = (m.group("c1") or m.group("c2") or "").strip().lower()
    return DIVISAS.get(d)


def _valor(m):
    """Valor del importe, o None si los separadores no cuadran (miles y decimales con el mismo signo)."""
    ent, sep = m.group("ent"), m.group("sep")
    if sep in ent:
        return None
    return float(re.sub(r"[.,]", "", ent) + "." + m.group("dec"))


def _importe(m):
    return _valor(m), _signo(m), _divisa(m)


def _limpiar_concepto(txt):
    t = RE_TARJETA.sub(" ", RE_TRAS_TARJETA.sub(r"\1 ", txt))
    t = RE_HORA.sub(" ", t)  # «13 nov, 08:06 p. m.»: la hora no es parte del comercio
    t = re.sub(r"[€$£|·•*]+", " ", t)
    t = re.sub(r"\s+[+\-−–—]\s*$", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" -–—:,.")
    t = RE_REF_TARJETA.sub("", t).strip(" -–—:,.")  # «De Visa *3707» -> nada
    return t


def analizar_fila(fila, ref):
    """Devuelve {importe, signo, con_euro, concepto, fechas, ticket} o None si la fila no tiene importe."""
    # el OCR a veces lee un cero como «o»: «+20,oo €» -> «+20,00 €» (solo dentro de cifras)
    fila = RE_CIFRA_OCR.sub(lambda m: m.group(0).replace("o", "0").replace("O", "0"), fila)
    fp = plano(fila)
    imps = [m for m in RE_IMPORTE.finditer(fila) if _valor(m) is not None]
    fechas = _fechas(fp, ref)
    # Un importe con moneda o con signo gana a una «fecha» que lo pisa («-3.11 €» no es el 3 de noviembre);
    # un número suelto que en realidad es parte de una fecha (12.11) no cuenta como importe.
    seguros = [m for m in imps if _divisa(m) or _signo(m)]
    fechas = [f for f in fechas if not any(m.start() < f[1] and f[0] < m.end() for m in seguros)]
    imps = [m for m in imps if m in seguros or not any(a <= m.start() < b for a, b, _ in fechas)]
    info = {"fechas": [f for _, _, f in fechas], "ticket": bool(PAL_TICKET.search(fp)), "texto": fila}
    if not imps:
        resto = fila
        for a, b, _ in sorted(fechas, reverse=True):
            resto = resto[:a] + " " + resto[b:]
        info["concepto"] = _limpiar_concepto(re.sub(r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)\b,?",
                                                    " ", resto, flags=re.I))
        return info | {"importe": None}
    elegido = next((m for m in imps if _signo(m)), None) or next((m for m in imps if _divisa(m)), None) or imps[0]
    valor, signo, divisa = _importe(elegido)
    resto = fila
    cortes = [(m.start(), m.end()) for m in imps] + [(a, b) for a, b, _ in fechas]
    for a, b in sorted(cortes, reverse=True):
        resto = resto[:a] + " " + resto[b:]
    return info | {"importe": valor, "signo": signo, "divisa": divisa, "con_euro": divisa == "EUR",
                   "concepto": _limpiar_concepto(resto), "ignorar": bool(NO_ES_MOVIMIENTO.search(fp))}


def _letras(s):
    return len(re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]", s or ""))


def extraer_movimientos(filas, ref):
    """De las filas de texto de la captura saca la lista de movimientos con fecha, concepto, importe y tipo."""
    info = [analizar_fila(f, ref) for f in filas]
    movs = []  # (índice de fila, dict)
    for i, x in enumerate(info):
        if x["importe"] is None or x.get("ignorar"):
            continue
        if not (x["signo"] or x["divisa"]):
            continue
        concepto = x["concepto"]
        if _letras(concepto) < 2 and i > 0:  # el concepto puede estar justo encima del importe
            arriba = info[i - 1]
            if arriba["importe"] is None and not arriba["fechas"] and _letras(arriba["concepto"]) >= 2:
                concepto = arriba["concepto"]
        if _letras(concepto) < 2 or NO_ES_MOVIMIENTO.search(plano(concepto)):
            continue
        movs.append((i, {"concepto": concepto, "importe": x["importe"], "signo": x["signo"], "divisa": x["divisa"],
                         "fecha": x["fechas"][0] if x["fechas"] else None, "fecha_cerca": bool(x["fechas"]),
                         "fecha_leida": bool(x["fechas"])}))
    if not movs:
        return [], info
    # ¿La fecha va de título encima del grupo o en gris debajo de cada movimiento? (se decide con los movimientos con
    # signo si hay al menos dos: un saldo o un premio sin signo de la cabecera no debe confundir)
    filas_fecha = {i for i, x in enumerate(info) if x["importe"] is None and x["fechas"]}
    base = [(i, m) for i, m in movs if m["signo"]]
    base = base if len(base) >= 2 else movs
    idx_base = [i for i, _ in base]
    debajo = 0
    for n, i in enumerate(idx_base):
        siguiente = idx_base[n + 1] if n + 1 < len(idx_base) else len(info)
        if any(i < j < siguiente for j in filas_fecha):
            debajo += 1
    primero_fecha = min(filas_fecha) if filas_fecha else None
    estilo_debajo = bool(filas_fecha) and debajo >= 0.7 * len(base) and primero_fecha > idx_base[0]
    indices = [i for i, _ in movs]
    quedan = []
    for n, (i, m) in enumerate(movs):
        if not m["fecha"]:
            cerca = False
            if estilo_debajo:
                siguiente = indices[n + 1] if n + 1 < len(indices) else len(info)
                cand = [j for j in sorted(filas_fecha) if i < j < siguiente]
                cerca = bool(cand)
            else:
                cand = [j for j in sorted(filas_fecha, reverse=True) if j < i]
                if not cand:  # movimientos por encima del primer título visible: la fecha más cercana
                    cand = [j for j in sorted(filas_fecha) if j > i]
            m["fecha"] = info[cand[0]]["fechas"][0] if cand else ref
            m["fecha_leida"], m["fecha_cerca"] = bool(cand), cerca
            # Un importe SIN signo y sin ninguna fecha que le corresponda (encima en un título o debajo en gris)
            # es un saldo, un premio o un total de la cabecera, no un movimiento.
            if not m["signo"] and not (cerca or (not estilo_debajo and any(j < i for j in filas_fecha))):
                continue
        quedan.append(m)
    # Moneda: la que lleva cada importe; si alguno no la lleva, la que más se ve en la captura; si ninguna, euros.
    vistas = [m["divisa"] for m in quedan if m["divisa"]]
    por_defecto = max(set(vistas), key=vistas.count) if vistas else "EUR"
    out = []
    for m in quedan:
        cp = plano(m["concepto"])
        if m["signo"] == "+":
            tipo = "i"
        elif m["signo"] == "-":
            tipo = "g"
        else:
            tipo = "i" if PAL_INGRESO.search(cp) else "g"
        out.append({"fecha": m["fecha"], "concepto": m["concepto"], "importe": round(m["importe"], 2), "tipo": tipo,
                    "divisa": m["divisa"] or por_defecto, "con_signo": bool(m["signo"]),
                    "fecha_leida": m["fecha_leida"], "fecha_cerca": m["fecha_cerca"]})
    return out, info


def es_captura_banco(movs, info):
    """Varias líneas con concepto + importe con signo o con fecha, y sin pinta de ticket.
    Con 3 o más movimientos, como siempre. Con solo 2 o 3 también vale si cada uno tiene la estructura completa de la app
    del banco: comercio + importe con signo + su fecha al lado o justo debajo (y nada de ticket)."""
    con_signo = sum(1 for m in movs if m["con_signo"])
    con_fecha = sum(1 for x in info if x["fechas"])
    ticket = sum(1 for x in info if x["ticket"])
    completos = sum(1 for m in movs if m["con_signo"] and m.get("fecha_cerca"))
    if len(movs) >= 2 and completos >= 2 and completos >= len(movs) - 1 and ticket <= 1:
        return True
    if len(movs) < 3:
        return False
    if ticket >= 2 and con_signo < 3:
        return False
    return con_signo >= 3 or (con_signo >= 2 and con_fecha >= 2) or con_fecha >= 3


def tapar_tarjetas(texto):
    """Quita números de tarjeta y de cuenta (enteros o enmascarados) de un texto: «De Visa *3707» -> «De Visa ****»."""
    return RE_TARJETA.sub("****", RE_TRAS_TARJETA.sub(r"\1 ****", texto or ""))


def _lectura(lineas, ref):
    filas = agrupar_filas(lineas)
    movs, info = extraer_movimientos(filas, ref)
    return filas, movs, es_captura_banco(movs, info)


def leer_captura(ruta, ref):
    """Si la imagen es una captura de movimientos del banco devuelve {movimientos, texto, variante}; si no, None.
    Modo oscuro (fondo negro y letra blanca/gris): si la lectura normal no sale o la imagen es oscura o sale poco texto,
    se vuelve a leer con la imagen en negativo y en gris con contraste, y se queda la lectura que más movimientos da."""
    normal = leer_ocr(ruta, "normal")
    if not normal:
        return None
    lecturas = [("normal",) + _lectura(normal["lineas"], ref)] if normal["lineas"] else []
    oscura = normal["brillo"] is not None and normal["brillo"] < 0.35
    poco = len(normal["lineas"]) < 12
    # Solo se repite si hace falta (imagen oscura o poco texto): una foto de un ticket normal no paga dos lecturas más.
    # Si la normal ya ha salido bien, basta con comparar con la invertida (la que más ayuda en modo oscuro).
    if sys.platform.startswith("win") and (oscura or poco):
        detectada = bool(lecturas and lecturas[0][3])
        for variante in (("invertida",) if detectada else ("invertida", "gris")):
            otra = leer_ocr(ruta, variante)
            if otra and otra["lineas"]:
                lecturas.append((variante,) + _lectura(otra["lineas"], ref))
    buenas = [x for x in lecturas if x[3]]
    if not buenas:
        return None
    # la que más movimientos da; a igualdad, la que más fechas ha leído; a igualdad, la normal (va primero)
    variante, filas, movs, _ = max(buenas, key=lambda x: (len(x[2]), sum(1 for m in x[2] if m["fecha_leida"])))
    for m in movs:
        m["concepto"] = tapar_tarjetas(m["concepto"]).replace("****", " ").strip()
    return {"movimientos": movs, "texto": tapar_tarjetas("\n".join(filas))[:4000], "variante": variante}


# ---------------------------------------------------------------- comercio
PREFIJOS = re.compile(r"^(compra|compras|pago|pagos|cargo|adeudo|recibo|operacion|op|tarj|tarjeta|con|en|de|tpv|ct|cr|"
                      r"contactless|movil|apple pay|google pay|internet|comercio|transaccion)\b\.?\s*", re.I)
SUFIJOS = re.compile(r"\b(s\.?\s?a\.?\s?u?|s\.?\s?l\.?\s?u?|s\.?\s?c\.?|s\.?\s?coop\.?|cb|c\.b\.)\.?\s*$", re.I)


def nombre_comercio(concepto):
    """«COMPRA TARJ. 5402XXXX ZARA ESPAÑA SA» -> «Zara España»."""
    t = concepto or ""
    t = re.sub(r"\*+\s?\d+|\b\d{4}[xX*]+\d*\b|\b[xX*]{4,}\d*\b", " ", t)  # tarjetas enmascaradas
    t = re.sub(r"\s{2,}", " ", t).strip()
    for _ in range(4):
        nuevo = PREFIJOS.sub("", t).strip()
        if nuevo == t or _letras(nuevo) < 2:
            break
        t = nuevo
    t = SUFIJOS.sub("", t).strip(" .,-")
    if t.isupper() or t.islower():
        t = " ".join(w if re.fullmatch(r"(?:[A-Za-z]\.){1,3}|[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", w) else w.capitalize()
                     for w in t.split())
        t = re.sub(r"\b(De|Del|La|Las|Los|El|Y|En)\b", lambda m: m.group(0).lower(), t)
        t = t[:1].upper() + t[1:]
    return t[:60] or concepto


VACIAS = {"de", "del", "la", "las", "el", "los", "y", "en", "con", "sa", "sl", "slu", "sau", "es", "e"}


def clave_comercio(nombre):
    """Clave para recordar un comercio: minúsculas, sin tildes, sin números ni forma jurídica, 3 palabras."""
    t = plano(nombre)
    t = re.sub(r"[^a-z ]+", " ", t)
    pal = [p for p in t.split() if p not in VACIAS and len(p) > 1]
    return " ".join(pal[:3])


def parecidos(a, b):
    """¿Dos conceptos hablan del mismo comercio? (comparten alguna palabra con sustancia)."""
    pa = {p for p in plano(a).replace(".", " ").split() if len(p) >= 3 and p not in VACIAS}
    pb = {p for p in plano(b).replace(".", " ").split() if len(p) >= 3 and p not in VACIAS}
    pa = {re.sub(r"[^a-z]", "", p) for p in pa} - {""}
    pb = {re.sub(r"[^a-z]", "", p) for p in pb} - {""}
    return bool(pa & pb)
