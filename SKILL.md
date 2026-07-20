---
name: zenodo-app-publisher
description: Da de alta una app del catálogo de fborrasumh (Herramientas IA para la academia, UMH) en Zenodo, generando su DOI de concepto, subiendo un CITATION.cff al repo de GitHub de la app, y actualizando el index.html de github.com/fborrasumh/ia. Úsala siempre que el usuario quiera "publicar", "acuñar un DOI", "dar de alta en Zenodo", "registrar" o "añadir la cita" de una de sus apps, o cuando añada una app nueva al catálogo y quiera que quede registrada y citable. Cubre tanto apps ya presentes en el índice (con doi:"") como apps completamente nuevas que aún no están en la web.
---

# Zenodo App Publisher

Automatiza el alta de una app del catálogo **Herramientas IA para la academia** de
Fernando Borrás Rocher (UMH, ORCID 0000-0002-5519-4573) que se publica en
`https://fborrasumh.github.io/ia/`.

Por cada app, el flujo completo es:

1. **Zenodo** — archiva el ZIP del repo de GitHub y acuña un **DOI de concepto**
   (el que apunta siempre a la última versión) con los metadatos estándar del autor.
2. **CITATION.cff** — genera el fichero de cita con ese DOI y lo sube (commit directo)
   al repo de la app, para que GitHub muestre el botón *Cite this repository*.
3. **index.html** — escribe el DOI en la ficha de la app dentro de
   `github.com/fborrasumh/ia/index.html` y hace commit; si la app es nueva, primero
   inserta su ficha en el array `apps`.

Todo esto lo hace el script `scripts/publish_app.py`, que es la vía recomendada:
encapsula el orden correcto, es idempotente por app y limpia los borradores huérfanos
que deja un fallo a medias. **Prefiere el script a reimplementar los pasos a mano.**

## Antes de empezar: requisitos

Se necesitan dos tokens, siempre pasados como variables de entorno (nunca escritos en
ficheros ni en el propio script):

- `ZENODO_TOKEN` — token personal de zenodo.org con scopes `deposit:write` y
  `deposit:actions`. Se crea en zenodo.org → Applications → Personal access tokens.
- `GITHUB_TOKEN` — token de GitHub con scope `repo` (para subir CITATION.cff y el
  index.html). Solo hace falta si no usas `--no-github`.

Comprueba primero que ambos existen y que hay conectividad, y **valida cada token con una
llamada de solo lectura** (p. ej. `GET /api/deposit/depositions` en Zenodo y `GET /user`
en GitHub) antes de nada que escriba. Si falta un token, pídelo; recuérdale al usuario que
lo **revoque al terminar** si lo pega en el chat, porque queda en texto plano.

Instala la dependencia si hace falta: `pip install requests --break-system-packages`.

## Uso del script

El script trabaja en el directorio actual, donde lee/escribe `zenodo_state.json`
(registro de progreso: mapa `repo → {concept_doi, version_doi, record, branch}`).

**Caso A · la app ya está en el índice con `doi:""`** (lo más común). El script lee sus
metadatos del propio index.html remoto, así que basta el nombre del repo:

```bash
export ZENODO_TOKEN="..."; export GITHUB_TOKEN="..."
python3 scripts/publish_app.py --repo nutriquest
```

**Caso B · app nueva que aún no está en la web.** Hay que darle los metadatos mínimos;
el script inserta la ficha en el array `apps` y luego publica:

```bash
python3 scripts/publish_app.py --repo miapp \
  --cat sim --title "Mi App" --icon ti-flask \
  --sub-es "Subtítulo corto" --desc-es "Descripción en español." \
  --sub-en "Short subtitle" --desc-en "English description."
```

Las categorías válidas (`--cat`) son: `doc` (Docencia), `eva` (Evaluación),
`inv` (Investigación), `sim` (Simulación), `uti` (Utilidades). Los iconos son nombres
Tabler (p. ej. `ti-flask`); ver https://tabler.io/icons. Opcionalmente `--tit-es/-en`
(titulación) y `--comp-es/-en` (competencias); si se omiten, quedan vacíos y el usuario
los completa luego.

**Banderas útiles:**

- `--dry-run` — no acuña DOI ni toca GitHub; útil para confirmar que la app se resuelve
  bien. Empieza SIEMPRE por aquí si tienes dudas.
- `--sandbox` — publica en sandbox.zenodo.org (DOIs de prueba, **token de sandbox
  distinto**). Ideal para verificar metadatos sin generar un DOI permanente.
- `--no-github` — solo acuña el DOI en Zenodo; no sube CITATION.cff ni actualiza el
  índice. El script imprime el DOI para pegarlo a mano.
- `--branch B` — fuerza la rama del repo si la autodetección (main→master) no acierta.

## Flujo recomendado

1. **Valida los tokens** con llamadas de solo lectura y confirma conectividad con
   `zenodo.org`, `codeload.github.com` y `api.github.com`.
2. **Verifica que el repo existe y descarga**, comprobando la rama, antes de publicar:
   una `HEAD` a `https://codeload.github.com/fborrasumh/<repo>/zip/refs/heads/main`.
   Un nombre de repo equivocado es el fallo más común (p. ej. una URL del índice que no
   coincide con el repo real). Si no existe, no sigas: avisa al usuario y, si procede,
   corrige el nombre.
3. **Ensaya con `--dry-run`** y, si el usuario quiere máxima cautela con una app nueva,
   haz una pasada en `--sandbox` primero.
4. **Publica de verdad** (una app). Tras el primer DOI, **verifica el registro** leyendo
   `GET https://zenodo.org/api/records/<id>` y confirma autoría, ORCID, licencia
   (`mit-license`), tipo *Software* y que el ZIP se subió. Enseña el resultado antes de
   seguir con más.
5. Si son **varias apps**, ejecútalas de una en una (o en lotes pequeños) reutilizando el
   mismo directorio para que `zenodo_state.json` acumule el progreso. Los DOIs publicados
   son permanentes, así que ir por lotes con verificación reduce el riesgo.
6. Al terminar, recuerda al usuario **revocar los tokens** y comprobar que
   `fborrasumh.github.io/ia/` muestra el DOI (GitHub Pages tarda un par de minutos).

## Detalles importantes

- **DOI de concepto vs. de versión.** Se escribe en el índice el DOI de *concepto*
  (`conceptdoi`), que sobrevive a nuevas versiones. El DOI de versión queda guardado en
  `zenodo_state.json` por si se necesita.
- **Idempotencia.** Si la app ya tiene un DOI en el índice, el script no vuelve a acuñar
  (imprime que no hay nada que hacer). Se puede relanzar sin miedo a duplicar.
- **Borradores huérfanos.** Si Zenodo falla a mitad (o el proceso muere), puede quedar un
  depósito en estado borrador. El script los limpia automáticamente al capturar un error;
  si publicas por lotes desde fuera del script y algo muere, borra los borradores con una
  pasada de `GET /api/deposit/depositions` filtrando `submitted == false` y `DELETE`.
- **No ejecutes procesos largos en segundo plano** esperando que sobrevivan entre turnos:
  el contenedor no los mantiene vivos. Ejecuta en primer plano por lotes.
- **Metadatos fijos** (autor, ORCID, afiliación UMH, licencia MIT, tipo *Software*,
  v1.0.0, idioma español, keywords por categoría, enlace al repo como `isSupplementTo`)
  están codificados en el script para mantener consistencia entre registros. Si el usuario
  pide cambiarlos (p. ej. otra licencia), edita las constantes al principio de
  `scripts/publish_app.py`.
- **CITATION.cff** se sube por defecto a la rama detectada del repo de la app y actualiza
  el fichero si ya existía (usa su `sha`).

## Resolución de problemas

- **`403` de GitHub al listar repos** — es rate-limit de la API sin autenticar; usa el
  `GITHUB_TOKEN` en la cabecera `Authorization`.
- **`github.io` da 403 desde el contenedor** — normal, ese dominio no está permitido en el
  entorno; no significa que la app esté caída. Verifica el repo por `codeload`, no por la
  URL de Pages.
- **El DOI no se escribe en el índice** — el patrón `url:"...", doi:""` no coincidió
  (espaciado distinto en el índice). El script avisa e imprime el DOI para pegarlo a mano;
  el DOI en Zenodo ya es válido, no se pierde.
- **Licencia rechazada** — Zenodo espera identificadores en minúscula; `MIT` se normaliza
  solo a `mit-license`, así que no suele dar problema.
