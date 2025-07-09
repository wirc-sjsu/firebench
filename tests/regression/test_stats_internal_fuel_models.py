import tempfile
from firebench.tools import calculate_sha256
from firebench.stats import anderson_2015_stats

# Reference hash for figure generated using anderson_2015_stats for different units
REFERENCE_HASH_1 = "f9e37728e6db114f9663c88470d23a579c4fee6a1bf5aeb1184fbeb570687267"
REFERENCE_HASH_2 = "d61811fc3865f655143dc8c2d2d667aa1a7875ce9e5ef6e9d37bda083b16a746"


def test_anderson_2015_stats_hash_match():
    # unit_wind="m/s", unit_ros="m/s", dpi=150
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        anderson_2015_stats(output_filename=tmp.name)
        current_hash = calculate_sha256(tmp.name)
        assert current_hash == REFERENCE_HASH_1
    # unit_wind="ft/min", unit_ros="km/h", dpi=150
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        anderson_2015_stats(output_filename=tmp.name)
        current_hash = calculate_sha256(tmp.name)
        assert current_hash == REFERENCE_HASH_1
