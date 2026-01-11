from enum import Enum
from importlib.resources import files
from .utils import PublicKeyImportError


class Certificates(Enum):
    FB_VERIFIED_INPUT_REQUIREMENTS = "fb-verified-input-requirements"
    FB_VERIFIED_OBS_DATASET = "fb-verified-obs-dataset"
    FB_BENCHMARK_RUN_INTERNAL = "fb-benchmark-run-internal"
    FB_MODEL_RUN_INTERNAL = "fb-model-run-internal"
    FB_VERIFICATION_LVL = "fb-verification-lvl"


class KeyId(Enum):
    FB_PROD_2026_01 = "fb-prod-2026-01"


_FB_PUBLIC_KEYS = {
    KeyId.FB_PROD_2026_01.value: "firebench-prod-2026-01.asc",
}
_DEFAULT_KEY_PATH = "resources/public_keys"


def get_public_key(key_name):
    try:
        path = files("firebench").joinpath(f"{_DEFAULT_KEY_PATH}/{_FB_PUBLIC_KEYS[key_name]}")
    except KeyError:
        raise PublicKeyImportError(f"Public Key import fail for key {key_name}")
    with open(path, "r", encoding="utf-8") as f:
        pubkey_armor = f.read()
    return pubkey_armor
