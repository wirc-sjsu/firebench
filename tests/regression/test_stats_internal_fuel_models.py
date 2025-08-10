import tempfile
from firebench.tools import calculate_sha256
from firebench.stats import anderson_2015_stats
import hashlib

# Reference hash for figure generated using anderson_2015_stats for different units
REFERENCE_HASH_1 = "1fd65f7add5af642bf4650b9c81b5dfc450b6bf6be985e2fea8aa32b76a5b0cb"
REFERENCE_HASH_2 = "c1362de1a61d5a3aed2dc2b13c46b7e1117a2ea6e6e27a5ab42a1d93af71857b"


def sha256_fig_pixels(fig) -> str:
    fig.canvas.draw()
    buf = fig.canvas.buffer_rgba()
    return hashlib.sha256(memoryview(buf)).hexdigest()


def test_anderson_2015_stats_hash_match():
    # unit_wind="m/s", unit_ros="m/s", dpi=150
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        fig = anderson_2015_stats(output_filename=tmp.name, unit_wind="m/s", unit_ros="m/s", dpi=150)
        assert sha256_fig_pixels(fig) == REFERENCE_HASH_1

    # unit_wind="ft/min", unit_ros="km/h", dpi=150
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        fig = anderson_2015_stats(output_filename=tmp.name, unit_wind="ft/min", unit_ros="km/h", dpi=150)
        assert sha256_fig_pixels(fig) == REFERENCE_HASH_2
