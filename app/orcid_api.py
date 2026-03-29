import json
import requests
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config_orcid.json"


def save_config(client_id, client_secret, token):
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "token": token
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_config():
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def get_token(client_id, client_secret):
    r = requests.post(
        "https://orcid.org/oauth/token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "/read-public",
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("access_token", "")