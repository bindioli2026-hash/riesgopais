#!/usr/bin/env python3
"""Arma en _publicacion/ la copia pública del sitio.

Copia index.html con el bloque <script id="datos-embebidos"> sincronizado con
data.json (así la primera pintura ya muestra el último cierre, antes del fetch) y
los archivos auxiliares. No modifica los archivos de main.
"""
import json
import re
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
html = (root / "index.html").read_text(encoding="utf-8")
data = json.loads((root / "data.json").read_text(encoding="utf-8"))
contenido = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
# El contenido JSON no debe poder cerrar su elemento <script> del HTML.
contenido = contenido.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
patron = r'(<script id="datos-embebidos" type="application/json">).*?(</script>)'
html_nuevo, count = re.subn(patron, lambda m: m[1] + contenido + m[2], html, count=1, flags=re.DOTALL)
if count != 1:
    raise RuntimeError("No se encontró un único bloque datos-embebidos en index.html")

out = root / "_publicacion"
if out.exists():
    shutil.rmtree(out)
out.mkdir()
(out / "index.html").write_text(html_nuevo, encoding="utf-8")
for nombre in ["data.json", "CNAME", "robots.txt", "sitemap.xml", ".nojekyll"]:
    origen = root / nombre
    if origen.exists():
        shutil.copyfile(origen, out / nombre)
    elif nombre in ("data.json", "CNAME"):
        raise RuntimeError(f"Falta {nombre} en el repositorio")
print(
    "Sitio preparado en _publicacion/ con JSON embebido actualizado "
    f"(último cierre {data['argentina']['ultimo']['fecha']})."
)
