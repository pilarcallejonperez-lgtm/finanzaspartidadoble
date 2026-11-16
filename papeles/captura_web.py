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


# Muchos bancos (y los Excel hechos a mano) traen una columna de categoría: «Compras / Ropa y complementos»,
# «Alimentación», «Vehículo y transporte»… Si viene, manda ella: es lo que dice el banco o la propia clienta.
_PISTAS = [
    (r"hipoteca|alquiler|vivienda", "vivienda"),
    (r"prestamo|renting|financiacion|tarjeta de credito|credito", "financiacion"),
    (r"comunidad", "comunidad"),
    (r"luz|electricidad|energia", "luz"), (r"\bgas\b|butano", "gas"), (r"agua", "agua"),
    (r"telefono|internet|movil|fibra", "telefono"), (r"seguro", "seguros"),
    (r"educacion|colegio|formacion|guarderia|universidad", "colegio"),
    (r"abogado|gestoria|asesoria|notari|procurador|concurso de acreedores", "profesionales"),
    (r"impuesto|tasa|hacienda|multa", "impuestos"),
    (r"donativo|donacion|cuota de socio|cuotas|\bong\b|asociacion", "donativos"),
    (r"mascota|veterinari|pienso|perro|gato", "mascotas"),
    (r"familia|regalo", "familia"),
    (r"suscripcion|apps|software|streaming", "suscripciones"),
    (r"alimentacion|supermercado|super\b|comida", "super"),
    (r"restaurante|cafeteria|bares?\b|comer fuera", "restaurantes"),
    (r"belleza|cuidado personal|peluqueria|estetica|deporte|gimnasio", "belleza"),
    (r"ropa|complementos|calzado|moda", "ropa"),
    (r"salud|farmacia|medic|dentista|optica", "salud"),
    (r"vehiculo|coche|gasolina|combustible|parking|aparcamiento|peaje|taller", "coche"),
    (r"transporte|taxi|autobus|tren|metro", "transporte"),
    (r"ocio|cine|espectaculo|cultura", "ocio"),
    (r"viaje|hotel|vuelo|vacaciones", "viajes"),
    (r"limpieza|hogar|decoracion|mueble|bricolaje", "hogar"),
    (r"compra|electronica", "compras"),
]
_PISTAS_RX = [(re.compile(rx), cat) for rx, cat in _PISTAS]


def categoria_de_pista(pista):
    t = lector.plano(str(pista or "")).lower()
    if not t.strip():
        return None
    # «Compras / Ropa y complementos»: lo de después de la barra es lo más concreto
    for trozo in reversed([x.strip() for x in t.split("/") if x.strip()]):
        for rx, cat in _PISTAS_RX:
            if rx.search(trozo):
                return cat
    return None


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
        cat = "ingreso" if tipo == "i" else (categoria_de_pista(m.get("pista")) or lector.clasificar_comercio(concepto) or "duda")
        out.append({"fecha": m["fecha"], "tipo": tipo, "importe": round(abs(imp), 2), "divisa": m.get("divisa") or "EUR",
                    "concepto": nombre, "clave": banco.clave_comercio(nombre), "categoria": cat})
    return json.dumps({"movimientos": out}, ensure_ascii=False)
