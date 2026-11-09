"""Tucumán Ahorra: baja la base SEPA más reciente, filtra Tucumán y genera sepa_tucuman.json.
Sirve igual en Colab y en GitHub Actions. Si existe la carpeta plantillas/, también arma la web en docs/."""
import glob, gzip, io, json, os, re, statistics, sys, time, zipfile
from datetime import datetime
from email.utils import parsedate_to_datetime
import pandas as pd
import requests

# ---- Clasificador de sectores ----
import unicodedata

# (código, nombre, regex). El orden es la prioridad: gana la primera que coincide.
SECTORES = [
 ("mas", "Mascotas", r"\b(perros?|gatos?|mascotas?|balanceado|pedigree|whiskas|dog chow|cat chow|piedras? sanitarias?|excellent|royal canin|sieger|purina|pro plan|canin|felin|gatitos?|cachorros?)\b"),
 ("bby", "Bebés", r"\b(panal|panales|toallitas humedas|mamaderas?|chupetes?|biberon|babysec|huggies|pampers|estrella baby|nutrilon|bebes?|baby|sonajero|cochecito|fisher|prenatal)\b"),
 ("rop", "Ropa y calzado", r"\b(pant|pantalon|pantalones|boxer|camp|campe|campera|camperas|bermudas?|sandalias?|jogger|remeras?|shorts?|medias?|buzos?|pijamas?|jeans?|denim|cinturon|calzas?|zapatillas?|ojotas?|chinelas?|vestidos?|camisas?|cardigan|chaleco|traje|slips?|corpino|bikini|mallas?|gorras?|gorros?|bufanda|pantuflas?|zapatos?|botas?|botines?|mochilas?|bolsos?|carteras?|billeteras?|rinonera|lenceria|musculosa|polleras?|sacos?|sweater|sueter|camisetas?|enterito|cargo|hg|ropa|calzado|setx|corp|surt|check|liso)\b"),
 ("ele", "Electro y tecnología", r"\b(airfryer|freidora|licuadora|microondas|televisor|tv|heladera|ventilador|cafetera|pava electrica|plancha|aspiradora|notebook|celular|parlante|auriculares?|batidora|tostadora|cortapelo|secador|afeitadora|smart|aa|inv|calefactor|estufa|horno|anafe|lavarropas?|lavavajillas|freezer|termotanque|mouse|teclado|monitor|cargador|usb|pendrive|tablet|consola|joystick|camara|cooler|pilas?|bateria|led|radio|multiprocesadora|exprimidor|procesadora|sandwichera|waflera|yogurtera|hervidor|electrico|electrica|bluetooth|wifi|inalambrico|reloj|philco|bgh|samsung|lg|noblex|atma|liliana|peabody|oster|moulinex|philips|sony|jbl|motorola|xiaomi|tcl|hisense|whirlpool|drean|gafa|patrick|longvie|gadnic|yelmo|winco)\b"),
 ("alc", "Vinos y alcohol", r"\b(cervezas?|cerv|vinos?|fernet|whisky|vodka|gin|licor|sidra|espumante|champagne|aperitivo|campari|aperol|gancia|malbec|cabernet|chardonnay|tequila|ron|brahma|quilmes|stella artois|heineken|budweiser|cinzano|vermut|vermouth|syrah|torrontes|merlot|tannat|bonarda|pinot|rosado|brut|spritz|amargo serrano|amargo obrero|bitter)\b"),
 ("beb", "Bebidas", r"\b(gaseosas?|jugos?|soda|energizante|isotonica|coca cola|sprite|fanta|pepsi|seven up|7up|bebidas?|tonica|speed|monster|gatorade|powerade|ades|baggio|cepita|levite|terma|limonada|nectar|aquarius|schweppes|manaos|cunnington|villa del sur|villavicencio|aguas?|clight|tang)\b(?!\s*(oxigenada|colonia|micelar|de rosas|perfumada|de tocador))"),
 ("lac", "Lácteos y fiambres", r"\b(leche|leches|yogur|yogurt|yog|quesos?|queso|manteca|mant|ricota|muzzarella|mozzarella|fiambres?|jamon|salame|huevos?|postres?|flan|casancrem|margarina|mortadela|paleta cocida|bondiola|salchichon|panceta|cremoso|port salut|sardo|reggianito|provolone|untable|serenisima|sancor|ilolay|danone|yogurisimo|crema de leche|crema doble|crema para batir|chantilly|lomito ahumado|leberwurst|pate de foie)\b"),
 ("car", "Carnes y congelados", r"\b(hamburguesas?|milanesas?|pollo|carne|carnes|salchichas?|congelad[oa]s?|helados?|nuggets?|pizzas?|pescado|merluza|cerdo|bife|asado|vacuno|patamuslo|suprema|empanadas?|tapas? de|tartas?|lomo|chorizo|morcilla|vacio|picada|rebozad[oa]s?|bastoncitos?|medallones?|ravioles|noquis|sorrentinos|capeletinis|agnolotti|lasagna|canelones|bastones|camarones?|calamar|mariscos?)\b"),
 ("sna", "Snacks y golosinas", r"\b(galletitas?|galle|alfajor|alfajores|alf|chocolates?|choc|snacks?|papas fritas|papitas|chicles?|gum|caramelos?|golosinas?|turron|barras? de cereal|barritas?|obleas?|bon o bon|havanna|bombon|bombones|mani|chizitos?|palitos|tostaditas|crackers?|rosquitas?|bizcochos?|budin|magdalenas?|medialunas?|mantecol|gomitas|chupetin|pochoclo|palomitas|nachos|oreo|pepitos|terrabusi|bagley|arcor|cofler|milka|cadbury|kinder|kin bueno|bueno dark|ferrero|lindt|aguila|rocklets|sugus|mogul|mentos|halls|beldent|topline|trident|frutos secos|almendras|nueces|pasas|castanas|pistachos|mix|cereales?|tofi)\b"),
 ("lim", "Limpieza", r"\b(detergentes?|lavandina|limpiadores?|limpia|suavizantes?|jabon en polvo|jabon liquido|lavarropas|desinfectantes?|esponjas?|trapos?|papel higienico|rollos? de cocina|rollos? cocina|insecticidas?|desodorante de ambiente|aromatizador|aromatizantes?|lustra|lustramuebles|trapeador|escobas?|escobillon|baldes?|antigrasa|desengrasante|quitamanchas?|cif|ayudin|ala|skip|drive|ariel|poett|mr musculo|lysoform|raid|repelente|bolsas? (de )?(residuo|consorcio|camiseta|basura)|servilletas?|papel de cocina|film adherente|papel aluminio|ecovita|vim|cloro|destapacanerias|glade|morley|repuesto|microf|microfibra|pano|panos|rejilla|franela|guantes? (de )?(latex|goma|limpieza))\b"),
 ("hig", "Perfumería e higiene", r"\b(shampoo|champu|acondicionador|jabon|jabones|desodorante|antitranspirante|crema dental|pasta dental|dental|cepillo dental|cepillos?|toallitas?|algodon|afeitar|protectores?|tampones?|enjuague|crema corporal|crema facial|crema de manos|crema de enjuague|crema para peinar|rexona|dove|colgate|gillette|always|kotex|nivea|pantene|sedal|elvive|loreal|maquillaje|rimel|labial|esmalte|perfume|colonia|locion|gel|fijador|tintura|coloracion|talco|hisopos?|preservativos?|lubricante intimo|serum|mascara|tonico|crema|solar|bronceador|depilatoria|cuchillas?|apositos?|curitas?|alcohol en gel|alcohol etilico|alcohol fino|agua oxigenada|barbijo|termometro|panuelos?|gasa|vendas?|body splash|splash|bano de crema|vedetina|calipso|ojo ros|hav|vivere)\b"),
 ("jug", "Juguetes y librería", r"\b(juguetes?|muneca|munecas|lego|pelotas?|didactico|disfraz|puzzle|rompecabezas|peluche|bluey|stitch|hot wheels|barbie|cuadernos?|lapiz|lapices|lapicera|lapiceras|birome|biromas|marcadores?|resaltador|carpetas?|hojas?|tijeras?|goma de borrar|plastilina|crayones?|acuarelas?|libros?|albumes?|figuritas|juegos?|juego de|auto a escala|pistola de agua|slime|play doh|monopoly|cartas|ajedrez|armamundo|trencito|antiparras|frases|sorpresa|mochila escolar|escolar|stickers?|globos?|cotillon|pinata)\b"),
 ("dec", "Decoración y fiestas", r"\b(velas?|difusor|difusores|decoracion|decor|deco|cuadros?|espejos?|floreros?|portarretratos?|adornos?|navidad|navidenos?|arbol|guirnaldas?|incienso|home fragrance|cojin|cojines|almohadon|almohadones|estatua|figura|velador|home|ginger)\b"),
 ("fer", "Ferretería y auto", r"\b(herramientas?|taladro|destornillador|llaves?|martillo|alicates?|tornillos?|clavos?|pintura|rodillo|pincel|adhesivo|silicona|cinta|mangueras?|candado|cerradura|cables?|lamparas?|lamparita|focos?|aceite (de )?motor|lavaautos|anticongelante|refrigerante|limpiaparabrisas|pileta|piscina|jardin|riego|sellador|cemento|soldadora|broca|pinza|nivel|cutter|escalera|carretilla|multimetro|extension|zapatilla electrica|prolongador|enchufe|ficha|auto|moto|cubierta|ferreteria)\b"),
 ("hog", "Hogar y bazar", r"\b(ollas?|sarten|sartenes|cuchillos?|vasos?|tazas?|platos?|organizador|organizadores|tupper|tuppers|tapper|hermetico|hermeticos|herm|frascos?|coladores?|ralladores?|abrelatas|jarras?|botellas?|termos?|mates?|bombillas?|cubiertos|cucharas?|tenedores?|fuentes?|bandejas?|moldes?|cacerolas?|bowl|ensaladera|escurreplatos|sabanas?|toallas?|toallones?|frazadas?|mantas?|cortinas?|alfombras?|almohadas?|colchon|acolchado|cubrecama|fundas?|cestos?|perchero|perchas?|canastos?|balanza|set comedor|mesas?|sillas?|sillones?|muebles?|estantes?|camas?|manteles?|repasadores?|individuales|posavasos|bazar|vajilla|copas?|cafetera|tarro|tarros|tapa|tapas|cocot|caja|cajas|cuchillas|bano|madera|metal|mini|pack|set)\b"),
 ("fru", "Frutas y verduras", r"\b(bananas?|manzanas?|naranjas?|mandarinas?|limon|limones|tomates?|papas?|cebollas?|zanahorias?|lechugas?|zapallos?|ajos?|pimientos?|paltas?|frutillas?|uvas?|peras?|batatas?|choclos?|verduras?|hortalizas?|frutas?)\b"),
 ("alm", "Almacén", r"\b(aceites?|arroz|fideos?|harinas?|azucar|yerba|cafe|te|conservas?|atun|pure|salsas?|tomate|mayonesa|ketchup|mermeladas?|dulces?|cereal|vinagre|lentejas?|polenta|premezcla|aderezos?|caldos?|sopas?|gelatinas?|bizcochuelo|sal|pan rallado|rebozador|garbanzos?|porotos?|arvejas?|duraznos?|pate|picadillo|aceitunas?|pan|miel|edulcorante|stevia|cacao|avena|granola|semillas?|especias?|oregano|pimienta|condimentos?|comino|pimenton|cubitos?|maizena|almidon|levadura|esencia|colorante|sin tacc|legumbres?|saquitos|capsulas?|nespresso|dolce gusto|membrillo|sardinas?|caballa|anchoas?|picante|chimichurri|mostaza|soja|tallarin|tallarines|spaghetti|mostachol|tirabuzon|coditos?|ravioli|fecula|maiz|trigo|pasta|lasagne|alm|cra rem ceb|vainilla)\b"),
]
PRE = re.compile(r"\b(dulce de leche|premezcla|prepizza|salsas?|aceites? (de )?(girasol|oliva|maiz|mezcla|soja|uva|coco)|aceite comestible|yerba mate|yerba|arroz|fideos|harina|azucar)\b")
COMP = [(k, re.compile(p)) for k, _, p in SECTORES]
NOMBRES = {k: n for k, n, _ in SECTORES}
NOMBRES["otr"] = "Otros"


def _norm(s):
    return " " + unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower() + " "


# Si el producto EMPIEZA con un objeto no alimenticio, manda eso (ej. "PLATO POSTRE", "VASO CERV")
PRIMERA = {
 "hog": "plato platos vaso vasos taza tazas set juego sabanas sabana toalla toallon mantel frazada cuchara cuchillo cuchillos sarten olla jarra bowl bandeja fuente colador organizador canasto cesto botella termo pava mate",
 "jug": "peluche pistola lanzador maquina muneca munecas pelota juguete disfraz globo resaltador",
 "ele": "cable cargador auricular auriculares parlante",
 "hig": "mango toallitas",
 "dec": "vela velas difusor aromatizador sahumerio maceta",
 "lim": "limpiador guantes guante bolsas bolsa rejilla servilleta servilletas",
 "rop": "valija bandolera",
}
_PRIM = {w: k for k, ws in PRIMERA.items() for w in ws.split()}
PRE_HIG = re.compile(r"\b(toalla (fem|femenina|higienica)|toallas? femeninas?|ladysoft|lina|nosotras|siempre libre|protector diario)\b")
FALL = [
 ("rop", r"\b(negro|negra|gris|blanco|blanca|verde|azul|rojo|rosa|beige|celeste|marron|violeta|amarillo|naranja|bordo|crudo|lila|fucsia|color|colores|rayas|liso|lisa|estampado|talle)\b"),
 ("dec", r"\b(maceta|sahumerio|regalo|navid|pino|lavanda)\b"),
 ("fer", r"\b(pala|cabo|rollo|block|goma)\b"),
 ("hog", r"\b(jarro|acero|plastico|vidrio|ceramica|porcelana|bambu)\b"),
]
FALL += [
 ("fru", r"\b(brocoli|coliflor|orquideas?|acelga|espinaca|rucula|hongos?)\b"),
 ("hig", r"\b(cera|depil\w*|deo|loc|kids|panty|sol|vincha|corta unas|maquillaje|gloss\w*|crema)\b"),
 ("rop", r"\b(soutien|bretel|are|ropa)\b"),
 ("jug", r"\b(camion|playset|paw patrol|cartt|rc|nerf|toy\w*|plush)\b"),
 ("lac", r"\b(camemb\w*|fetas|burrata|cheddar|gouda|brie|roquefort)\b"),
 ("alm", r"\b(cast|aceto|endulzante|choritos?|sobres|zucra|pate|bud|ddl|bimbo|tostad\w*|caju)\b"),
 ("hog", r"\b(cesta|cuenco|org|cuch|utens|embudo|parrilla|inodoro|cocina|centrifuga|baul|acol|jacquard|pizzeras?|escobillo|molde)\b"),
 ("fer", r"\b(wd|lava parabrisas|impregnante|lubricante|lampara|parabrisas|quimbat)\b"),
]
FALLC = [(k, re.compile(p)) for k, p in FALL]


def sector(nombre, marca=""):
    s = _norm(nombre)
    if PRE.search(s):
        return "alm"
    if PRE_HIG.search(s):
        return "hig"
    w = s.split()
    if w and w[0] in _PRIM:
        return _PRIM[w[0]]
    for k, rx in COMP:
        if rx.search(s):
            return k
    for k, rx in FALLC:
        if rx.search(s):
            return k
    return "otr"

# ---- fin clasificador ----

BASE = "https://datos.produccion.gob.ar/dataset/6f47ec76-d1ce-4e34-a7e1-621fe9b1d0b5/resource/"
DIAS = {
    "lunes": "0a9069a9-06e8-4f98-874d-da5578693290",
    "martes": "9dc06241-cc83-44f4-8e25-c9b1636b8bc8",
    "miercoles": "1e92cd42-4f94-4071-a165-62c4cb2ce23c",
    "jueves": "d076720f-a7f0-4af8-b1d6-1b99d5a90c14",
    "viernes": "91bc072a-4726-44a1-85ec-4a8467aad27e",
    "sabado": "b3c3da5d-213d-41e7-8d74-f23fda0a3c30",
    "domingo": "f8e75128-515a-436e-bf8d-5c63a62f2005",
}
H = {"User-Agent": "Mozilla/5.0"}
PROVINCIA = "AR-T"  # Tucumán
OPT = dict(sep="|", dtype=str, encoding_errors="replace", on_bad_lines="skip")
K = ["id_comercio", "id_bandera", "id_sucursal"]


def url_dia(d):
    return BASE + DIAS[d] + "/download/sepa_" + d + ".zip"


def elegir_dia():
    mejor, fecha_mejor = None, None
    for d in DIAS:
        try:
            r = requests.head(url_dia(d), timeout=30, allow_redirects=True, headers=H)
            lm = r.headers.get("Last-Modified")
            f = parsedate_to_datetime(lm) if lm else None
            print("  ", d, r.status_code, lm)
            if r.status_code == 200 and f and (fecha_mejor is None or f > fecha_mejor):
                mejor, fecha_mejor = d, f
        except Exception as e:
            print("  ", d, "X", type(e).__name__)
    if mejor is None:
        sys.exit("No se pudo consultar ningún día. El servidor puede estar caído o bloqueando la conexión.")
    return mejor


def descargar(d, destino):
    for intento in range(1, 4):
        try:
            with requests.get(url_dia(d), stream=True, timeout=(30, 300), headers=H) as r:
                r.raise_for_status()
                with open(destino, "wb") as f:
                    for ch in r.iter_content(1024 * 1024):
                        f.write(ch)
            return
        except Exception as e:
            print("Intento", intento, "falló:", type(e).__name__)
            time.sleep(10)
    sys.exit("No se pudo descargar el archivo.")


def procesar(path):
    z = zipfile.ZipFile(path)
    nombres = z.namelist()
    fecha = None
    for n in nombres:
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", n)
        if m:
            fecha = m.group(3) + "/" + m.group(2) + "/" + m.group(1)
            break
    prods, rotos, usados = [], 0, 0
    for n in [x for x in nombres if x.endswith(".zip")]:
        try:
            zi = zipfile.ZipFile(io.BytesIO(z.read(n)))
            nom = {x.lower(): x for x in zi.namelist()}
            com = pd.read_csv(zi.open(nom["comercio.csv"]), **OPT)
            suc = pd.read_csv(zi.open(nom["sucursales.csv"]), **OPT)
        except Exception:
            rotos += 1
            continue
        t = suc[suc["sucursales_provincia"].astype(str).str.upper() == PROVINCIA]
        if t.empty:
            continue
        t = t.merge(com[["id_comercio", "id_bandera", "comercio_bandera_nombre"]],
                    on=["id_comercio", "id_bandera"], how="left")
        claves = t[K + ["comercio_bandera_nombre"]]
        try:
            for ch in pd.read_csv(zi.open(nom["productos.csv"]), chunksize=200000, **OPT):
                f = ch.merge(claves, on=K)
                if len(f):
                    prods.append(f)
            usados += 1
        except Exception:
            rotos += 1
    if not prods:
        sys.exit("No se encontraron precios de Tucumán.")
    print("Comercios con Tucumán:", usados, "| archivos dañados:", rotos)
    return pd.concat(prods), fecha


def a_json(P, fecha, salida):
    d = P.copy()
    d["precio"] = pd.to_numeric(d["productos_precio_lista"], errors="coerce")
    d["promo"] = pd.to_numeric(d["productos_precio_unitario_promo1"], errors="coerce")
    d = d[d["precio"] > 0]
    d["cad"] = d["comercio_bandera_nombre"]
    d["ean"] = d["id_producto"]
    chains = sorted(d["cad"].dropna().unique())
    primero = lambda s: s.value_counts().index[0]
    info = d.groupby("ean").agg(n=("productos_descripcion", primero), m=("productos_marca", primero))
    mins = d.groupby(["ean", "cad"])["precio"].min().unstack().reindex(columns=chains)
    tabla = info.join(mins, how="inner")
    maxd = d.groupby(["ean", "cad"])["precio"].max().unstack().reindex(columns=chains).to_dict("index")
    rows = []
    for ean, r in tabla.iterrows():
        precios = [None if pd.isna(r[c]) else int(round(r[c])) for c in chains]
        mm = []
        for i, c in enumerate(chains):
            v = maxd.get(ean, {}).get(c)
            lo = precios[i]
            mm.append(None if (v is None or pd.isna(v) or lo is None or int(round(v)) <= lo) else int(round(v)))
        rows.append([ean, str(r["n"])[:70], str(r["m"])[:20], precios, mm, sector(str(r["n"]), str(r["m"]))])
    pr = d[(d["promo"] > 0) & (d["promo"] < d["precio"])]
    pr = pr.groupby(["ean", "cad"]).agg(p=("promo", "min"), l=("productos_leyenda_promo1", "first"))
    promos = {}
    for (ean, cad), r in pr.iterrows():
        promos.setdefault(ean, {})[str(chains.index(cad))] = [int(round(r["p"])), str(r["l"])[:500]]
    out = {"fecha": fecha, "cadenas": chains, "productos": rows, "promos": promos}
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("Cadenas:", chains)
    print("Productos:", len(rows), "| con promo:", len(promos))
    print("Archivo:", salida, "%.1f MB" % (os.path.getsize(salida) / 1e6))
    return out


def a_fecha(s):
    return datetime.strptime(s, "%d/%m/%Y")


def ranking(out, prev):
    """Compara los precios actuales con un snapshot anterior (mediana del cambio entre cadenas)."""
    chains, pc = out["cadenas"], prev["cadenas"]
    idx = [(i, pc.index(c)) for i, c in enumerate(chains) if c in pc]
    res, todos_med = [], []
    for r in out["productos"]:
        po = prev["p"].get(r[0])
        if not po:
            continue
        ch, antes, ahora = [], [], []
        for i, j in idx:
            a, b = po[j], r[3][i]
            if a and b:
                ch.append((b - a) / a * 100)
                antes.append(a)
                ahora.append(b)
        if len(ch) < 3:
            continue
        med = statistics.median(ch)
        todos_med.append(med)
        if abs(med) < 1 or abs(med) > 40:  # sin cambio real o posible error de carga
            continue
        res.append([r[0], r[1], round(med, 1), min(antes), min(ahora), len(ch)])
    if not todos_med:
        return None
    todos = statistics.median(todos_med)
    suben = sorted([x for x in res if x[2] > 0], key=lambda x: -x[2])[:500]
    bajan = sorted([x for x in res if x[2] < 0], key=lambda x: x[2])[:500]
    return {"desde": prev["fecha"], "hasta": out["fecha"], "n": len(todos_med), "cambiaron": len(res),
            "mediana": round(todos, 2), "suben": suben, "bajan": bajan}


def completar_historial(out, salida, carpeta="historial", max_snap=10):
    """Guarda el snapshot de hoy y calcula el ranking contra el de hace ~7 días."""
    os.makedirs(carpeta, exist_ok=True)
    hoy = a_fecha(out["fecha"])
    snaps = []
    for f in glob.glob(os.path.join(carpeta, "*.json.gz")) + glob.glob("*.json.gz"):
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                s = json.load(fh)
            snaps.append((a_fecha(s["fecha"]), s, f))
        except Exception:
            pass
    previos = [x for x in snaps if x[0] < hoy]
    if previos:
        # el más cercano a 7 días antes; si no hay, el más viejo
        ref = min(previos, key=lambda x: abs((hoy - x[0]).days - 7))
        out["ranking"] = ranking(out, ref[1])
        print("Ranking contra", ref[1]["fecha"], "->", (out["ranking"] or {}).get("n"), "productos")
    else:
        out["ranking"] = None
        print("Sin snapshot anterior: el ranking empieza cuando haya dos fechas.")
    snap = {"fecha": out["fecha"], "cadenas": out["cadenas"], "p": {r[0]: r[3] for r in out["productos"]}}
    nombre = os.path.join(carpeta, hoy.strftime("%Y-%m-%d") + ".json.gz")
    with gzip.open(nombre, "wt", encoding="utf-8") as fh:
        json.dump(snap, fh, separators=(",", ":"))
    for _, _, f in sorted(snaps, key=lambda x: x[0])[:-(max_snap - 1)] if len(snaps) >= max_snap else []:
        os.remove(f)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print("Snapshot guardado:", nombre)


def armar_web(salida_json):
    """Inyecta los datos en las plantillas y deja todo en docs/ (GitHub Pages)."""
    if not os.path.isdir("plantillas"):
        return
    raw = open(salida_json, encoding="utf-8").read().replace("</", "<\\/")
    os.makedirs("docs", exist_ok=True)
    for plantilla, destino in (("buscador.html", "index.html"), ("imagenes.html", "imagenes.html")):
        t = open(os.path.join("plantillas", plantilla), encoding="utf-8").read()
        open(os.path.join("docs", destino), "w", encoding="utf-8").write(t.replace("__DATA__", raw))
    with open(salida_json, "rb") as a, open(os.path.join("docs", "sepa_tucuman.json"), "wb") as b:
        b.write(a.read())
    print("Web armada en docs/")


if __name__ == "__main__":
    salida = "sepa_tucuman.json"
    if len(sys.argv) > 2 and sys.argv[1] == "--desde-json":
        armar_web(sys.argv[2])
        sys.exit()
    print("Consultando qué día tiene los datos más nuevos...")
    dia = elegir_dia()
    print("Se usa:", dia)
    descargar(dia, "sepa.zip")
    P, fecha = procesar("sepa.zip")
    out = a_json(P, fecha, salida)
    completar_historial(out, salida)
    armar_web(salida)
    try:
        from google.colab import files
        files.download(salida)
    except Exception:
        pass
