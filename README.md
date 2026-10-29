# Matinées BCN

Web estática, pensada para el móvil, con las sesiones de cine que empiezan **antes de las 13:00 de lunes a viernes** en Barcelona y alrededores.

**Web:** https://guillepb.github.io/matinees/

Cines seguidos a diario:

| Cine | Fuente | Enlace de compra |
| --- | --- | --- |
| Zumzeig | [calendario de zumzeigcine.coop](https://zumzeigcine.coop/es/cine/calendari/) + fichas | Por sesión (próximas 3); después, la película en codetickets |
| Cines Verdi Barcelona | [cartelera](https://barcelona.cines-verdi.com/cartelera) + fichas | Por sesión |
| Kinépolis Full Splau | [Publicine](https://www.publicine.net/cartelera-cine/cornella-de-llobregat/kinepolis-barcelona-full-splau) | Por sesión |
| Cinemes Girona | [cartelera](https://www.cinemesgirona.cat/cartelera) + fichas (misma plataforma que Verdi) | Por sesión |

## Cómo funciona

```
scraper/sources/*.py   un módulo por fuente: fetch(cinema) -> list[Session]
scraper/run.py         scraping de todas las fuentes  -> data/sessions.json (todo, sin filtrar)
scraper/build.py       filtro de matinées              -> docs/matinees.json
docs/index.html        la web: lee matinees.json, sin build ni dependencias
config.yaml            cines, hora de corte, días y horizonte
```

- Si una fuente falla (o devuelve 0 sesiones), las demás se publican igual y se conservan sus sesiones de la ejecución anterior marcadas como `stale`; la web lo avisa en el pie.
- El filtro (corte a las 13:00 inclusive, lunes a viernes, 14 días vista) está en `config.yaml` y se aplica en `build.py`, así que cambiarlo no requiere volver a hacer scraping.
- El scraper es educado: User-Agent identificable, 1,5 s entre peticiones al mismo dominio, timeout de 20 s, un reintento y respeto a `robots.txt`.

## Ejecutar en local

Requiere Python 3.12.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python -m scraper.run      # ~2 min: descarga todas las fuentes
.venv/bin/python -m scraper.build    # genera docs/matinees.json
.venv/bin/python -m pytest           # tests contra los HTML guardados en tests/fixtures/

# Ver la web
.venv/bin/python -m http.server -d docs 8000   # http://localhost:8000
```

Para ver la web como si fuera otra hora (p. ej. con sesiones ya empezadas): `http://localhost:8000/?now=2026-10-29T11:40`.

## Añadir un cine

**Si está en Publicine** (la mayoría de cadenas: Cinesa, Yelmo, Ocine, Kinépolis…), basta con añadirlo a `config.yaml`:

```yaml
cinemas:
  - id: cinesa-diagonal                  # clave estable, sin espacios
    name: Cinesa Diagonal                # nombre visible en la web
    source: publicine
    url: https://www.publicine.net/cartelera-cine/barcelona/cinesa-diagonal
    tickets_url: https://www.cinesa.es/  # por si una sesión no trae enlace propio
```

Para encontrar su URL, busca el cine en [publicine.net](https://www.publicine.net/) y copia la de su cartelera.

**Si no está en Publicine**, hay que escribir un módulo nuevo en `scraper/sources/<nombre>.py` con una función `fetch(cinema, http=None, today=None) -> list[Session]` (ver `verdi.py` como ejemplo), guardar un HTML de muestra en `tests/fixtures/` con sus tests, y usar `source: <nombre>` en `config.yaml`.

Opcional: para darle un color propio en la web, añade su `id` a `DOT` en `docs/index.html`.

## Automatización (GitHub Actions)

| Workflow | Cuándo | Qué hace |
| --- | --- | --- |
| `daily.yml` | Cada día a las 06:17 (Madrid) y a mano | `run.py` + `build.py`, commit de los JSON y publica la web. Falla (y GitHub avisa por email) si fallan todas las fuentes o si `build.py` revienta |
| `pages.yml` | Al cambiar `docs/` en `main`, a mano, y llamado por el anterior | Publica `docs/` en GitHub Pages |
| `tests.yml` | En cada push y PR | `pytest` |

El cron de GitHub va en UTC: `daily.yml` programa las 04:17 y las 05:17 UTC y solo ejecuta la que corresponde a las 06:17 en Madrid según el horario de verano o invierno. GitHub puede retrasar las ejecuciones programadas unos minutos.

### Activar GitHub Pages

La web se publica con GitHub Actions (no "desde una rama"), porque los commits que hace el propio workflow con `GITHUB_TOKEN` no disparan otros workflows. En **Settings → Pages → Build and deployment → Source** elige **GitHub Actions**, o desde la terminal:

```sh
gh api -X POST repos/<usuario>/matinees/pages -f build_type=workflow
```

Después lanza el primer despliegue desde **Actions → Scraping diario → Run workflow** (o `gh workflow run daily.yml`).

Nota: GitHub desactiva los workflows programados de un repositorio público tras 60 días sin actividad. Si ocurre, avisa por email y se reactivan con un clic en la pestaña Actions.
