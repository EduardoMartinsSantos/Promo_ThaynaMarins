"""
Extrator de issues do Jira via REST API.

Autenticacao (definir em variaveis de ambiente ou arquivo .env):
  JIRA_URL         -> ex: https://seudominio.atlassian.net  (ou URL do Server/DC)
  JIRA_EMAIL       -> email da conta (somente Jira Cloud)
  JIRA_API_TOKEN   -> API token (Jira Cloud, gerado em id.atlassian.com)
  JIRA_PAT         -> Personal Access Token (Jira Server/Data Center, alternativa ao par acima)

Uso:
  python jira_extract.py --jql "project = PROJ AND status != Done" --output issues.xlsx
  python jira_extract.py --jql "project = PROJ" --fields key,summary,status,assignee,created --output issues.csv
  python jira_extract.py --jql "project = PROJ" --output issues.json
"""

import argparse
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_FIELDS = [
    "key",
    "summary",
    "status",
    "assignee",
    "reporter",
    "priority",
    "issuetype",
    "created",
    "updated",
]

PAGE_SIZE = 100


def build_session() -> tuple[requests.Session, str]:
    base_url = os.environ.get("JIRA_URL", "").rstrip("/")
    if not base_url:
        sys.exit("Erro: defina JIRA_URL (ex: https://seudominio.atlassian.net)")

    session = requests.Session()
    pat = os.environ.get("JIRA_PAT")
    if pat:
        session.headers["Authorization"] = f"Bearer {pat}"
    else:
        email = os.environ.get("JIRA_EMAIL")
        token = os.environ.get("JIRA_API_TOKEN")
        if not email or not token:
            sys.exit(
                "Erro: defina JIRA_EMAIL + JIRA_API_TOKEN (Cloud) "
                "ou JIRA_PAT (Server/Data Center)"
            )
        session.auth = (email, token)

    session.headers["Accept"] = "application/json"
    return session, base_url


def extract_field(fields: dict, name: str):
    value = fields.get(name)
    if isinstance(value, dict):
        return value.get("displayName") or value.get("name") or value.get("value")
    if isinstance(value, list):
        return ", ".join(
            v.get("name", str(v)) if isinstance(v, dict) else str(v) for v in value
        )
    return value


def fetch_issues(session: requests.Session, base_url: str, jql: str, field_names: list[str]) -> list[dict]:
    issues = []
    start_at = 0
    total = None

    while total is None or start_at < total:
        resp = session.get(
            f"{base_url}/rest/api/2/search",
            params={
                "jql": jql,
                "startAt": start_at,
                "maxResults": PAGE_SIZE,
                "fields": ",".join(field_names),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        total = data["total"]

        for raw in data["issues"]:
            row = {"key": raw["key"]}
            row.update(
                {name: extract_field(raw["fields"], name) for name in field_names if name != "key"}
            )
            issues.append(row)

        start_at += PAGE_SIZE
        print(f"  {min(start_at, total)}/{total} issues obtidas", file=sys.stderr)

    return issues


def save_output(issues: list[dict], output_path: str) -> None:
    ext = os.path.splitext(output_path)[1].lower()

    if ext == ".json":
        import json

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(issues, f, ensure_ascii=False, indent=2)
        return

    import pandas as pd

    df = pd.DataFrame(issues)
    if ext == ".xlsx":
        df.to_excel(output_path, index=False)
    elif ext == ".csv":
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    else:
        sys.exit(f"Formato de saida nao suportado: {ext} (use .xlsx, .csv ou .json)")


def main():
    parser = argparse.ArgumentParser(description="Extrai issues do Jira via REST API")
    parser.add_argument("--jql", required=True, help='Filtro JQL, ex: "project = PROJ"')
    parser.add_argument(
        "--fields",
        default=",".join(DEFAULT_FIELDS),
        help=f"Campos separados por virgula (default: {','.join(DEFAULT_FIELDS)})",
    )
    parser.add_argument("--output", required=True, help="Arquivo de saida: .xlsx, .csv ou .json")
    args = parser.parse_args()

    field_names = [f.strip() for f in args.fields.split(",") if f.strip()]
    session, base_url = build_session()

    print(f"Consultando Jira: {args.jql}", file=sys.stderr)
    issues = fetch_issues(session, base_url, args.jql, field_names)

    save_output(issues, args.output)
    print(f"OK: {len(issues)} issues salvas em {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
