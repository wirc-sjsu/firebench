from enum import Enum, auto


class Certificates(Enum):
    FB_VERIFIED_INPUT_REQUIREMENTS = "fb-verified-input-requirements"
    FB_VERIFIED_OBS_DATASET = "fb-verified-obs-dataset"
    FB_BENCHMARK_RUN_INTERNAL = "fb-benchmark-run-internal"
    FB_MODEL_RUN_INTERNAL = "fb-model-run-internal"


class KeyId(Enum):
    FB_PROD_2026_01 = "fb-prod-2026-01"
