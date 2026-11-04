# Riesgo País Hoy

Sitio estático de [www.riesgopais.ar](https://www.riesgopais.ar): el riesgo país argentino (JP Morgan EMBI) con su serie desde 2011, comparación regional, escenarios y contexto renovado a diario.

## Cómo se mantiene

- **Rueda y cierres (automático, sin intervención):** el flujo `.github/workflows/publicar-gh-pages.yml` corre cada media hora de 10:23 a 18:53 (hora argentina) los días hábiles, y a las 20:23, 23:23 y 1:23 para el cierre oficial. En cada corrida, `scripts/actualizar_riesgo_pais.py`:
  - toma los cierres oficiales nuevos de [ArgentinaDatos](https://argentinadatos.com/) y del histórico de Ámbito (la fuente de la que ArgentinaDatos copia, que publica el cierre del día de noche);
  - toma la lectura en vivo de la rueda de Ámbito (`mercados.ambito.com/riesgopais/variacion`) o, si falla, de la tabla "Riesgo País hoy" de Rava Bursátil, y la guarda como `argentina.intradiario` con la hora en que se tomó. Solo se acepta si es posterior al último cierre oficial, no es futura y no se aleja más de 30 % del último cierre; cuando llega el cierre oficial de ese día, la lectura se retira.
  
  Solo cambia el bloque `argentina` de `data.json`; nunca toca `editorial` ni `region`, y no inventa valores: sin datos nuevos, no escribe nada. Los feriados no necesitan tratamiento especial (sin rueda no hay dato nuevo).
- **Editorial y cuadro regional:** los escriben las tareas automáticas de Claude que mantienen la página original y sincronizan su `data.json` con este repositorio.
- **Publicación:** cuando hay datos nuevos (y siempre con cada push a `main`), el mismo flujo arma la copia pública con `scripts/preparar_sitio.py` (sincroniza el JSON embebido de `index.html` con `data.json`) y la sube a la rama `gh-pages`, que es la que sirve GitHub Pages. También se puede lanzar a mano desde **Actions → Run workflow**.

GitHub no garantiza la puntualidad de las corridas programadas (a veces las atrasa o las salta); por eso se piden cada media hora, para que el sitio quede al día al menos una vez por hora.

`index.html` solo cambia cuando cambia el diseño. Las pruebas del actualizador se corren con `python -m unittest discover -s scripts -p 'test_*.py'`.

Fuentes: Ámbito Financiero (cierres, vía ArgentinaDatos, y rueda en vivo), Rava Bursátil (respaldo de la rueda), Bloomberg Línea (región) y prensa citada en la página.
