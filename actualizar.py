"""Tucumán Ahorra: baja la base SEPA más reciente, filtra Tucumán y genera sepa_tucuman.json.
Sirve igual en Colab y en GitHub Actions. Si existe la carpeta plantillas/, también arma la web en docs/."""
import glob, gzip, io, json, os, re, statistics, sys, time, zipfile
from datetime import datetime
from email.utils import parsedate_to_datetime
import pandas as pd
import requests

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
        rows.append([ean, str(r["n"])[:70], str(r["m"])[:20], precios, mm])
    pr = d[(d["promo"] > 0) & (d["promo"] < d["precio"])]
    pr = pr.groupby(["ean", "cad"]).agg(p=("promo", "min"), l=("productos_leyenda_promo1", "first"))
    promos = {}
    for (ean, cad), r in pr.iterrows():
        promos.setdefault(ean, {})[str(chains.index(cad))] = [int(round(r["p"])), str(r["l"])[:60]]
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
    suben = sorted([x for x in res if x[2] > 0], key=lambda x: -x[2])[:60]
    bajan = sorted([x for x in res if x[2] < 0], key=lambda x: x[2])[:60]
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
