from importlib.resources import files

FB_PUBLIC_KEYS = {
    "fb-prod-2026-01": "firebench-prod-2026-01.asc",
}
DEFAULT_KEY_PATH = "resources/public_keys"


def get_public_key(key_name):
    path = files("firebench").joinpath(f"{DEFAULT_KEY_PATH}/{FB_PUBLIC_KEYS[{key_name}]}")
    with open(path, "r", encoding="utf-8") as f:
        pubkey_armor = f.read()
    return pubkey_armor
