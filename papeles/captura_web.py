# Papeles en orden (web) · capturas del banco con la MISMA lógica que la app del ordenador (banco.py + lector.py).
# El OCR lo hace el navegador (Tesseract) y aquí llegan sus líneas como [{t, x, y, w, h}].
import json
import re
from datetime import date

# Letras sueltas que el OCR lee de los iconos del banco delante del comercio («o Zoho», «O ElevenLabs», «may Primaprix»)
_RUIDO = re.compile(r"^(?:(?!(?:el|la|los|las|de|del)\s)(?:[a-z]{1,3}|[A-Za-z0-9])\s+)+(?=[A-ZÁÉÍÓÚÑ0-9])")


def _limpio(t):
    s = _RUIDO.sub("", t or "").strip()
    return s if len(re.sub(r"[^A-Za-zÁÉÍÓÚÑáéíóúñ]", "", s)) >= 2 else (t or "").strip()
import banco
import lector


def leer(lineas_json, ref_iso):
    """Devuelve JSON con la lista de movimientos si es una captura del banco; si no, null."""
    ref = date.fromisoformat(ref_iso)
    lineas = json.loads(lineas_json)
    if not lineas:
        return "null"
    filas, movs, es = banco._lectura(lineas, ref)
    if not es:
        return "null"
    out = []
    for m in movs:
        concepto = _limpio(banco.tapar_tarjetas(m["concepto"]).replace("****", " ").strip())
        nombre = banco.nombre_comercio(concepto) or concepto
        if m["tipo"] == "i":
            cat = "ingreso"
        else:
            cat = lector.clasificar_comercio(concepto) or "duda"
        out.append({"fecha": m["fecha"].isoformat(), "tipo": m["tipo"], "importe": m["importe"],
                    "divisa": m.get("divisa") or "EUR", "concepto": nombre, "clave": banco.clave_comercio(nombre),
                    "categoria": cat})
    return json.dumps({"movimientos": out}, ensure_ascii=False)


def clasificar(movs_json):
    """Movimientos que ya vienen limpios (Excel del banco): [{fecha ISO, importe con signo, concepto}].
    Devuelve el mismo formato que leer(), con el comercio, la clave y la categoría de siempre."""
    out = []
    for m in json.loads(movs_json):
        imp = float(m["importe"])
        if not imp:
            continue
        concepto = banco.tapar_tarjetas(str(m.get("concepto") or "")).replace("****", " ").strip() or "Movimiento"
        nombre = banco.nombre_comercio(concepto) or concepto
        tipo = "i" if imp > 0 else "g"
        cat = "ingreso" if tipo == "i" else (lector.clasificar_comercio(concepto) or "duda")
        out.append({"fecha": m["fecha"], "tipo": tipo, "importe": round(abs(imp), 2), "divisa": m.get("divisa") or "EUR",
                    "concepto": nombre, "clave": banco.clave_comercio(nombre), "categoria": cat})
    return json.dumps({"movimientos": out}, ensure_ascii=False)
