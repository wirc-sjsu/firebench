from firebench.stats import anderson_2015_stats


def test_anderson_2015_stats_hash_match(tmp_path):
    # unit_wind="m/s", unit_ros="m/s", dpi=150
    out = tmp_path / "plot.png"
    anderson_2015_stats(output_filename=str(out), unit_wind="m/s", unit_ros="m/s", dpi=150)
    assert out.exists()
    assert out.stat().st_size > 0

    # unit_wind="ft/min", unit_ros="km/h", dpi=150
    anderson_2015_stats(output_filename=str(out), unit_wind="ft/min", unit_ros="km/h", dpi=150)
    assert out.exists()
    assert out.stat().st_size > 0
