"""Papeles en orden · lector de documentos.
Saca del texto de un PDF: fecha, emisor, NIF/CIF, importe total, tipo de documento,
categoría y fecha de vencimiento. Todo con reglas (sin IA y sin internet).
Para leer el texto del PDF usa pypdf (ya instalado en el equipo); si no está, prueba pdfplumber.
"""
import re
import unicodedata
from datetime import date
from pathlib import Path

# ------------------------------------------------------------------ categorías
CATEGORIAS = [
    ("luz", "Luz"), ("agua", "Agua"), ("gas", "Gas"), ("telefono", "Teléfono e internet"),
    ("seguros", "Seguros"), ("colegio", "Colegio"), ("comunidad", "Comunidad"),
    ("vivienda", "Hipoteca o alquiler"), ("coche", "Vehículo y transporte"), ("transporte", "Transporte público"), ("salud", "Salud"),
    ("financiacion", "Préstamos, renting y tarjeta"), ("belleza", "Belleza, cuidado personal y deporte"),
    ("suscripciones", "Suscripciones"), ("impuestos", "Impuestos y tasas"),
    ("super", "Súper y comida"), ("restaurantes", "Comer fuera"), ("ropa", "Ropa"), ("compras", "Compras"),
    ("ocio", "Ocio y caprichos"), ("otros", "Otros"),
    ("revisar", "Por revisar"),  # lo que no se ha podido leer bien se guarda aquí, sin preguntar
    ("duda", "En duda"),         # movimientos del banco de los que no sabemos qué son (ella elige)
    ("banco", "Banco"),          # carpeta de las capturas de pantalla del banco
]
NOMBRE_CAT = dict(CATEGORIAS)
NOMBRE_CAT["ingreso"] = "Ingresos"
# Categorías que no son de gasto (no salen en el desplegable de «En duda»)
NO_GASTO = ("revisar", "duda", "banco")

TIPOS = [
    ("factura", "Factura"), ("recibo", "Recibo"), ("poliza", "Póliza"),
    ("presupuesto", "Presupuesto o aviso de renovación"), ("contrato", "Contrato"),
    ("garantia", "Garantía"), ("captura", "Captura del banco"), ("otro", "Otro"),
]
NOMBRE_TIPO = dict(TIPOS)
TIPO_CORTO = {"factura": "Factura", "recibo": "Recibo", "poliza": "Póliza", "presupuesto": "Presupuesto",
              "contrato": "Contrato", "garantia": "Garantía", "captura": "Captura del banco", "otro": "Documento"}


def plano(t):
    """minúsculas y sin tildes, para comparar."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# (patrón sobre texto plano, nombre bonito, categoría)
EMISORES = [
    (r"repsol (luz|electricidad|gas)", "Repsol", "luz"),
    (r"iberdrola", "Iberdrola", "luz"), (r"endesa", "Endesa", "luz"), (r"naturgy", "Naturgy", "gas"),
    (r"gas natural fenosa", "Naturgy", "gas"), (r"holaluz", "Holaluz", "luz"),
    (r"totalenergies", "TotalEnergies", "luz"), (r"octopus energy", "Octopus Energy", "luz"),
    (r"\bedp\b", "EDP", "luz"), (r"curenergia", "Curenergía", "luz"), (r"energia xxi", "Energía XXI", "luz"),
    (r"canal de isabel ii", "Canal de Isabel II", "agua"), (r"aqualia", "Aqualia", "agua"),
    (r"emasesa", "Emasesa", "agua"), (r"aguas de [a-z]+", None, "agua"), (r"aguas municipales", None, "agua"),
    (r"aquona", "Aquona", "agua"), (r"agbar|aigues de barcelona", "Aigües de Barcelona", "agua"),
    (r"movistar|telefonica de espana", "Movistar", "telefono"), (r"vodafone", "Vodafone", "telefono"),
    (r"\borange\b", "Orange", "telefono"), (r"masmovil|mas movil", "MásMóvil", "telefono"),
    (r"yoigo", "Yoigo", "telefono"), (r"jazztel", "Jazztel", "telefono"), (r"pepephone", "Pepephone", "telefono"),
    (r"\bdigi\b", "Digi", "telefono"), (r"\blowi\b", "Lowi", "telefono"), (r"simyo", "Simyo", "telefono"),
    (r"mapfre", "Mapfre", "seguros"), (r"mutua madrilena", "Mutua Madrileña", "seguros"),
    (r"linea directa", "Línea Directa", "seguros"), (r"allianz", "Allianz", "seguros"), (r"\baxa\b", "AXA", "seguros"),
    (r"generali", "Generali", "seguros"), (r"zurich", "Zurich", "seguros"), (r"reale seguros", "Reale", "seguros"),
    (r"pelayo", "Pelayo", "seguros"), (r"\bcaser\b", "Caser", "seguros"), (r"santalucia|santa lucia", "Santalucía", "seguros"),
    (r"ocaso", "Ocaso", "seguros"), (r"sanitas", "Sanitas", "seguros"), (r"adeslas", "Adeslas", "seguros"),
    (r"\bdkv\b", "DKV", "seguros"), (r"\basisa\b", "Asisa", "seguros"), (r"catalana occidente", "Catalana Occidente", "seguros"),
    (r"\bverti\b", "Verti", "seguros"), (r"liberty seguros", "Liberty", "seguros"), (r"\bmutua\b", "Mutua", "seguros"),
    (r"netflix", "Netflix", "suscripciones"), (r"spotify", "Spotify", "suscripciones"),
    (r"disney\+|disney plus", "Disney+", "suscripciones"), (r"\bhbo\b|\bmax\b streaming", "Max", "suscripciones"),
    (r"amazon prime|prime video", "Amazon Prime", "suscripciones"), (r"dazn", "DAZN", "suscripciones"),
    (r"youtube premium", "YouTube Premium", "suscripciones"), (r"icloud|apple\.com", "Apple", "suscripciones"),
    (r"audible", "Audible", "suscripciones"), (r"filmin", "Filmin", "suscripciones"),
    (r"agencia tributaria|\baeat\b", "Agencia Tributaria", "impuestos"),
    (r"direccion general de trafico|\bdgt\b", "DGT", "impuestos"),
    (r"ayuntamiento de [a-z]+", None, "impuestos"), (r"diputacion de [a-z]+", None, "impuestos"),
    (r"comunidad de propietarios", None, "comunidad"),
    # --- ampliación 14/11/2026
    # agua (empresas municipales y concesionarias)
    (r"aquavall|agua de valladolid|servicioagua", "Aquavall", "agua"), (r"canal de isabel", "Canal de Isabel II", "agua"),
    (r"\baqualia\b", "Aqualia", "agua"), (r"\bemaya\b", "Emaya", "agua"), (r"\bemasa\b", "Emasa", "agua"),
    (r"\bemuasa\b", "Emuasa", "agua"), (r"\bemacsa\b", "Emacsa", "agua"), (r"aguas municipalizadas", None, "agua"),
    (r"empresa municipal de aguas", None, "agua"), (r"\baquara\b", "Aquara", "agua"), (r"\bfacsa\b", "FACSA", "agua"),
    (r"global omnium|aguas de valencia", "Global Omnium", "agua"), (r"\bagua de [a-z]{4,}", None, "agua"),
    # dominios e internet
    (r"dondominio|soluciones corporativas ip", "DonDominio", "telefono"), (r"\barsys\b", "Arsys", "telefono"),
    (r"\bionos\b|1&1 ionos", "IONOS", "telefono"), (r"godaddy", "GoDaddy", "telefono"), (r"hostinger", "Hostinger", "telefono"),
    (r"dinahosting", "Dinahosting", "telefono"), (r"nominalia", "Nominalia", "telefono"), (r"\bcdmon\b", "cdmon", "telefono"),
    (r"raiola networks", "Raiola Networks", "telefono"), (r"webempresa", "Webempresa", "telefono"),
    (r"namecheap", "Namecheap", "telefono"), (r"siteground", "SiteGround", "telefono"),
    (r"\bo2\b fibra|telefonica moviles", "Movistar", "telefono"), (r"\bfinetwork\b", "Finetwork", "telefono"),
    (r"avatel", "Avatel", "telefono"), (r"\bsilbo\b", "Silbo", "telefono"),
    # ropa
    (r"zara home", "Zara Home", "compras"), (r"\bzara\b", "Zara", "ropa"), (r"bershka", "Bershka", "ropa"),
    (r"stradivarius", "Stradivarius", "ropa"), (r"pull ?(and|&) ?bear", "Pull&Bear", "ropa"),
    (r"massimo dutti", "Massimo Dutti", "ropa"), (r"\boysho\b", "Oysho", "ropa"), (r"\blefties\b", "Lefties", "ropa"),
    (r"\bmango\b|punto fa,? s\.?l", "Mango", "ropa"), (r"\bh ?& ?m\b|hennes ?(&|and) ?mauritz", "H&M", "ropa"),
    (r"primark", "Primark", "ropa"), (r"\bkiabi\b", "Kiabi", "ropa"), (r"springfield", "Springfield", "ropa"),
    (r"cortefiel", "Cortefiel", "ropa"), (r"\bshein\b", "Shein", "ropa"), (r"decathlon", "Decathlon", "compras"),
    # compras y súper
    (r"el corte ingles", "El Corte Inglés", "compras"), (r"mercadona", "Mercadona", "super"),
    (r"carrefour", "Carrefour", "super"), (r"\blidl\b", "Lidl", "super"),
    (r"supermercados dia|dia retail|distribuidora internacional de alimentacion", "Dia", "super"),
    (r"\balcampo\b", "Alcampo", "super"), (r"\beroski\b", "Eroski", "super"), (r"\baldi\b", "Aldi", "super"),
    (r"\bgadis\b", "Gadis", "super"), (r"\bconsum\b", "Consum", "super"), (r"\bahorramas\b", "Ahorramás", "super"),
    (r"too ?good ?to ?go", "Too Good To Go", "super"),
    (r"amazon prime|prime video", "Amazon Prime", "suscripciones"), (r"\bamazon\b", "Amazon", "compras"),
    (r"\bikea\b", "IKEA", "compras"), (r"leroy merlin", "Leroy Merlin", "compras"), (r"media ?markt", "MediaMarkt", "compras"),
    (r"\bfnac\b", "Fnac", "compras"), (r"pccomponentes", "PcComponentes", "compras"),
    # energía y coche
    (r"\b(cepsa|moeve) (luz|gas|electricidad)", "Moeve", "luz"),
    (r"\brepsol\b", "Repsol", "coche"), (r"\bcepsa\b|\bmoeve\b", "Moeve", "coche"), (r"\bgalp\b", "Galp", "coche"),
    (r"\bacciona\b", "Acciona", "coche"), (r"\bzunder\b", "Zunder", "coche"), (r"\bionity\b", "Ionity", "coche"),
    (r"\bwallbox\b", "Wallbox", "coche"),
    # seguros
    (r"penelope seguros", "Penélope Seguros", "seguros"), (r"\bmapfre\b", "Mapfre", "seguros"),
    (r"segurcaixa", "SegurCaixa Adeslas", "seguros"), (r"\bfiatc\b", "Fiatc", "seguros"), (r"\bhelvetia\b", "Helvetia", "seguros"),
    (r"\bqualitas auto\b", "Qualitas Auto", "seguros"), (r"\bmutua general de seguros\b", "MGS", "seguros"),
]

# Grupos o sociedades que salen en la letra pequeña de varias marcas: solo si no hay una marca concreta
EMISORES_GRUPO = [
    (r"inditex|industria de diseno textil", "Inditex", "ropa"),
    (r"telefonica", "Movistar", "telefono"),
]

PALABRAS = [  # (categoría, palabras sobre texto plano) — gana la que más aparece; si empatan, la primera
    ("seguros", ["seguro", "seguros", "poliza", "aseguradora", "prima neta", "tomador"]),
    ("comunidad", ["comunidad de propietarios", "cuota de comunidad", "administrador de fincas", "derrama"]),
    ("vivienda", ["hipoteca", "prestamo hipotecario", "alquiler", "arrendamiento", "renta mensual"]),
    ("impuestos", ["ibi", "bienes inmuebles", "impuesto sobre bienes inmuebles", "impuesto de circulacion",
                   "impuesto municipal", "tasa municipal", "tasa de basura", "tasa de basuras", "basuras", "multa",
                   "vehiculos de traccion mecanica", "modelo 100", "plusvalia", "liquidacion tributaria"]),
    ("colegio", ["colegio", "ampa", "comedor escolar", "escuela infantil", "guarderia", "matricula",
                 "academia", "extraescolar", "uniforme escolar"]),
    ("luz", ["electricidad", "energia electrica", "potencia contratada", "kwh", "luz"]),
    ("gas", ["gas natural", "suministro de gas", "butano", "propano"]),
    ("agua", ["suministro de agua", "agua potable", "saneamiento", "alcantarillado", "m3", "abastecimiento",
              "depuracion", "consumo de agua", "agua cuota", "cuota de agua", "servicio de agua"]),
    ("telefono", ["fibra", "movil", "telefono", "internet", "linea fija", "tarifa de datos",
                  "registro de dominio", "renovacion de dominio", "nombre de dominio", "dominio web", "hosting",
                  "alojamiento web"]),
    ("ropa", ["anorak", "camiseta", "pantalon", "vestido", "chaqueta", "abrigo", "zapatillas", "jersey", "falda",
              "blusa", "sudadera", "calcetines", "sujetador"]),
    ("suscripciones", ["suscripcion", "plan mensual", "membresia", "premium"]),
    ("coche", ["itv", "taller", "neumatico", "gasolina", "gasoleo", "carburante", "parking",
               "aparcamiento", "revision del vehiculo", "cambio de aceite"]),
    ("salud", ["farmacia", "clinica", "dental", "dentista", "optica", "fisioterapia", "hospital", "consulta medica"]),
    ("super", ["mercadona", "carrefour", "lidl", "alcampo", "eroski", "supermercado", "aldi", "hipercor"]),
]

SEGURO_TIPOS = [("hogar", ["hogar", "vivienda", "multirriesgo"]), ("coche", ["automovil", "coche", "vehiculo", "auto "]),
                ("moto", ["motocicleta", "moto "]), ("salud", ["salud", "asistencia sanitaria", "dental"]),
                ("vida", ["seguro de vida", "vida riesgo", "fallecimiento"]), ("decesos", ["decesos"]),
                ("mascotas", ["mascota", "perro", "gato"])]

# ------------------------------------------------------------------ lectura de PDF
LIBRERIA_PDF = None
try:
    import pypdf  # noqa
    LIBRERIA_PDF = "pypdf"
except ImportError:
    try:
        import pdfplumber  # noqa
        LIBRERIA_PDF = "pdfplumber"
    except ImportError:
        LIBRERIA_PDF = None


def texto_pdf(ruta, max_paginas=4):
    if LIBRERIA_PDF == "pypdf":
        import logging
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        from pypdf import PdfReader
        lector = PdfReader(ruta)
        return "\n".join((p.extract_text() or "") for p in lector.pages[:max_paginas])
    if LIBRERIA_PDF == "pdfplumber":
        import pdfplumber
        with pdfplumber.open(ruta) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_paginas])
    return ""


# ------------------------------------------------------------------ fechas e importes
MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                     "septiembre", "octubre", "noviembre", "diciembre"], 1)}
MESES["setiembre"] = 9
RE_FECHA = re.compile(
    r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4}|\d{2})\b"
    r"|\b(\d{4})-(\d{2})-(\d{2})\b"
    r"|\b(\d{1,2}) de (" + "|".join(MESES) + r")(?: de|,)? (\d{4})\b")
RE_IMPORTE = re.compile(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}|\d+\.\d{2}(?=\s*(?:€|eur)))(?![\d])")


def fechas_en(linea):
    out = []
    for m in RE_FECHA.finditer(linea):
        try:
            if m.group(1):
                d, mo, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if a < 100:
                    a += 2000
            elif m.group(4):
                a, mo, d = int(m.group(4)), int(m.group(5)), int(m.group(6))
            else:
                d, mo, a = int(m.group(7)), MESES[m.group(8)], int(m.group(9))
            out.append(date(a, mo, d))
        except ValueError:
            pass
    return [f for f in out if 1990 <= f.year <= 2100]


def importes_en(linea):
    out = []
    for m in RE_IMPORTE.finditer(linea):
        s = m.group(1)
        s = s.replace(".", "").replace(",", ".") if "," in s else s
        try:
            out.append(float(s))
        except ValueError:
            pass
    return out


# El total final manda: primero las frases claras de «lo que se paga»; luego las líneas «TOTAL» (sin bases ni IVA);
# y solo al final «importe», «precio» o «prima» sueltos.
CLAVES_TOTAL_FUERTES = [r"total a pagar", r"importe a pagar", r"\ba pagar\b", r"total factura", r"importe total",
                        r"total importe", r"total recibo", r"importe del recibo", r"importe adeudado", r"importe a cargar",
                        r"total a cargar", r"total compra", r"total venta", r"total ticket", r"total a abonar",
                        r"prima total", r"precio total", r"prima anual", r"total \(?(eur|euros|€)\)?"]
CLAVES_TOTAL_DEBILES = [r"\bimporte\b", r"\bprecio\b", r"\bprima\b"]
# líneas que hablan de dinero que NO es el total de este papel (deudas anteriores, ahorros, bases, IVA…)
NO_ES_TOTAL = (r"adeudaban|pendientes? de pago|deuda|facturas? (anteriores|pendientes)|por un importe total de|"
               r"acumulad|ahorr|descuento|\bdto\b|saldo anterior|importe minimo|limite|franquicia")
PARCIAL = r"subtotal|sin iva|base imponible|\bbase\b|\bneto\b|\bbruto\b|\biva\b|\bigic\b|cuota iva|impuestos?\b|\bimp\b"
CLAVES_FECHA = [r"fecha de emision", r"fecha emision", r"fecha de factura", r"fecha factura", r"fecha de expedicion",
                r"fecha expedicion", r"fecha de operacion", r"fecha del recibo", r"fecha de cargo",
                r"fecha del presupuesto", r"fecha de compra", r"fecha"]
CLAVES_VENC = [r"fecha de vencimiento", r"vencimiento", r"\bvence\b", r"valido hasta", r"validez", r"fin de (la )?garantia",
               r"garantia hasta", r"fecha de renovacion", r"renovacion", r"fecha de efecto", r"periodo de cobertura",
               r"fin del contrato", r"duracion"]


def es_parcial(lp):
    """Línea de base, neto o IVA (no del total). «IVA incluido» no cuenta como parcial."""
    return bool(re.search(PARCIAL, re.sub(r"\b(iva|impuestos?|igic) (incl\w*|inc\b)", "", lp)))


def _importe_cerca(lineas_p, i):
    """Importe en la línea i o, si la etiqueta va sola, en la siguiente (o la de después)."""
    imps = importes_en(lineas_p[i])
    if imps:
        return imps[-1]
    for j in (i + 1, i + 2):
        if j < len(lineas_p) and not re.search(NO_ES_TOTAL, lineas_p[j]):
            imps = importes_en(lineas_p[j])
            if imps:
                return imps[0]
            if re.search(r"[a-z]{4,}", lineas_p[j]):  # ya es otra cosa
                break
    return None


def buscar_total(lineas_p):
    # 1) frases claras de «total a pagar» (en el orden de la lista)
    for clave in CLAVES_TOTAL_FUERTES:
        for i, lp in enumerate(lineas_p):
            if re.search(clave, lp) and not re.search(NO_ES_TOTAL, lp):
                x = _importe_cerca(lineas_p, i)
                if x is not None:
                    return x
    # 2) líneas «TOTAL …» que no sean bases, netos ni IVA: el mayor (el total final siempre es el más alto)
    totales = []
    for i, lp in enumerate(lineas_p):
        if re.search(r"\btotal\b", lp) and not re.search(NO_ES_TOTAL, lp) and not es_parcial(lp):
            x = _importe_cerca(lineas_p, i)
            if x is not None:
                totales.append(x)
    if totales:
        return max(totales)
    # 3) «importe», «precio», «prima» sueltos
    for clave in CLAVES_TOTAL_DEBILES:
        for i, lp in enumerate(lineas_p):
            if re.search(clave, lp) and not re.search(NO_ES_TOTAL, lp) and not es_parcial(lp):
                x = _importe_cerca(lineas_p, i)
                if x is not None:
                    return x
    todos = [x for lp in lineas_p if not re.search(NO_ES_TOTAL, lp) for x in importes_en(lp)]
    return max(todos) if todos else None


def buscar_fecha(lineas_p):
    for clave in CLAVES_FECHA:
        for i, lp in enumerate(lineas_p):
            if re.search(clave, lp) and not re.search(r"vencim|valido|validez|efecto|renovacion|nacimiento|hasta", lp):
                fs = fechas_en(lp) or (fechas_en(lineas_p[i + 1]) if i + 1 < len(lineas_p) else [])
                if fs:
                    return fs[0]
    for lp in lineas_p:
        if not re.search(r"vencim|valido|validez|hasta|nacimiento", lp):
            fs = fechas_en(lp)
            if fs:
                return fs[0]
    return None


def buscar_vencimiento(lineas_p):
    for clave in CLAVES_VENC:
        for i, lp in enumerate(lineas_p):
            if re.search(clave, lp):
                fs = fechas_en(lp) or (fechas_en(lineas_p[i + 1]) if i + 1 < len(lineas_p) else [])
                if fs:
                    return max(fs)
    return None


# ------------------------------------------------------------------ titular / cliente (nunca es el emisor)
ETIQ_CLIENTE = re.compile(
    r"datos (del |de la |de )?(cliente|titular|tomador|asegurado|destinatario|comprador|suministro)"
    r"|^(cliente|titular|tomador|asegurado|destinatario|comprador|facturar a|factura a|enviar a|para|senor|sr\.|sra\.)\b"
    r"|direccion de (suministro|envio|entrega)|dir\.? suministro|punto de suministro|^nombre( y apellidos)?\b")
NOMBRE_CLIENTE = re.compile(
    r"^(?:titular|cliente|tomador|asegurado|destinatario|comprador|para|nombre(?: y apellidos)?)"
    r"(?: del (?:contrato|seguro|recibo|suministro))?\s*[:.\-]\s*(.+)$")
CORTE_NOMBRE = re.compile(r"\s+(?:nif|n\.i\.f|dni|d\.n\.i|nie|cif|·|-|\|)\b.*$|[\s,]*\d.*$")
PERSONA_COMA = re.compile(r"^[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ' ]+,\s*[A-ZÁÉÍÓÚÑÜ][A-ZÁÉÍÓÚÑÜ' ]+$")  # «APELLIDOS, NOMBRE»


def zona_cliente(lineas, lineas_p):
    """Índices de las líneas que hablan del titular/cliente y nombres del cliente (texto plano)."""
    zona, nombres = set(), set()
    for i, lp in enumerate(lineas_p):
        if not ETIQ_CLIENTE.search(lp):
            continue
        zona.add(i)
        m = NOMBRE_CLIENTE.match(lp)
        if m:
            nom = CORTE_NOMBRE.sub("", m.group(1)).strip(" ,.:;")
            if len(nom) >= 5:
                nombres.add(nom)
        elif len(lp) <= 40:  # etiqueta sola («Datos del cliente»): lo de debajo es del cliente
            for j in range(i + 1, min(i + 6, len(lineas_p))):
                if re.search(r"factura|fecha|serie|n[º°o]\.? ?(de )?(factura|pedido|cliente)|concepto|importe|pago", lineas_p[j]):
                    break
                zona.add(j)
                if j == i + 1 and not re.search(r"\d", lineas_p[j]) and len(lineas_p[j].split()) >= 2:
                    nombres.add(lineas_p[j].strip(" ,.:;"))
    for i, ln in enumerate(lineas):
        if PERSONA_COMA.match(ln.strip()) and not RX_SOC_PUNTOS.search(ln) and not RX_SOC_SIGLAS.search(ln):
            nombres.add(lineas_p[i].strip())
    for i, lp in enumerate(lineas_p):
        if any(n in lp for n in nombres):
            zona.add(i)
    return zona, nombres


# ------------------------------------------------------------------ NIF / CIF
RE_CIF = re.compile(r"(?<![A-Z0-9])(?:ES)?([ABCDEFGHJNPQRSUVW])[- ]?(\d{7})[- ]?([0-9A-J])\b")
RE_DNI = re.compile(r"\b(\d{8})[- ]?([A-Z])\b")
RE_NIE = re.compile(r"\b([XYZ])[- ]?(\d{7})[- ]?([A-Z])\b")


def buscar_nif(lineas, zona=None):
    """NIF/CIF del emisor: primero el de una empresa fuera del bloque del cliente; el DNI del titular, lo último."""
    zona = zona or set()
    candidatos = []
    for i, ln in enumerate(lineas):
        u = ln.upper()
        lp = plano(ln)
        de_cliente = i in zona or bool(re.search(r"titular|cliente|tomador|asegurado|nombre|d\.?n\.?i", lp))
        for m in RE_CIF.finditer(u):
            candidatos.append((0 if not de_cliente else 2, "".join(m.groups())))
        for rx in (RE_DNI, RE_NIE):
            for m in rx.finditer(u):
                candidatos.append((1 if not de_cliente else 3, "".join(m.groups())))
    candidatos.sort(key=lambda x: x[0])
    return candidatos[0][1] if candidatos else ""


# ------------------------------------------------------------------ tipo
PRESUP_FUERTE = (r"presupuesto|cotizacion|propuesta de (renovacion|seguro)|aviso de renovacion|oferta de renovacion|"
                 r"proyecto de seguro|tarificacion|sin compromiso|informacion previa|nota informativa previa|"
                 r"precio de tu seguro|precio de su seguro|simulacion (de|del) (seguro|prestamo|hipoteca)")
PRESUP_DEBIL = r"\boferta\b|\bproyecto\b|tu precio|su precio"
GARANTIA = r"certificado de garantia|tarjeta de garantia|garantia del (producto|aparato|fabricante)|periodo de garantia"
TICKET = (r"\bticket\b|\btique\b|\btiquet\b|justificante de compra|ticket regalo|tique regalo|copia para el (titular|cliente)|"
          r"fecha expedicion/operacion")
FACTURA_FUERTE = (r"factura simplificada|factura completa|n[º°o]\.? ?(de )?factura|numero de factura|factura n[º°o]|"
                  r"fecha (de )?factura|total factura|serie\b.{0,15}factura")
RECIBO = r"\brecibo\b|aviso de cargo|adeudo|domiciliacion"
CONTRATO = r"\bcontrato de\b|contrato de arrendamiento|condiciones del contrato"


def es_poliza_de_verdad(todo):
    """Póliza = certificado de seguro, o condiciones particulares con su número, o nº de póliza + efecto + tomador."""
    num = re.search(r"n[º°o]\.? ?(de )?poliza|numero de poliza|poliza n[º°o]?\b|poliza:", todo)
    if re.search(r"certificado (de|del) seguro|suplemento a la poliza", todo):
        return True
    if re.search(r"condiciones particulares", todo) and num and not re.search(r"(en|segun) (las )?condiciones particulares", todo):
        return True
    return bool(num and re.search(r"fecha de efecto|efecto:", todo) and re.search(r"tomador", todo))


def detectar_tipo(lineas_p):
    cabecera = " ".join(lineas_p[:6])
    todo = " ".join(lineas_p)
    # 1) lo que pone en la cabecera manda (sin «póliza» suelta: en las facturas del agua o la luz es el nº de contrato)
    for tipo, rx in (("presupuesto", PRESUP_FUERTE), ("garantia", GARANTIA), ("recibo", r"\brecibo\b|aviso de cargo"),
                     ("factura", r"\bfactura\b|" + TICKET),
                     ("poliza", r"condiciones particulares|certificado (de|del) seguro|suplemento a la poliza|poliza de seguro"),
                     ("contrato", CONTRATO)):
        if re.search(rx, cabecera):
            return tipo
    # 2) si no, el texto entero (un presupuesto habla de pólizas: va primero)
    if re.search(PRESUP_FUERTE, todo):
        return "presupuesto"
    if re.search(GARANTIA, todo):
        return "garantia"
    if re.search(TICKET, todo) or re.search(FACTURA_FUERTE, todo):
        return "factura"
    if es_poliza_de_verdad(todo):
        return "poliza"
    for tipo, rx in (("recibo", RECIBO), ("factura", r"\bfactura\b"), ("contrato", CONTRATO),
                     ("presupuesto", PRESUP_DEBIL)):
        if re.search(rx, todo):
            return tipo
    if re.search(r"\bpoliza\b", todo) and re.search(r"tomador|asegurado|prima", todo):
        return "poliza"
    return "otro"


# ------------------------------------------------------------------ emisor
RX_SOC_PUNTOS = re.compile(r"(?<![A-Za-z])(S\.\s?A\.?(\s?U\.?)?|S\.\s?L\.?(\s?[UL]\.?)?|S\.\s?COOP\.?|C\.\s?B\.|"
                           r"Sociedad (An[oó]nima|Limitada|Cooperativa)( Unipersonal)?)(?![A-Za-z])", re.I)
RX_SOC_SIGLAS = re.compile(r"(?<![A-Za-z])(SAU|SLU|SLL|SA|SL)(?![A-Za-z])")
RX_ENTIDAD_PUBLICA = re.compile(r"entidad p[uú]blica empresarial|empresa municipal|ayuntamiento de|organismo aut[oó]nomo|"
                                r"consorcio de", re.I)
ETIQ_EMISOR = re.compile(r"^(?:emisor|emitida por|expedida por|raz[oó]n social|empresa|proveedor|vendedor|vendido por|"
                         r"prestador|arrendador)\s*:\s*(.+)$", re.I)
CORTE_EMPRESA = re.compile(r"\s+(?:C\.?I\.?F|N\.?I\.?F|VAT|Tel[ée]?f?|TLF|Tfno|P[aá]gina|P[aá]g\.|www\.|Inscrita|"
                           r"Registro Mercantil|Domicilio|C/|Calle|Avda|Plaza)\b.*$", re.I)
NO_ES_NOMBRE = (r"factura|recibo|presupuesto|poliza|fecha|garantia|ticket|tique|n[º°o]\.? |\d{3,}|\btotal\b|importe|"
                r"precio|cantidad|concepto|\biva\b|\bud\b|\buds\b|copia|pagina|https?:|www\.|@|^(c/|calle|avda|avenida|"
                r"paseo|plaza|pza|ctra|carretera)\b|datos|atencion al cliente|informacion|^\W*$|^\W*(espana|spain)\W*$")
DOMINIOS_GENERICOS = {"gmail", "hotmail", "outlook", "yahoo", "icloud", "google", "facebook", "instagram", "boe", "agpd",
                      "aepd", "consorseguros", "sede", "eoficina", "youtube", "linkedin", "twitter", "whatsapp"}


def _bonito(s):
    s = re.sub(r"\s+", " ", s).strip(" ,-:;|")
    if s.isupper():
        s = " ".join(w if RX_SOC_PUNTOS.fullmatch(w.strip(",")) or RX_SOC_SIGLAS.fullmatch(w.strip(","))
                     else (w.lower() if w.lower() in ("de", "del", "la", "las", "los", "y", "e") else w.capitalize())
                     for w in s.split())
    return s[:60]


def _razon_social(ln):
    """Si la línea tiene una razón social (S.A., S.L., entidad pública…), la devuelve recortada; si no, ''."""
    s = re.sub(r"\s+", " ", ln).strip()
    m = RX_SOC_PUNTOS.search(s) or RX_SOC_SIGLAS.search(s)
    if m:
        nombre = s[:m.end()]
    elif RX_ENTIDAD_PUBLICA.search(s):
        nombre = CORTE_EMPRESA.sub("", s)
    else:
        return ""
    nombre = re.sub(r"^.*:\s*", "", nombre) if ":" in nombre else nombre
    nombre = CORTE_EMPRESA.sub("", nombre).strip(" ,-")
    palabras = nombre.split()
    if len(palabras) < 2 or len(palabras) > 9 or not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", nombre):
        return ""
    return nombre


def _buscar_diccionario(texto_p, lista):
    """La marca que aparece antes en el papel (si empatan, la más larga; luego la primera de la lista)."""
    mejor = None
    for k, (rx, nombre, cat) in enumerate(lista):
        for m in re.finditer(rx, texto_p):
            if m.start() > 0 and texto_p[m.start() - 1] == "@":  # correo o web de otro (p. ej. el del cliente)
                continue
            clave = (m.start(), -len(m.group(0)), k)
            if mejor is None or clave < mejor[0]:
                mejor = (clave, m.group(0), nombre, cat)
            break
    if not mejor:
        return None
    _, txt, nombre, cat = mejor
    if nombre is None:
        nombre = " ".join(w.capitalize() if w not in ("de", "del", "la", "las", "los") else w for w in txt.split())
    return nombre, cat


def detectar_emisor(lineas, texto_p, zona=None):
    zona = zona or set()
    if lineas:
        texto_p = " ".join(plano(ln) for i, ln in enumerate(lineas) if i not in zona)
    # 0) marcas conocidas
    r = _buscar_diccionario(texto_p, EMISORES) or _buscar_diccionario(texto_p, EMISORES_GRUPO)
    if r:
        return r
    libres = [(i, ln) for i, ln in enumerate(lineas) if i not in zona]
    # 1) «Emisor: …», «Razón social: …»
    for i, ln in libres:
        m = ETIQ_EMISOR.match(ln.strip())
        if m and len(m.group(1).strip()) >= 3:
            return _bonito(CORTE_EMPRESA.sub("", m.group(1))), None
    # 2) en la cabecera: primero una razón social; si no, la primera línea con pinta de nombre (logotipo)
    for i, ln in libres:
        if i >= 8:
            break
        rs = _razon_social(ln)
        if rs and not re.search(NO_ES_NOMBRE, plano(rs)):
            return _bonito(rs), None
    for i, ln in libres:
        if i >= 8:
            break
        s = ln.strip()
        lp = plano(s)
        cortas = sum(1 for w in lp.split() if len(w) <= 3)
        if (len(s) >= 3 and re.search(r"[a-z]{3,}", lp) and not re.search(NO_ES_NOMBRE, lp)
                and not PERSONA_COMA.match(s) and not (len(lp.split()) >= 4 and cortas * 2 >= len(lp.split()))):
            rs = _razon_social(s)
            return _bonito(rs or s), None
    # 3) una razón social (S.A., S.L., entidad pública…) en cualquier sitio
    for i, ln in libres:
        rs = _razon_social(ln)
        if rs:
            return _bonito(rs), None
    # 4) la línea del CIF de empresa: lo que va delante, o la línea de encima
    for i, ln in libres:
        m = RE_CIF.search(ln.upper())
        if m:
            antes = re.sub(r"\b(C\.?I\.?F|N\.?I\.?F|VAT)\b\.?:?", "", ln[:m.start()], flags=re.I).strip(" :-,")
            if re.search(r"[A-Za-z]{3,}", antes) and not re.search(NO_ES_NOMBRE, plano(antes)):
                return _bonito(antes), None
            if i > 0 and (i - 1) not in zona and not re.search(NO_ES_NOMBRE, plano(lineas[i - 1])):
                return _bonito(lineas[i - 1]), None
    # 5) la web del emisor
    for i, ln in libres:
        for m in re.finditer(r"(?:www\.)?\b([a-z0-9][a-z0-9-]{2,})\.(?:com|es|net|org|eu|cat|info)\b", plano(ln)):
            if m.group(1) not in DOMINIOS_GENERICOS:
                return m.group(1).capitalize(), None
    return "", None


# ------------------------------------------------------------------ categoría
# Si el emisor no está en el diccionario, su nombre puede decir la categoría (p. ej. «Calzados Pepe» → Ropa).
# Ocio no: un gimnasio o una peluquería desconocidos se dejan en «Otros» hasta que ella lo diga.
CAT_POR_NOMBRE = ("ropa", "super", "restaurantes", "coche", "transporte", "compras", "salud", "suscripciones", "colegio")


def detectar_categoria(texto_p, cat_emisor):
    if cat_emisor in ("luz", "gas"):
        gas = len(re.findall(r"\bgas\b|gas natural", texto_p))
        luz = len(re.findall(r"electric|kwh|potencia|\bluz\b", texto_p))
        return "gas" if gas > luz else "luz"
    if cat_emisor:
        return cat_emisor
    # el IVA sale en todas las facturas: no es un impuesto «de casa»
    tp = re.sub(r"impuestos? (sobre el valor anadido|incluidos?)|\biva\b|\bigic\b", " ", texto_p)
    mejor, n_mejor = "otros", 0
    for cat, rx in _PALABRAS_RX:
        n = len(rx.findall(tp))
        if n > n_mejor:
            mejor, n_mejor = cat, n
    return mejor


def asunto(cat, texto_p, emisor):
    if cat == "seguros":
        for sub, pal in SEGURO_TIPOS:
            if any(p in texto_p for p in pal):
                return "seguro de " + sub
        return "seguro"
    if cat == "vivienda":
        return "alquiler" if "alquiler" in texto_p or "arrendamiento" in texto_p else "hipoteca"
    if cat == "impuestos":
        if re.search(r"\bibi\b|bienes inmuebles", texto_p):
            return "IBI"
        if re.search(r"traccion mecanica|impuesto (de|sobre) (la )?circulacion", texto_p):
            return "impuesto de circulación"
        return "impuestos y tasas"
    if cat == "suscripciones":
        return emisor or "suscripción"
    if cat == "telefono" and re.search(r"dominio|hosting|alojamiento web", texto_p):
        return "dominio web"
    if cat in ("otros", "salud", "coche", "super", "ocio", "compras", "restaurantes"):  # «Factura de salud» suena raro
        return ""
    return NOMBRE_CAT[cat].lower()


def hacer_concepto(tipo, asu, base=None):
    base = base or TIPO_CORTO.get(tipo, "Documento")
    if not asu:
        return base
    if asu.startswith("seguro") or asu[0].isupper():
        return f"{base} {asu}"
    return f"{base} de {asu}"


def analizar_texto(texto):
    lineas = [re.sub(r"\s+", " ", l).strip() for l in (texto or "").splitlines()]
    lineas = [l for l in lineas if l]
    lineas_p = [plano(l) for l in lineas]
    texto_p = " ".join(lineas_p)
    zona, _ = zona_cliente(lineas, lineas_p)
    tipo = detectar_tipo(lineas_p)
    emisor, cat_emisor = detectar_emisor(lineas, texto_p, zona)
    if not cat_emisor and emisor:
        c = clasificar_comercio(emisor)
        cat_emisor = c if c in CAT_POR_NOMBRE else None
    cat = detectar_categoria(texto_p, cat_emisor)
    fecha = buscar_fecha(lineas_p)
    venc = buscar_vencimiento(lineas_p) if tipo in ("poliza", "presupuesto", "contrato", "garantia") else None
    if venc and fecha and venc <= fecha:
        venc = None
    asu = asunto(cat, texto_p, emisor)
    ticket = tipo == "factura" and re.search(TICKET, texto_p) and not re.search(r"\bfactura\b", " ".join(lineas_p[:6]))
    return {
        "fecha": fecha.isoformat() if fecha else "",
        "emisor": emisor,
        "nif": buscar_nif(lineas, zona),
        "importe": buscar_total(lineas_p),
        "tipo": tipo,
        "categoria": cat,
        "vencimiento": venc.isoformat() if venc else "",
        "concepto": hacer_concepto(tipo, asu, "Ticket" if ticket else None),
    }


def clasificar_concepto(texto):
    """Para los gastos apuntados a mano: categoría por comercio, emisor o palabras."""
    cat = clasificar_comercio(texto)
    if cat:
        return cat
    tp = plano(texto)
    _, cat = detectar_emisor([], tp) if tp else ("", None)
    return detectar_categoria(tp, cat)


# ------------------------------------------------------------------ comercios (movimientos del banco y apuntes a mano)
# (patrón con límites de palabra sobre texto plano, categoría). Se mira en este orden: lo más concreto primero.
COMERCIOS = [
    # excepciones que deben ir antes que la marca general
    (r"repsol (luz|electricidad|gas|vivit)", "luz"), (r"amazon prime|prime video|primevideo", "suscripciones"),
    (r"zara home|el corte ingles", "compras"), (r"carrefour (e\.?s\.?|gasolinera|estacion)", "coche"),
    (r"movistar plus|movistar\+", "telefono"), (r"cepsa (luz|gas)|moeve (luz|gas)", "luz"),
    # correo profesional y servicios de internet (como los dominios y el alojamiento web: «Teléfono e internet»)
    (r"zoho|zoho mail|zoho corp\w*|google workspace|g suite|gsuite|proton ?mail|microsoft exchange", "telefono"),
    # suscripciones a programas y servicios en línea
    (r"elevenlabs|eleven labs|canva|capcut|notion|dropbox|grammarly|midjourney|manychat", "suscripciones"),
    # súper y droguería
    (r"primaprix|prima prix", "super"),
    # ropa y calzado
    (r"zara|bershka|stradivarius|pull ?(and|&|y)? ?bear|massimo dutti|oysho|lefties|primark|mango|kiabi|"
     r"h ?& ?m|hennes|springfield|cortefiel|women ?'?secret|desigual|sfera|shein|calzedonia|intimissimi|tezenis|"
     r"uterque|tendam|c ?& ?a|benetton|levi'?s|nike|adidas|foot ?locker|deichmann|merkal|skechers|"
     r"zapateria|calzados?|zapatos|boutique|moda|textil|ropa|lenceria|mercería|merceria", "ropa"),
    # comer fuera (bares, cafeterías, restaurantes y comida a domicilio)
    (r"cafeteria|cafe|cafes|bar|bares|restaurante|rest|restaurant|meson|taberna|tasca|cerveceria|pizzeria|"
     r"telepizza|dominos?|domino'?s|pizza hut|papa john'?s|burger king|mcdonald'?s?|mc donald'?s?|kfc|foster'?s hollywood|"
     r"ginos|vips|100 montaditos|cien montaditos|tgb|the good burger|starbucks|five guys|goiko|tagliatella|"
     r"lizarran|rodilla|pans ?(&|and)? ?company|la surena|taco bell|popeyes|tim hortons|costa coffee|udon|"
     r"glovo|just ?eat|uber ?eats|deliveroo|churreria|heladeria|kebab|wok|sushi|asador|marisqueria|bodega|"
     r"chiringuito|hamburgueseria|bocateria|creperia|gastrobar|vinoteca|cena|cenas|comida fuera|comer fuera|"
     r"desayunos?|meriendas?|tapas|pinchos", "restaurantes"),
    # coche y gasolina
    (r"repsol|cepsa|moeve|bp|galp|shell|ballenoil|plenoil|petronor|petroprix|avia|esso|disa|bonarea energia|"
     r"gasolinera|gasolina|gasoleo|diesel|carburantes?|estacion de servicio|e\.s\.|"
     r"autopista|peaje|via t|aparcamiento|parking|empark|telpark|saba|itv|taller|talleres|neumaticos?|"
     r"norauto|midas|feu vert|euromaster|lavado|lavacoches|recambios", "coche"),
    # súper y comida
    (r"mercadona|carrefour|lidl|dia|supermercados dia|alcampo|auchan|eroski|gadis|aldi|hipercor|consum|"
     r"bonpreu|caprabo|condis|ahorramas|masymas|mas y mas|froiz|family cash|simply|spar|coviran|bm supermercados|"
     r"uvesco|lupa|supersol|hiperber|el arbol|vegalsa|hiper|carniceria|fruteria|panaderia|pasteleria|"
     r"pescaderia|charcuteria|supermercado|hipermercado|alimentacion|ultramarinos|mercado|bonarea", "super"),
    # salud
    (r"farmacia|parafarmacia|farma|clinica|dental|dentista|optica|opticalia|general optica|multiopticas|"
     r"alain afflelou|hospital|quiron|vithas|hm hospitales|fisioterapia|fisio|podologo|podologia|psicolog\w*|"
     r"medico|laboratorio|analisis clinicos", "salud"),
    # compras (tiendas en general)
    (r"amazon|amzn|aliexpress|ebay|temu|miravia|ikea|leroy merlin|bricomart|bauhaus|brico ?depot|aki|"
     r"media ?markt|fnac|pccomponentes|worten|decathlon|tiger|flying tiger|primor|druni|sephora|"
     r"douglas|juguettos|toys ?r ?us|casa del libro|papeleria|libreria|ferreteria|bazar|game|conforama|"
     r"jysk|maisons du monde|el corte ingles|sprinter|perfumeria|drogueria|tienda|wallapop|vinted", "compras"),
    # suscripciones
    (r"netflix|spotify|disney|hbo|hbo max|max\.com|dazn|apple\.com|apple com|itunes|icloud|google one|"
     r"youtube premium|youtube|audible|filmin|crunchyroll|skyshowtime|atresplayer|openai|chatgpt|"
     r"microsoft 365|office 365|adobe|playstation plus|xbox|kindle unlimited|storytel|deezer|tidal", "suscripciones"),
    # ocio y caprichos
    (r"cines?|yelmo|cinesa|kinepolis|ocine|teatro|entradas|ticketmaster|museo|zoo|bolera|parque de atracciones|"
     r"booking|airbnb|hotel|hostal|apartamentos|gimnasio|gym|basic ?fit|mcfit|altafit|anytime fitness|holmes place|"
     r"vivagym|peluqueria|estetica|barberia|manicura|spa|loterias?|apuestas|bingo|casino|floristeria|"
     r"viajes|halcon|viajes el corte ingles|ocio", "ocio"),
    # recibos de casa por palabras (por si no hay factura)
    (r"comunidad de propietarios|com\.? prop|cdad\.? prop|comunidad prop", "comunidad"),
    (r"hipoteca|prestamo hipotecario|alquiler|arrendamiento", "vivienda"),
    (r"colegio|escuela|ampa|academia|guarderia|escuela infantil|comedor escolar|extraescolar|universidad|matricula", "colegio"),
    (r"agencia tributaria|aeat|hacienda|ayuntamiento|diputacion|tasa|tasas|dgt|trafico|seguridad social|tgss|ibi|multa", "impuestos"),
    (r"seguro|seguros|poliza", "seguros"),
    # dinero que se mueve (según el signo: si entra es ingreso; si sale, a «Otros»)
    (r"bizum|transferencia|transf|traspaso|cajero|reintegro|retirada( de)? efectivo|disposicion efectivo|"
     r"comision|comisiones|mantenimiento cuenta|nomina|pension", "otros"),
]
NUEVAS = [
    # préstamos, renting y la cuota de la tarjeta de crédito (no la hipoteca: esa es «vivienda»)
    (r"renting|santander consumer|consumer finance|financiacion|financiera|prestamo(?! hipotecario)|prestamos personales|"
     r"cajamar consumo|cofidis|cetelem|oney|aplazame|sequra|klarna|cargo mensual tarjeta( de)? credito|"
     r"cuota( de la)? tarjeta|tarjeta de credito \w+ \(?cuota|liquidacion( de la)? tarjeta( de)? credito", "financiacion"),
    # deporte y gimnasio
    (r"gimnasios?|gym|basic ?fit|mcfit|vivagym|viva gym|altafit|anytime fitness|dreamfit|go ?fit|synergym|fitness|"
     r"duet fit|crossfit|pilates|yoga|padel|piscina|polideportivo|club deportivo|deportes?", "belleza"),  # Mapi: junto a belleza
    # belleza y cuidado personal
    (r"peluqueria|peluqueros|estetica|centro de estetica|barberia|manicura|depilacion|rituals|rituals ?cosmetics|"
     r"primor|druni|sephora|douglas|kiko|kiko milano|perfumeria|cosmetica|cosmeticos|icaria|yves rocher|"
     r"the body shop|lush|belleza|cuidado personal|spa", "belleza"),
]
_NUEVAS_RX = [(re.compile(r"(?<![a-z0-9])(?:" + rx + r")(?![a-z0-9])"), cat) for rx, cat in NUEVAS]
_COMERCIOS_RX = [(re.compile(r"(?<![a-z0-9])(?:" + rx + r")(?![a-z0-9])"), cat) for rx, cat in COMERCIOS]
_EMISORES_RX = [(re.compile(rx), cat) for rx, _, cat in EMISORES]
_PALABRAS_RX = [(cat, re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(p) for p in pal) + r")(?![a-z0-9])"))
                for cat, pal in PALABRAS]


# ------------------------------------------------------------------ diccionario grande de comercios (comercios_es.json)
RUTA_COMERCIOS = Path(__file__).resolve().parent / "comercios_es.json"
# Lo que el banco pone delante del comercio: «COMPRA TARJ. 1234XXXXXXXX5678», «PAGO CON TARJETA», «APPLE PAY»…
PREFIJOS_BANCO = re.compile(
    r"^(?:compras?|pagos?|cargos?|adeudos?|recibos?|operacion|op|tarj|tarjeta|tarjetas|con|en|de|del|por|tpv|ct|cr|"
    r"contactless|sin contacto|movil|apple pay|google pay|samsung pay|internet|comercio|transaccion|credito|debito|"
    r"visa|mastercard|maestro|n[ºo°]?|num|ref|fecha|valor|terminal|comercio electronico|compra web|"
    # pasarelas de pago que van delante del comercio: «SUMUP *CHURROS LOLA», «ZTL*PANADERIA», «PAYPAL *EBAY», «SQ *…»
    r"sumup|sum up|zettle|izettle|ztl|sq|sp|paypal|pp|stripe|redsys|tpv virtual)\b\.?\s*\*?\s*:?\s*")
RE_TARJETA_NUM = re.compile(r"\b\d{4,6}[x*•]{4,}[\dx*•]*\b|[x*•]{4,}\d*|\*+\s?\d{2,}|\b\d{12,19}\b")
FORMAS_JURIDICAS = {"sl", "sa", "slu", "sau", "sll", "slne", "sc", "scoop", "coop", "cb", "sociedad", "limitada", "anonima"}
# Gasolineras abreviadas como salen en los extractos: «E.S. VALLADOLID SUR», «EE.SS.», «E/S», «EST. SERV.», «A.S.»…
# «ES» solo vale como palabra suelta al principio (tras quitar los prefijos) seguida de un nombre, sin cifras (no un IBAN).
GAS_INICIO = re.compile(r"^(?:e\.\s?s\.?|e\s?s\.|ee\.?\s?ss\.?|eess|e\s?/\s?s|est\.?\s?serv(?:icio)?\.?|a\.\s?s\.|"
                        r"es(?=\s+[a-z]{2,}))(?=[\s,.:-]|$)")
GAS_PALABRAS = re.compile(r"(?<![a-z0-9.])(?:e\.\s?s\.|ee\.\s?ss\.?|eess|e/s|est\.\s?serv\.?|estacion (?:de )?servicio|"
                          r"estaciones de servicio|area (?:de )?servicio|gasolineras?|gasoleos?|gasoil|gasoleo|carburantes?|"
                          r"combustibles?|surtidor(?:es)?|autoservicio 24 ?h(?:oras)?)(?![a-z0-9])")


def normalizar_comercio(texto):
    """«COMPRA TARJ. 5402XXXXXXXX1234 MERCADONA VALLADOLID 1234 S.A.» -> «mercadona valladolid» (minúsculas, sin
    tildes, sin prefijos del banco, sin tarjetas, sin números ni forma jurídica). Devuelve (con signos, sin signos)."""
    t = re.sub(r"\s+", " ", plano(texto)).strip()
    t = RE_TARJETA_NUM.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip(" -:,")
    for _ in range(6):
        nuevo = PREFIJOS_BANCO.sub("", t).strip(" -:,")
        if nuevo == t or not re.search(r"[a-z]{2,}", nuevo):
            break
        t = nuevo
    limpio = re.sub(r"[^a-z0-9]+", " ", t)
    # fuera números de tienda y referencias («1234», «12b», «p1234567»), pero no marcas como «q8» u «o2»
    palabras = [p for p in limpio.split() if not p.isdigit() and not re.fullmatch(r"\d+[a-z]{1,2}|[a-z]{1,2}\d{3,}", p)]
    # formas jurídicas: «s l», «s a u», «sl», «s coop»… al final o sueltas
    out, i = [], 0
    while i < len(palabras):
        p = palabras[i]
        if p == "s" and i + 1 < len(palabras) and palabras[i + 1] in ("l", "a", "c", "coop"):
            i += 2
            if i < len(palabras) and palabras[i] in ("u", "l"):
                i += 1
            continue
        if p in FORMAS_JURIDICAS:
            i += 1
            continue
        out.append(p)
        i += 1
    return t, " ".join(out)


def _cargar_comercios():
    """{nombre normalizado: categoría} y las pistas por palabra. Si el archivo falta, la app sigue con las reglas."""
    import json
    nombres, pistas, conflictos = {}, [], []
    try:
        datos = json.loads(RUTA_COMERCIOS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("No he podido leer comercios_es.json:", e)
        return nombres, pistas, conflictos, 1
    for g in datos.get("grupos", []):
        cat = g.get("categoria")
        if cat not in NOMBRE_CAT:
            continue
        for c in g.get("comercios", []):
            k = " ".join(re.sub(r"[^a-z0-9]+", " ", plano(c)).split())
            if not k:
                continue
            if k in nombres and nombres[k] != cat:
                conflictos.append((k, nombres[k], cat))  # gana el primero (el más concreto va antes en el archivo)
                continue
            nombres[k] = cat
    for cat, pal in (datos.get("pistas") or {}).items():
        if cat in NOMBRE_CAT and pal:
            ks = sorted({" ".join(re.sub(r"[^a-z0-9]+", " ", plano(p)).split()) for p in pal} - {""}, key=len, reverse=True)
            # palabra entera, también en plural («bares», «cafeterias»)
            pistas.append((cat, re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(p) for p in ks) + r")(?:e?s)?(?![a-z0-9])")))
    largo = max((len(k.split()) for k in nombres), default=1)
    return nombres, pistas, conflictos, largo


DICCIONARIO, PISTAS, CONFLICTOS_DICCIONARIO, _LARGO = _cargar_comercios()


def buscar_en_diccionario(normalizado):
    """El nombre más largo del diccionario que aparece como palabras enteras (a igual largo, el que va antes)."""
    pal = normalizado.split()
    for n in range(min(_LARGO, len(pal)), 0, -1):
        for i in range(len(pal) - n + 1):
            cat = DICCIONARIO.get(" ".join(pal[i:i + n]))
            if cat:
                return cat
    return None


def clasificar_comercio(texto):
    """Categoría de un movimiento del banco o de un apunte a mano. None si no lo sabemos (=> «En duda»).
    Orden: gasolineras abreviadas -> diccionario de comercios -> reglas de siempre -> pistas por palabras -> emisores."""
    tp = re.sub(r"\s+", " ", plano(texto)).strip()
    if not tp:
        return None
    con_signos, norm = normalizar_comercio(texto)
    if GAS_INICIO.search(con_signos) or GAS_PALABRAS.search(con_signos):
        return "coche"
    # Categorías que pidió Mapi el 16/11/2026: van antes que el diccionario (que las metía en «Compras» u «Ocio»)
    for rx, cat in _NUEVAS_RX:
        if rx.search(tp):
            return cat
    cat = buscar_en_diccionario(norm)
    if cat:
        return cat
    for rx, cat in _COMERCIOS_RX:
        if rx.search(tp):
            return cat
    for cat, rx in PISTAS:
        if rx.search(norm):
            return cat
    for rx, cat in _EMISORES_RX:
        if rx.search(tp):
            return cat
    for cat, rx in _PALABRAS_RX:
        if rx.search(tp):
            return cat
    return None
