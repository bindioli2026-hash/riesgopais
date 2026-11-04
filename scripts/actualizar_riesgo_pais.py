#!/usr/bin/env python3
"""Actualiza el bloque "argentina" de data.json: cierres oficiales y lectura de la rueda.

Cierres oficiales (serie y "ultimo"): ArgentinaDatos (API o su repositorio en
GitHub), completados con el histórico de Ámbito, que es la fuente de la que
ArgentinaDatos copia los valores y que publica el cierre del día unas horas
antes.

Lectura de la rueda ("intradiario"): el valor en vivo que publica Ámbito
(mercados.ambito.com/riesgopais/variacion) o, si falla, la tabla "Riesgo País
hoy" de Rava Bursátil. Solo se acepta si es posterior al último cierre oficial,
no es de una fecha futura y está dentro de un rango razonable; si ninguna fuente
responde, se conserva la lectura anterior mientras siga siendo posterior al
último cierre. Cuando llega el cierre oficial de ese día, la lectura se retira.

Los bloques "region" y "editorial" nunca se tocan. No se inventan valores: si no
hay datos nuevos, el archivo no se modifica.

Uso: actualizar_riesgo_pais.py [--simular]   (--simular: muestra qué haría y no escribe)
"""
from __future__ import annotations

import html
import json
import math
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

RUTA = Path(__file__).resolve().parents[1] / "data.json"
BA = ZoneInfo("America/Argentina/Buenos_Aires")
UA = "riesgopais-ar/1.2 (actualizacion de datos; www.riesgopais.ar)"

API_SERIE = "https://api.argentinadatos.com/v1/finanzas/indices/riesgo-pais"
API_ULTIMO = API_SERIE + "/ultimo"
RAW_SERIE = (
    "https://raw.githubusercontent.com/enzonotario/esjs-argentina-datos-api/main/"
    "datos/v1/finanzas/indices/riesgo-pais/index.json"
)
AMBITO_HISTORICO = "https://mercados.ambito.com/riesgopais/historico-general/{desde}/{hasta}"
AMBITO_VIVO = "https://mercados.ambito.com/riesgopais/variacion"
AMBITO_PAGINA = "https://www.ambito.com/contenidos/riesgo-pais.html"
RAVA_HOY = "https://www.rava.com/cotizaciones/historico/riesgo-pais/hoy/"
RAVA_PAGINA = "https://www.rava.com/perfil/RIESGO%20PAIS"

VALOR_MIN, VALOR_MAX = 1, 10000
# Una lectura de la rueda que se aleje más que esto del último cierre se descarta.
SALTO_MAXIMO = 0.30


# ----------------------------------------------------------------------------
# Descarga y parseo
# ----------------------------------------------------------------------------
def descargar(url: str, *, json_=True, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        datos = resp.read()
    if json_:
        return json.loads(datos.decode("utf-8"))
    return datos.decode("utf-8", errors="replace")


def numero(texto):
    """'805,00' -> 805.0; '1.234,5' -> 1234.5; 831 -> 831.0; inválido -> None."""
    if isinstance(texto, bool):
        return None
    if isinstance(texto, (int, float)):
        return float(texto)
    if not isinstance(texto, str):
        return None
    t = texto.strip().replace("\xa0", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def fecha_iso(texto):
    """'03-11-2026', '03/11/2026' o '2026-11-03' -> '2026-11-03'; inválido -> None."""
    if not isinstance(texto, str):
        return None
    t = texto.strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(t, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def registro(fila, hoy: date):
    """Normaliza una fila {"fecha","valor"} a (fecha_iso, entero) o None si no sirve."""
    if not isinstance(fila, dict):
        return None
    fecha = fecha_iso(fila.get("fecha"))
    valor = numero(fila.get("valor"))
    if fecha is None or valor is None or not math.isfinite(valor):
        return None
    if date.fromisoformat(fecha) > hoy or not VALOR_MIN <= valor <= VALOR_MAX:
        return None
    # El indicador se publica en puntos básicos enteros.
    return (fecha, int(round(valor)))


# ----------------------------------------------------------------------------
# Fuentes de cierres oficiales
# ----------------------------------------------------------------------------
def filas_argentinadatos(res):
    if isinstance(res, dict) and "fecha" in res:
        return [res]
    if isinstance(res, dict) and isinstance(res.get("data"), list):
        return res["data"]
    if isinstance(res, list):
        return res
    raise ValueError("formato inesperado")


def filas_ambito_historico(res):
    """[["Fecha","Puntos"],["02-11-2026","805,00"],...] -> [{"fecha","valor"}]"""
    if not isinstance(res, list):
        raise ValueError("formato inesperado")
    filas = []
    for item in res:
        if not (isinstance(item, list) and len(item) >= 2) or item[0] == "Fecha":
            continue
        filas.append({"fecha": item[0], "valor": item[1]})
    return filas


def obtener_cierres(hoy: date) -> list:
    """Filas {"fecha","valor"} de todas las fuentes de cierres que respondan."""
    desde = (hoy - timedelta(days=20)).isoformat()
    fuentes = (
        ("API de ArgentinaDatos (serie completa)", API_SERIE, filas_argentinadatos),
        ("GitHub de ArgentinaDatos (serie completa)", RAW_SERIE, filas_argentinadatos),
        ("histórico de Ámbito (últimos 20 días)", AMBITO_HISTORICO.format(desde=desde, hasta=hoy.isoformat()), filas_ambito_historico),
        ("API de ArgentinaDatos (último valor)", API_ULTIMO, filas_argentinadatos),
    )
    filas = []
    for nombre, url, parsear in fuentes:
        # La serie completa alcanza con una fuente; el histórico de Ámbito se suma siempre.
        if filas and "ArgentinaDatos" in nombre:
            continue
        try:
            nuevas = parsear(descargar(url))
        except Exception as exc:  # noqa: BLE001 - se informa y se sigue con la siguiente fuente
            print(f"AVISO: falló {nombre} ({exc}).", file=sys.stderr)
            continue
        print(f"Cierres: {nombre}, {len(nuevas)} filas.")
        filas.extend(nuevas)
    if not filas:
        raise RuntimeError("Ninguna fuente de cierres respondió; no se modifica data.json.")
    return filas


# ----------------------------------------------------------------------------
# Lectura de la rueda
# ----------------------------------------------------------------------------
def rueda_ambito(res):
    """{"ultimo":"831","fecha":"03-11-2026",...} -> {"fecha","valor","fuente","url"}"""
    if not isinstance(res, dict):
        raise ValueError("formato inesperado")
    return {"fecha": res.get("fecha"), "valor": res.get("ultimo"), "fuente": "Ámbito Financiero", "url": AMBITO_PAGINA}


def rueda_rava(pagina: str):
    """Toma la fila más reciente de la tabla 'Últimos días' (Fecha | Cierre | Variación | Máximo | Mínimo)."""
    mejor = None
    for fila in re.findall(r"<tr[^>]*>(.*?)</tr>", pagina, flags=re.S | re.I):
        celdas = [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", fila, flags=re.S | re.I)]
        if len(celdas) < 2 or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", celdas[0]):
            continue
        fecha = fecha_iso(celdas[0])
        if fecha and (mejor is None or fecha > mejor["fecha"]):
            mejor = {"fecha": fecha, "valor": celdas[1]}
    if mejor is None:
        raise ValueError("no se encontró la tabla de cierres")
    return {"fecha": mejor["fecha"], "valor": mejor["valor"], "fuente": "Rava Bursátil", "url": RAVA_PAGINA}


def leer_rueda():
    """Devuelve la lectura en vivo de la primera fuente que responda, o None."""
    fuentes = (
        ("Ámbito (valor en vivo)", lambda: rueda_ambito(descargar(AMBITO_VIVO))),
        ("Rava (tabla de hoy)", lambda: rueda_rava(descargar(RAVA_HOY, json_=False))),
    )
    for nombre, obtener in fuentes:
        try:
            lectura = obtener()
        except Exception as exc:  # noqa: BLE001
            print(f"AVISO: falló {nombre} ({exc}).", file=sys.stderr)
            continue
        print(f"Rueda: {nombre} -> {lectura.get('valor')} ({lectura.get('fecha')}).")
        return lectura
    print("AVISO: ninguna fuente de la rueda respondió; se conserva la lectura anterior si sigue vigente.", file=sys.stderr)
    return None


def rueda_valida(lectura, ultimo: list, hoy: date):
    """Normaliza la lectura en vivo o devuelve None si no es publicable."""
    if not isinstance(lectura, dict):
        return None
    r = registro({"fecha": lectura.get("fecha"), "valor": lectura.get("valor")}, hoy)
    if r is None:
        return None
    fecha, valor = r
    if fecha <= ultimo[0]:
        return None  # ese día ya tiene cierre oficial (o la lectura es vieja)
    if abs(valor - ultimo[1]) > SALTO_MAXIMO * ultimo[1]:
        print(f"AVISO: lectura de la rueda descartada por salto implausible ({valor} vs cierre {ultimo[1]}).", file=sys.stderr)
        return None
    return {"fecha": fecha, "valor": valor, "fuente": str(lectura.get("fuente") or ""), "url": str(lectura.get("url") or "")}


# ----------------------------------------------------------------------------
# Aplicación sobre data.json
# ----------------------------------------------------------------------------
def aplicar(datos: dict, filas: list, hoy: date, instante: datetime, rueda=None) -> tuple[bool, int]:
    """Incorpora cierres nuevos y la lectura de la rueda. Devuelve (hubo_cambios, cierres_agregados)."""
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
        raise ValueError("Las fuentes no devolvieron ningún cierre comparable con la última fecha local.")
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

    # Lectura de la rueda: se publica si es válida y distinta de la vigente.
    vigente = ar.get("intradiario") if isinstance(ar.get("intradiario"), dict) else None
    nueva = rueda_valida(rueda, nueva_ultima, hoy)
    if nueva is not None:
        if vigente is None or (vigente.get("fecha"), vigente.get("valor")) != (nueva["fecha"], nueva["valor"]):
            nueva["hora"] = instante.astimezone(BA).strftime("%H:%M")
            ar["intradiario"] = nueva
            cambio = True
    else:
        # Sin lectura nueva: la anterior se conserva mientras sea posterior al último
        # cierre oficial; se retira si quedó alcanzada por la serie, si es futura o
        # si está malformada.
        if ar.get("intradiario") is not None:
            fecha_iv = vigente.get("fecha") if vigente else None
            valor_iv = vigente.get("valor") if vigente else None
            if (
                not isinstance(fecha_iv, str)
                or fecha_iv <= nueva_ultima[0]
                or fecha_iv > hoy.isoformat()
                or isinstance(valor_iv, bool)
                or not isinstance(valor_iv, (int, float))
                or registro({"fecha": fecha_iv, "valor": valor_iv}, hoy) is None
            ):
                ar["intradiario"] = None
                cambio = True
    if cambio:
        datos["generado"] = instante.astimezone(BA).isoformat(timespec="seconds")
    return cambio, agregados


def main(argv) -> int:
    simular = "--simular" in argv
    ahora = datetime.now(BA)
    hoy = ahora.date()
    filas = obtener_cierres(hoy)
    rueda = leer_rueda()
    data = json.loads(RUTA.read_text(encoding="utf-8"))
    cambiado, agregados = aplicar(data, filas, hoy, ahora, rueda)
    if cambiado and not simular:
        # Solo reescribir data.json cuando cambien datos efectivos.
        RUTA.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    ar = data["argentina"]
    print(
        f"{'SIMULACIÓN: ' if simular else ''}Cierres nuevos: {agregados}. Último cierre: {ar['ultimo']}. "
        f"Rueda: {ar.get('intradiario')}. Archivo {'modificado' if cambiado and not simular else 'sin cambios'}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
