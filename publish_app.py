#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_app.py — Da de alta UNA app nueva del catálogo fborrasumh/ia:
  1. Acuña un DOI de concepto en Zenodo (archivando el ZIP del repo de GitHub).
  2. Sube un CITATION.cff con ese DOI al repo de la app.
  3. Escribe el DOI en el index.html de github.com/fborrasumh/ia y hace commit.

Está pensado para ejecutarse de forma repetida y segura: es idempotente por app
(si la app ya tiene DOI en el índice, no vuelve a acuñar), guarda progreso en
zenodo_state.json, y limpia los borradores huérfanos que deje un fallo a medias.

REQUISITOS
  pip install requests
  export ZENODO_TOKEN="..."   # scopes deposit:write + deposit:actions
  export GITHUB_TOKEN="..."   # scope repo  (solo si subes CITATION.cff / index.html)

USO
  # Alta completa de una app ya presente en el index.html (con doi:""):
  python3 publish_app.py --repo nutriquest

  # Alta de una app nueva que AÚN NO está en el index.html (la inserta y publica):
  python3 publish_app.py --repo miapp --cat sim --title "Mi App" \
      --icon ti-flask \
      --sub-es "Subtítulo" --desc-es "Descripción en español." \
      --sub-en "Subtitle" --desc-en "English description."

  # Ensayo sin tocar nada:
  python3 publish_app.py --repo miapp --dry-run

  # Solo Zenodo, sin subir a GitHub todavía:
  python3 publish_app.py --repo miapp --no-github

OPCIONES DE VERIFICACIÓN
  --sandbox     usa sandbox.zenodo.org (DOIs de prueba; token distinto)
  --branch B    fuerza la rama del repo (por defecto autodetecta main/master)

Ver también: SKILL.md para el flujo recomendado y la resolución de problemas.
"""

import argparse, base64, json, os, re, sys, time
from datetime import date

try:
    import requests
except ImportError:
    sys.exit("Falta la librería requests:  pip install requests")

# ── Configuración fija del catálogo ─────────────────────────────────────────
GITHUB_USER   = "fborrasumh"
INDEX_REPO    = "ia"                      # repo que sirve el catálogo
INDEX_PATH    = "index.html"
ORCID         = "0000-0002-5519-4573"
CREATOR       = {"name": "Borrás Rocher, Fernando",
                 "affiliation": "Universidad Miguel Hernández de Elche",
                 "orcid": ORCID}
LICENSE       = "MIT"
STATE_FILE    = "zenodo_state.json"
CATALOG_URL   = "https://fborrasumh.github.io/ia/"
BASE_KEYWORDS = ["artificial intelligence", "higher education",
                 "educational technology", "Universidad Miguel Hernández"]
CAT_KEYWORDS  = {"doc": ["teaching"], "eva": ["assessment"], "inv": ["research tools"],
                 "sim": ["clinical simulation"], "uti": ["academic utilities"]}
VALID_CATS    = set(CAT_KEYWORDS)


# ── GitHub helpers ──────────────────────────────────────────────────────────
def gh_headers(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def gh_get_file(repo, path, token, ref="main"):
    """Devuelve (texto, sha) o (None, None) si no existe."""
    api = f"https://api.github.com/repos/{GITHUB_USER}/{repo}/contents/{path}"
    r = requests.get(api, headers=gh_headers(token), params={"ref": ref}, timeout=30)
    if r.status_code == 200:
        d = r.json()
        return base64.b64decode(d["content"]).decode("utf-8"), d["sha"]
    return None, None


def gh_default_branch(repo, token):
    r = requests.get(f"https://api.github.com/repos/{GITHUB_USER}/{repo}",
                     headers=gh_headers(token), timeout=30)
    if r.status_code == 200:
        return r.json().get("default_branch", "main")
    return "main"


def gh_put_file(repo, path, content_bytes, message, token, branch="main", sha=None):
    api = f"https://api.github.com/repos/{GITHUB_USER}/{repo}/contents/{path}"
    body = {"message": message,
            "content": base64.b64encode(content_bytes).decode(),
            "branch": branch}
    if sha:
        body["sha"] = sha
    r = requests.put(api, headers=gh_headers(token), json=body, timeout=60)
    r.raise_for_status()
    return r.json()


# ── Descarga del repo desde GitHub (para archivarlo en Zenodo) ──────────────
def download_repo_zip(repo, forced_branch=None):
    branches = [forced_branch] if forced_branch else ("main", "master")
    for branch in branches:
        url = f"https://codeload.github.com/{GITHUB_USER}/{repo}/zip/refs/heads/{branch}"
        r = requests.get(url, timeout=120)
        if r.status_code == 200 and len(r.content) > 200:
            return r.content, branch
    return None, None


# ── Zenodo ──────────────────────────────────────────────────────────────────
def make_metadata(title, cat, url, repo, branch, desc_es, desc_en):
    desc = (f"<p>{desc_es}</p><p><em>{desc_en}</em></p>"
            f"<p>Aplicación web de un solo fichero (HTML/JS, sin backend); funciona "
            f"íntegramente en el navegador y la API key del usuario se almacena "
            f"localmente. Parte del catálogo "
            f"<a href='{CATALOG_URL}'>Herramientas IA para la academia</a> "
            f"(Universidad Miguel Hernández de Elche).</p>"
            f"<p>App: <a href='{url}'>{url}</a></p>")
    return {"metadata": {
        "title": f"{title} — herramienta IA para la academia (UMH)",
        "upload_type": "software",
        "description": desc,
        "creators": [CREATOR],
        "license": LICENSE,
        "version": "1.0.0",
        "publication_date": date.today().isoformat(),
        "language": "spa",
        "keywords": BASE_KEYWORDS + CAT_KEYWORDS.get(cat, []),
        "related_identifiers": [{
            "identifier": f"https://github.com/{GITHUB_USER}/{repo}/tree/{branch}",
            "relation": "isSupplementTo", "scheme": "url"}],
    }}


def zenodo_publish(base, token, meta, zip_bytes, repo, branch):
    p = {"access_token": token}
    r = requests.post(f"{base}/api/deposit/depositions", params=p, json=meta, timeout=60)
    r.raise_for_status()
    dep = r.json()
    dep_id, bucket = dep["id"], dep["links"]["bucket"]
    r = requests.put(f"{bucket}/{repo}-{branch}.zip", params=p, data=zip_bytes, timeout=300)
    r.raise_for_status()
    r = requests.post(f"{base}/api/deposit/depositions/{dep_id}/actions/publish",
                      params=p, timeout=60)
    r.raise_for_status()
    pub = r.json()
    concept = pub.get("conceptdoi") or pub.get("doi")
    return concept, pub.get("doi"), pub["links"].get("html", ""), dep_id


def cleanup_orphan_drafts(base, token):
    """Borra depósitos sin publicar (borradores huérfanos de intentos fallidos)."""
    p = {"access_token": token, "size": 100}
    r = requests.get(f"{base}/api/deposit/depositions", params=p, timeout=40)
    if r.status_code != 200:
        return 0
    removed = 0
    for x in r.json():
        if not x.get("submitted"):
            d = requests.delete(f"{base}/api/deposit/depositions/{x['id']}",
                                params={"access_token": token}, timeout=40)
            if d.status_code == 204:
                removed += 1
    return removed


# ── CITATION.cff ────────────────────────────────────────────────────────────
def citation_cff(title, repo, url, doi):
    return f"""cff-version: 1.2.0
message: "Si usas este software, cítalo con estos metadatos."
title: "{title}"
type: software
authors:
  - family-names: "Borrás Rocher"
    given-names: "Fernando"
    affiliation: "Universidad Miguel Hernández de Elche"
    orcid: "https://orcid.org/{ORCID}"
doi: "{doi}"
version: "1.0.0"
date-released: "{date.today().isoformat()}"
url: "{url}"
repository-code: "https://github.com/{GITHUB_USER}/{repo}"
license: {LICENSE}
"""


# ── index.html ──────────────────────────────────────────────────────────────
def app_in_index(html, url):
    return f'url:"{url}"' in html


def read_app_meta_from_index(html, url):
    """Extrae title, cat, desc_es, desc_en de una app ya presente en el índice."""
    m = re.search(r'\{ cat:"([a-z]+)", icon:"[^"]*", title:"([^"]+)", url:"'
                  + re.escape(url) + r'", doi:"([^"]*)"', html)
    if not m:
        return None
    cat, title, doi = m.group(1), m.group(2), m.group(3)
    block = html[m.start(): m.start() + 2500]
    des = re.search(r'es:\{ sub:"[^"]*", desc:"([^"]*)"', block)
    den = re.search(r'en:\{ sub:"[^"]*", desc:"([^"]*)"', block)
    return {"cat": cat, "title": title, "doi": doi,
            "desc_es": des.group(1) if des else "",
            "desc_en": den.group(1) if den else ""}


def insert_app_into_index(html, app):
    """Inserta un objeto de app nuevo justo antes del cierre del array `apps`."""
    ev_es = "Pendiente de registro sistemático de uso."
    ev_en = "Systematic usage records pending."
    obj = (f'  {{ cat:"{app["cat"]}", icon:"{app["icon"]}", title:"{app["title"]}", '
           f'url:"{app["url"]}", doi:"",\n'
           f'    es:{{ sub:"{app["sub_es"]}", desc:"{app["desc_es"]}", '
           f'tit:"{app.get("tit_es","")}", comp:"{app.get("comp_es","")}", evid:"{ev_es}" }},\n'
           f'    en:{{ sub:"{app["sub_en"]}", desc:"{app["desc_en"]}", '
           f'tit:"{app.get("tit_en","")}", comp:"{app.get("comp_en","")}", evid:"{ev_en}" }} }},\n')
    # el array termina en "];"
    m = re.search(r'\n\];', html)
    if not m:
        raise RuntimeError("No se encontró el cierre del array apps (`];`) en index.html")
    return html[:m.start()] + "\n" + obj + html[m.start():]


def patch_index_doi(html, url, doi):
    old = f'url:"{url}", doi:""'
    new = f'url:"{url}", doi:"{doi}"'
    if old not in html:
        return html, False
    return html.replace(old, new, 1), True


# ── main ────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Da de alta una app del catálogo fborrasumh/ia en Zenodo + GitHub.")
    ap.add_argument("--repo", required=True, help="nombre del repo de la app en GitHub")
    ap.add_argument("--sandbox", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-github", action="store_true", help="acuña DOI pero no toca GitHub")
    ap.add_argument("--branch", help="fuerza la rama del repo")
    # metadatos para apps que aún no están en el index.html
    ap.add_argument("--cat", choices=sorted(VALID_CATS))
    ap.add_argument("--title")
    ap.add_argument("--icon", default="ti-app-window")
    ap.add_argument("--sub-es"); ap.add_argument("--desc-es")
    ap.add_argument("--sub-en"); ap.add_argument("--desc-en")
    ap.add_argument("--tit-es", default=""); ap.add_argument("--comp-es", default="")
    ap.add_argument("--tit-en", default=""); ap.add_argument("--comp-en", default="")
    args = ap.parse_args()

    base = "https://sandbox.zenodo.org" if args.sandbox else "https://zenodo.org"
    ztok = os.environ.get("ZENODO_TOKEN", "")
    gtok = os.environ.get("GITHUB_TOKEN", "")
    if not args.dry_run and not ztok:
        sys.exit("Define ZENODO_TOKEN (export ZENODO_TOKEN=...)")
    if not args.no_github and not args.dry_run and not gtok:
        sys.exit("Define GITHUB_TOKEN o usa --no-github")

    repo = args.repo
    url = f"https://fborrasumh.github.io/{repo}/"

    # 1) leer el index.html actual del repo ia (o trabajar en seco)
    if args.dry_run and not gtok:
        html, index_sha = "", None
        print("(dry-run sin GITHUB_TOKEN: no se lee el índice remoto)")
    else:
        html, index_sha = gh_get_file(INDEX_REPO, INDEX_PATH, gtok or ztok, ref="main") \
            if gtok else (None, None)
        if html is None and gtok:
            sys.exit(f"No se pudo leer {INDEX_REPO}/{INDEX_PATH} en GitHub (revisa el token).")

    # 2) resolver metadatos de la app: del índice si ya está, o de los flags
    meta_from_index = read_app_meta_from_index(html, url) if html else None
    if meta_from_index:
        if meta_from_index["doi"]:
            print(f"✔ {repo} ya tiene DOI en el índice ({meta_from_index['doi']}). Nada que hacer.")
            return
        cat = meta_from_index["cat"]; title = meta_from_index["title"]
        desc_es = meta_from_index["desc_es"]; desc_en = meta_from_index["desc_en"]
        need_insert = False
    else:
        # app nueva: exige metadatos mínimos
        missing = [f for f in ("cat", "title", "sub_es", "desc_es", "sub_en", "desc_en")
                   if not getattr(args, f)]
        if missing:
            sys.exit("La app no está en el índice; faltan metadatos: --"
                     + ", --".join(m.replace("_", "-") for m in missing))
        cat = args.cat; title = args.title
        desc_es = args.desc_es; desc_en = args.desc_en
        need_insert = True

    print(f"App: {title}  ·  repo: {repo}  ·  cat: {cat}  ·  destino Zenodo: {base}")
    if args.dry_run:
        print("[dry-run] no se acuña DOI ni se toca GitHub.")
        if need_insert:
            print("[dry-run] se insertaría una ficha nueva en index.html.")
        return

    # 3) descargar el repo y publicar en Zenodo
    zip_bytes, branch = download_repo_zip(repo, args.branch)
    if not zip_bytes:
        sys.exit(f"No se pudo descargar el repo {repo} (¿nombre o rama correctos?).")
    meta = make_metadata(title, cat, url, repo, branch, desc_es, desc_en)
    try:
        concept, vdoi, record, _ = zenodo_publish(base, ztok, meta, zip_bytes, repo, branch)
    except requests.HTTPError as e:
        n = cleanup_orphan_drafts(base, ztok)
        sys.exit(f"Error publicando en Zenodo: {e}\n{getattr(e.response,'text','')[:300]}"
                 f"\n(Borradores huérfanos limpiados: {n}. Corrige y reintenta.)")
    print(f"✓ DOI de concepto: {concept}   ({record})")

    # guardar estado
    state = json.load(open(STATE_FILE)) if os.path.exists(STATE_FILE) else {}
    state[repo] = {"concept_doi": concept, "version_doi": vdoi,
                   "record": record, "branch": branch}
    json.dump(state, open(STATE_FILE, "w"), indent=2, ensure_ascii=False)

    if args.no_github:
        print("--no-github: DOI acuñado; no se sube CITATION.cff ni se actualiza el índice.")
        print(f"   Pega el DOI a mano en index.html: {concept}")
        return

    # 4) CITATION.cff en el repo de la app
    _, cff_sha = gh_get_file(repo, "CITATION.cff", gtok, ref=branch)
    gh_put_file(repo, "CITATION.cff",
                citation_cff(title, repo, url, concept).encode(),
                "Add CITATION.cff with Zenodo DOI", gtok, branch=branch, sha=cff_sha)
    print("✓ CITATION.cff subido a", f"{GITHUB_USER}/{repo}")

    # 5) actualizar index.html en el repo ia
    if need_insert:
        html = insert_app_into_index(html, {
            "cat": cat, "icon": args.icon, "title": title, "url": url,
            "sub_es": args.sub_es, "desc_es": desc_es,
            "sub_en": args.sub_en, "desc_en": desc_en,
            "tit_es": args.tit_es, "comp_es": args.comp_es,
            "tit_en": args.tit_en, "comp_en": args.comp_en})
        print("✓ Ficha nueva insertada en index.html")
    html, ok = patch_index_doi(html, url, concept)
    if not ok:
        print(f"⚠ No se pudo escribir el DOI en index.html; añádelo a mano: {concept}")
    else:
        gh_put_file(INDEX_REPO, INDEX_PATH, html.encode(),
                    f"Añadir DOI de Zenodo para {repo}", gtok, branch="main", sha=index_sha)
        print(f"✓ index.html actualizado en {GITHUB_USER}/{INDEX_REPO}")

    print(f"\nHecho. Registro Zenodo: {record}")


if __name__ == "__main__":
    main()
