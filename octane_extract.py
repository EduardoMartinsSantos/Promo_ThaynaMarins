"""
Extrator de work items do ALM Octane via REST API.

Autenticacao (definir em variaveis de ambiente ou arquivo .env):
  OCTANE_URL             -> ex: https://octane.suaempresa.com:8080
  OCTANE_SHARED_SPACE    -> ID do shared space (numero)
  OCTANE_WORKSPACE       -> ID do workspace (numero)
  OCTANE_CLIENT_ID       -> API access client id (gerado em Settings > Spaces > API Access)
  OCTANE_CLIENT_SECRET   -> API access client secret

Uso:
  python octane_extract.py --entity defects --output defects.xlsx
  python octane_extract.py --entity stories --fields id,name,phase,owner,creation_time \
      --query "phase={name='In Progress'}" --output stories.csv
  python octane_extract.py --entity features --output features.json

Tipos de entidade comuns: defects, stories, tasks, tests, requirements, features, epics, work_items
"""

import argparse
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_FIELDS = ["id", "name", "phase", "owner", "priority", "creation_time", "last_modified"]

PAGE_SIZE = 100


def build_session() -> tuple[requests.Session, str, str, str]:
    base_url = os.environ.get("OCTANE_URL", "").rstrip("/")
    shared_space = os.environ.get("OCTANE_SHARED_SPACE")
    workspace = os.environ.get("OCTANE_WORKSPACE")
    client_id = os.environ.get("OCTANE_CLIENT_ID")
    client_secret = os.environ.get("OCTANE_CLIENT_SECRET")

    missing = [
        name
        for name, val in [
            ("OCTANE_URL", base_url),
            ("OCTANE_SHARED_SPACE", shared_space),
            ("OCTANE_WORKSPACE", workspace),
            ("OCTANE_CLIENT_ID", client_id),
            ("OCTANE_CLIENT_SECRET", client_secret),
        ]
        if not val
    ]
    if missing:
        sys.exit(f"Erro: defina as variaveis de ambiente: {', '.join(missing)}")

    session = requests.Session()
    session.headers["Accept"] = "application/json"
    session.headers["Content-Type"] = "application/json"

    resp = session.post(
        f"{base_url}/authentication/sign_in",
        json={"client_id": client_id, "client_secret": client_secret},
    )
    resp.raise_for_status()

    return session, base_url, shared_space, workspace


def extract_field(fields: dict, name: str):
    value = fields.get(name)
    if isinstance(value, dict):
        return value.get("name") or value.get("id")
    if isinstance(value, list):
        return ", ".join(v.get("name", str(v)) if isinstance(v, dict) else str(v) for v in value)
    return value


def fetch_entities(
    session: requests.Session,
    base_url: str,
    shared_space: str,
    workspace: str,
    entity: str,
    field_names: list[str],
    query: str | None,
) -> list[dict]:
    items = []
    offset = 0
    total = None
    url = f"{base_url}/api/shared_spaces/{shared_space}/workspaces/{workspace}/{entity}"

    while total is None or offset < total:
        params = {
            "fields": ",".join(field_names),
            "offset": offset,
            "limit": PAGE_SIZE,
        }
        if query:
            params["query"] = query

        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        total = data["total_count"]

        for raw in data["data"]:
            items.append({name: extract_field(raw, name) for name in field_names})

        offset += PAGE_SIZE
        print(f"  {min(offset, total)}/{total} itens obtidos", file=sys.stderr)

    return items


def save_output(items: list[dict], output_path: str) -> None:
    ext = os.path.splitext(output_path)[1].lower()

    if ext == ".json":
        import json

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        return

    import pandas as pd

    df = pd.DataFrame(items)
    if ext == ".xlsx":
        df.to_excel(output_path, index=False)
    elif ext == ".csv":
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    else:
        sys.exit(f"Formato de saida nao suportado: {ext} (use .xlsx, .csv ou .json)")


def main():
    parser = argparse.ArgumentParser(description="Extrai work items do ALM Octane via REST API")
    parser.add_argument(
        "--entity",
        required=True,
        help="Tipo de entidade: defects, stories, tasks, tests, requirements, features, epics, work_items",
    )
    parser.add_argument(
        "--fields",
        default=",".join(DEFAULT_FIELDS),
        help=f"Campos separados por virgula (default: {','.join(DEFAULT_FIELDS)})",
    )
    parser.add_argument("--query", help="Filtro no formato do Octane, ex: \"phase={name='In Progress'}\"")
    parser.add_argument("--output", required=True, help="Arquivo de saida: .xlsx, .csv ou .json")
    args = parser.parse_args()

    field_names = [f.strip() for f in args.fields.split(",") if f.strip()]
    session, base_url, shared_space, workspace = build_session()

    print(f"Consultando Octane: entity={args.entity} query={args.query}", file=sys.stderr)
    items = fetch_entities(session, base_url, shared_space, workspace, args.entity, field_names, args.query)

    save_output(items, args.output)
    print(f"OK: {len(items)} itens salvos em {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
