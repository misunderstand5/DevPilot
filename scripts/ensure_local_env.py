"""Idempotently provision missing local-only credentials without printing secrets."""

from pathlib import Path
import secrets
import json
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
CREDENTIALS_PATH = ROOT / ".devpilot-credentials.txt"


def parse_env(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def generated_password() -> str:
    # URL-safe characters also work unescaped in Compose and SQLAlchemy URLs.
    return secrets.token_urlsafe(24)


def existing_mysql_credentials() -> dict[str, str]:
    """Reuse credentials baked into an existing container/volume pair."""
    try:
        completed = subprocess.run(
            ["docker", "inspect", "devpilot-mysql"], capture_output=True,
            text=True, check=True, timeout=10,
        )
        payload = json.loads(completed.stdout)
        env_items = payload[0]["Config"]["Env"]
        env = dict(item.split("=", 1) for item in env_items if "=" in item)
        return {key: env[key] for key in ("MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD") if env.get(key)}
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, IndexError, json.JSONDecodeError):
        return {}


def main() -> None:
    original = ENV_PATH.read_text(encoding="utf-8-sig") if ENV_PATH.exists() else ""
    values = parse_env(original)
    generated: dict[str, str] = {}
    container_values = existing_mysql_credentials()
    required = {
        "MYSQL_ROOT_PASSWORD": generated_password,
        "MYSQL_PASSWORD": generated_password,
        "AUTH_SECRET_KEY": lambda: secrets.token_urlsafe(48),
        "AUTH_ADMIN_PASSWORD": generated_password,
        "AUTH_ENGINEER_PASSWORD": generated_password,
    }
    for key, factory in required.items():
        desired = container_values.get(key)
        if desired and values.get(key) != desired:
            generated[key] = desired
            values[key] = desired
        elif not values.get(key):
            generated[key] = factory()
            values[key] = generated[key]

    if generated:
        existing_lines = original.splitlines()
        replaced = set()
        output_lines = []
        for line in existing_lines:
            key = line.split("=", 1)[0].strip() if "=" in line else ""
            if key in generated:
                output_lines.append(f"{key}={generated[key]}")
                replaced.add(key)
            else:
                output_lines.append(line)
        if generated.keys() - replaced:
            output_lines.extend(["", "# Generated local-only credentials (do not commit)"])
            output_lines.extend(f"{key}={generated[key]}" for key in generated.keys() - replaced)
        ENV_PATH.write_text("\n".join(output_lines).rstrip() + "\n", encoding="utf-8")

    # Keep a small user-facing login note separate from the full environment.
    credentials = (
        "DevPilot local login credentials\n"
        f"Tenant: {values.get('AUTH_DEFAULT_TENANT', 'devpilot')}\n"
        f"Tenant admin: admin / {values['AUTH_ADMIN_PASSWORD']}\n"
        f"Developer: engineer / {values['AUTH_ENGINEER_PASSWORD']}\n"
        "This file is local-only and ignored by Git.\n"
    )
    CREDENTIALS_PATH.write_text(credentials, encoding="utf-8")
    state = "generated" if generated else "already_configured"
    print(f"local_env={state} credentials_file={CREDENTIALS_PATH.name}")


if __name__ == "__main__":
    main()
