"""Create a minimal, valid FireBench model-output file."""

from pathlib import Path

import numpy as np

from firebench.standardize import new_std_file, validate_h5_std
from firebench.tools import StandardVariableNames

OUTPUT = Path("model_output.h5")


def create_model_output(path: Path = OUTPUT) -> Path:
    """Write a small time-dependent rate-of-spread field and validate the file."""
    rate_of_spread = np.array(
        [
            [[0.10, 0.12, 0.09], [0.08, 0.11, 0.07]],
            [[0.14, 0.16, 0.12], [0.11, 0.15, 0.10]],
        ],
        dtype=np.float32,
    )

    with new_std_file(str(path), authors="Example User", overwrite=True) as h5:
        h5.attrs["model_name"] = "Synthetic spread example"
        h5.attrs["description"] = "Small model-output file used by the FireBench tutorial"

        surface = h5.require_group("spatial_2d/surface")
        surface.attrs["crs"] = "EPSG:32610"

        time = surface.create_dataset(StandardVariableNames.TIME.value, data=np.array([0.0, 60.0]))
        time.attrs["units"] = "second"
        time.attrs["time_origin"] = "2021-08-17T00:00:00+00:00"

        position_x = surface.create_dataset("position_x", data=np.array([0.0, 30.0, 60.0]))
        position_x.attrs["units"] = "meter"
        position_y = surface.create_dataset("position_y", data=np.array([0.0, 30.0]))
        position_y.attrs["units"] = "meter"

        ros = surface.create_dataset(StandardVariableNames.RATE_OF_SPREAD.value, data=rate_of_spread)
        ros.attrs["units"] = "meter / second"
        ros.attrs["dimensions"] = "time, position_y, position_x"
        ros.attrs["description"] = "Synthetic surface-fire rate of spread"

        validate_h5_std(h5)

    return path


if __name__ == "__main__":
    created = create_model_output()
    print(f"Wrote {created}")
