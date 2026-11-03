#!/usr/bin/env python3
"""Actualiza únicamente los cierres argentinos de data.json desde ArgentinaDatos.

Mantiene sin cambios los apartados "region" y "editorial" y toda la serie anterior.
No usa datos intradiarios, predicciones ni valores inventados: solo cierres
publicados por la fuente. Si ninguna fuente responde, termina con error y no
toca el archivo.
"""
from __future__ import annotations

import json
import math
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

RUTA = Path(__file__).resolve().parents[1] / "data.json"
API_SERIE = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"
API_ULTIMO = API_SERIE + "/ultimo"
# Mismo conjunto de datos, servido desde el repositorio público de ArgentinaDatos.
RAW_SERIE = (
    "https://raw.githubusercontent.com/enzonotario/esjs-argentina-datos-api/main/"
    "datos/v1/finanzas/indices/riesgo-pais/index.json"
)
FUENTES = (
    ("API de ArgentinaDatos (serie completa)", API_SERIE),
    ("GitHub de ArgentinaDatos (serie completa)", RAW_SERIE),
    ("API de ArgentinaDatos (último valor)", API_ULTIMO),
)
BA = ZoneInfo("America/Argentina/Buenos_Aires")


def consultar(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "riesgopais-ar/1.1 (actualizacion de cierres; www.riesgopais.ar)",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


def obtener_filas() -> list:
    """Devuelve la lista de filas {"fecha","valor"} de la primera fuente que responda."""
    for nombre, url in FUENTES:
        try:
            res = consultar(url)
        except Exception as exc:  # noqa: BLE001 - se informa y se prueba la siguiente fuente
            print(f"AVISO: falló {nombre} ({exc}).", file=sys.stderr)
            continue
        if isinstance(res, dict) and "fecha" in res:
            filas = [res]
        elif isinstance(res, dict) and isinstance(res.get("data"), list):
            filas = res["data"]
        elif isinstance(res, list):
            filas = res
        else:
            print(f"AVISO: {nombre} devolvió un formato inesperado.", file=sys.stderr)
            continue
        print(f"Fuente usada: {nombre} ({len(filas)} filas).")
        return filas
    raise RuntimeError("Ninguna fuente de ArgentinaDatos respondió; no se modifica data.json.")


def registro(fila, hoy: date):
    if not isinstance(fila, dict):
        return None
    fecha, valor = fila.get("fecha"), fila.get("valor")
    if not isinstance(fecha, str) or len(fecha) != 10:
        return None
    try:
        f = date.fromisoformat(fecha)
    except ValueError:
        return None
    if f > hoy or isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    if not math.isfinite(valor) or not 1 <= valor <= 10000:
        return None
    # El indicador se publica en puntos básicos enteros.
    return (fecha, int(round(valor)))


def aplicar(datos: dict, filas: list, hoy: date, instante: datetime) -> tuple[bool, int]:
    """Incorpora a datos["argentina"] los cierres nuevos. Devuelve (hubo_cambios, agregados)."""
    ar = datos["argentina"]
    serie = ar["serie"]
    if not isinstance(serie, list) or len(serie) < 2:
        raise ValueError("Serie original vacía o inválida; no se sobrescribe.")
    ultimo_reg = serie[-1]
    if not (isinstance(ultimo_reg, list) and len(ultimo_reg) == 2):
        raise ValueError("Último elemento de la serie inválido.")
    fecha_anterior = ultimo_reg[0]
    nuevos = {}
    for fila in filas:
        r = registro(fila, hoy)
        if r and r[0] >= fecha_anterior:
            nuevos[r[0]] = r[1]
    if not nuevos:
        raise ValueError("La fuente no devolvió ningún cierre comparable con la última fecha local.")
    cambio = False
    agregados = 0
    if fecha_anterior in nuevos and nuevos[fecha_anterior] != ultimo_reg[1]:
        ultimo_reg[1] = nuevos[fecha_anterior]
        cambio = True
        print(f"Corrección publicada por la fuente para {fecha_anterior}: {ultimo_reg[1]}")
    for fecha in sorted(nuevos):
        if fecha > fecha_anterior:
            serie.append([fecha, nuevos[fecha]])
            cambio = True
            agregados += 1
    nueva_ultima = serie[-1]
    if ar.get("ultimo") != {"fecha": nueva_ultima[0], "valor": nueva_ultima[1]}:
        ar["ultimo"] = {"fecha": nueva_ultima[0], "valor": nueva_ultima[1]}
        cambio = True
    # La lectura provisoria ("en la rueda") se conserva mientras sea posterior al
    # último cierre oficial: la página la muestra con su fecha y la reemplaza el
    # cierre oficial de ese día cuando la fuente lo publica. Se descarta si quedó
    # alcanzada por la serie, si es de una fecha futura o si está malformada.
    iv = ar.get("intradiario")
    if iv is not None:
        fecha_iv = iv.get("fecha") if isinstance(iv, dict) else None
        if (
            not isinstance(fecha_iv, str)
            or fecha_iv <= nueva_ultima[0]
            or fecha_iv > hoy.isoformat()
            or registro({"fecha": fecha_iv, "valor": iv.get("valor")}, hoy) is None
        ):
            ar["intradiario"] = None
            cambio = True
    if cambio:
        datos["generado"] = instante.astimezone(BA).isoformat(timespec="seconds")
    return cambio, agregados


def main() -> int:
    hoy = datetime.now(BA).date()
    filas = obtener_filas()
    original = RUTA.read_text(encoding="utf-8")
    data = json.loads(original)
    cambiado, agregados = aplicar(data, filas, hoy, datetime.now(BA))
    if cambiado:
        # Solo reescribir data.json cuando cambien datos efectivos.
        RUTA.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Cierres nuevos: {agregados}. Último: {data['argentina']['ultimo']}. Archivo modificado: {cambiado}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
