import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from textwrap import dedent
from zipfile import ZipFile

from packaging.version import Version

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

RUNTIME_DATA_FILES = {
    "firebench/resources/data/fuel_models/Anderson13.json",
    "firebench/resources/data/fuel_models/ScottandBurgan40.json",
    "firebench/resources/data/fuel_models/WUDAPT_urban.json",
    "firebench/resources/data/fuel_models/data_Anderson13.csv",
    "firebench/resources/data/fuel_models/data_ScottandBurgan40.csv",
    "firebench/resources/data/fuel_models/data_WUDAPT_urban.csv",
    "firebench/resources/data/ros_model_validation/Anderson_2015/Table_8.json",
    "firebench/resources/data/ros_model_validation/Anderson_2015/Table_A1.json",
    "firebench/resources/data/ros_model_validation/Anderson_2015/data_Table_8.csv",
    "firebench/resources/data/ros_model_validation/Anderson_2015/data_Table_A1.csv",
    "firebench/resources/wx_sensor_height_providers.json",
    "firebench/resources/wx_sensor_height_stations.json",
    "firebench/resources/wx_sensor_height_trusted_history.json",
}


def _find_wheel(path: Path) -> Path:
    if path.is_file():
        return path

    wheels = sorted(path.glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError(f"Expected exactly one wheel in {path}, found {len(wheels)}.")
    return wheels[0]


def _check_wheel_contents(wheel: Path) -> None:
    with ZipFile(wheel) as archive:
        missing = RUNTIME_DATA_FILES.difference(archive.namelist())
    if missing:
        formatted = "\n".join(f"- {path}" for path in sorted(missing))
        raise RuntimeError(f"Wheel is missing runtime data files:\n{formatted}")


def _check_isolated_import(wheel: Path, expected_version: str) -> None:
    with TemporaryDirectory(prefix="firebench-wheel-check-") as temp_dir:
        temp_path = Path(temp_dir)
        site_dir = temp_path / "site"
        work_dir = temp_path / "work"
        site_dir.mkdir()
        work_dir.mkdir()
        (work_dir / "data").mkdir()

        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--target",
                str(site_dir),
                str(wheel),
            ],
            check=True,
        )

        verification_code = dedent(f"""
            from pathlib import Path

            import firebench
            from firebench.standardize import validate_installed_sensor_height_resources
            from firebench.tools import (
                get_firebench_data_directory,
                read_data_file,
                read_fuel_data_file,
            )

            package_path = Path(firebench.__file__).resolve()
            expected_site = Path({str(site_dir)!r}).resolve()
            if expected_site not in package_path.parents:
                raise RuntimeError(f"Imported FireBench from {{package_path}}, not {{expected_site}}.")
            if firebench.__version__ != {expected_version!r}:
                raise RuntimeError(
                    f"Installed FireBench version is {{firebench.__version__}}, "
                    f"expected {expected_version}."
                )

            data_path = Path(get_firebench_data_directory()).resolve()
            if expected_site not in data_path.parents:
                raise RuntimeError(f"Resolved runtime data outside the wheel install: {{data_path}}.")

            expected_counts = {{
                "Anderson13": 13,
                "ScottandBurgan40": 40,
                "WUDAPT_urban": 10,
            }}
            for name, expected_count in expected_counts.items():
                data = read_fuel_data_file(name)
                if data["nb_fuel_classes"] != expected_count:
                    raise RuntimeError(
                        f"{{name}} has {{data['nb_fuel_classes']}} classes, expected {{expected_count}}."
                    )

            anderson = read_data_file(
                "Table_A1",
                "ros_model_validation/Anderson_2015",
            )
            if anderson["nb_fuel_classes"] == 0:
                raise RuntimeError("The packaged Anderson validation table is empty.")

            sensor_height_counts = validate_installed_sensor_height_resources()
            if any(count == 0 for count in sensor_height_counts.values()):
                raise RuntimeError(
                    f"An installed sensor-height resource is empty: {{sensor_height_counts}}."
                )

            print(f"Verified runtime data from {{data_path}}")
            """)
        env = os.environ.copy()
        env.pop("FIREBENCH_DATA_PATH", None)
        env["PYTHONPATH"] = str(site_dir)
        subprocess.run(
            [sys.executable, "-c", verification_code],
            cwd=work_dir,
            env=env,
            check=True,
        )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: check_wheel_runtime_data.py WHEEL_OR_DIST_DIRECTORY")

    wheel = _find_wheel(Path(sys.argv[1]).resolve())
    project_config = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    expected_version = str(Version(project_config["project"]["version"]))
    _check_wheel_contents(wheel)
    _check_isolated_import(wheel, expected_version)
    print(f"Verified wheel runtime resources: {wheel}")


if __name__ == "__main__":
    main()
