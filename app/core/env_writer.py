"""
Escreve chaves no .env sem perder comentários/ordem das linhas existentes.
Usado pela tela de configuração (/api/settings) para persistir credenciais
de ML/Shopee sem exigir edição manual do arquivo.
"""
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def update_env_file(updates: dict[str, str]) -> None:
    if not updates:
        return

    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    pending = dict(updates)
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in pending:
                new_lines.append(f"{key}={pending.pop(key)}")
                continue
        new_lines.append(line)

    for key, value in pending.items():
        new_lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
