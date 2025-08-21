import os

def get_secret(name, default=""):
    """Reads Docker secrets from /run/secrets/"""
    secret_path = f"/run/secrets/{name}"
    try:
        with open(secret_path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return default