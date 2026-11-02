# Riesgo País Hoy

Sitio estático de [www.riesgopais.ar](https://www.riesgopais.ar): el riesgo país argentino (JP Morgan EMBI) con su serie desde 2011, comparación regional, escenarios y contexto renovado a diario.

## Cómo se mantiene

- **Cierres diarios (automático, sin intervención):** el flujo `.github/workflows/publicar-gh-pages.yml` corre cuatro veces por día hábil (10:17, 13:17, 16:17 y 19:17, hora argentina), toma los cierres nuevos de [ArgentinaDatos](https://argentinadatos.com/) con `scripts/actualizar_riesgo_pais.py` y los guarda en `data.json` (solo el bloque `argentina`; nunca toca `editorial` ni `region`). Si la fuente no responde, no inventa valores: la corrida informa el error.
- **Editorial, cotización en la rueda y cuadro regional:** los escriben las tareas automáticas de Claude que mantienen la página original y sincronizan su `data.json` con este repositorio.
- **Publicación:** después de cada corrida programada y de cada push a `main`, el mismo flujo arma la copia pública con `scripts/preparar_sitio.py` (sincroniza el JSON embebido de `index.html` con `data.json`) y la sube a la rama `gh-pages`, que es la que sirve GitHub Pages. También se puede lanzar a mano desde **Actions → Run workflow**.

`index.html` solo cambia cuando cambia el diseño. Las pruebas del actualizador se corren con `python -m unittest discover -s scripts -p 'test_*.py'`.

Fuentes: ArgentinaDatos (cierres de Ámbito Financiero), Rava Bursátil (intradiario), Bloomberg Línea (región) y prensa citada en la página.
