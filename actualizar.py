"""Tucumán Ahorra: baja la base SEPA más reciente, filtra Tucumán y genera sepa_tucuman.json.
Sirve igual en Colab y en GitHub Actions. Si existe la carpeta plantillas/, también arma la web en docs/."""
import io, json, os, re, sys, time, zipfile
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
    a_json(P, fecha, salida)
    armar_web(salida)
    try:
        from google.colab import files
        files.download(salida)
    except Exception:
        pass
