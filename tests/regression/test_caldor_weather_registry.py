from hashlib import sha256

from firebench.benchmarks import c001_caldor

WEATHER_REGISTRY_SHA256 = "66c89152344eca96c43e57aa82c1f5343ce8800e08468906d72312c8586e0890"


def test_caldor_weather_registry_manifest_is_stable():
    c001_caldor.build_registries()
    rows = []
    for group in c001_caldor.WX_GROUP_BENCHMARKS.values():
        for benchmark_id, weight in group.items():
            benchmark = c001_caldor.BENCHMARK_FUNCTIONS[benchmark_id]
            rows.append(
                "|".join(
                    (
                        benchmark_id,
                        benchmark.keywords["kpi_name_custom"],
                        benchmark.keywords["station_set"].value,
                        str(weight),
                    )
                )
            )

    assert len(rows) == 5148
    assert rows[0] == "FB001_WX001|Air temp MAE min W1 TSO|TSO|1"
    assert rows[311] == "FB001_WX312|FMC 10h Bias max W4 All sources|all sources|0"
    assert rows[312] == "FB001_WX313|Air temp MAE min WH1 TSO|TSO|1"
    assert rows[-1] == "FB001_WX5148|FMC 10h Bias max WH62 All sources|all sources|0"
    assert sha256(("\n".join(rows) + "\n").encode()).hexdigest() == WEATHER_REGISTRY_SHA256
