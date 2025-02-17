import importlib
import platform
from importlib.metadata import version, PackageNotFoundError

# all packages that could impact measurements
watched_packages = [
    "numpy",
    "qcodes",
    "core_tools",
    "pulse_lib",
    "qconstruct",
    "qt_dataviewer",
    # Qblox
    "qblox_instruments",
    "q1pulse",
    # Keysight
    "hvi2_script",
    "keysight_fpga",
    "keysightSD1",
    "keysight_hvi",
    "keysight_tse",
    ]


def get_software_versions() -> dict[str, str]:
    result = {
        "Python": platform.python_version(),
        }
    for name in watched_packages:
        try:
            meta_version = version(name)
            version_info = meta_version
            if name not in ["qcodes", "numpy"]:
                package = importlib.import_module(name)
                source_version = getattr(package, "__version__", "not set")
                if source_version != meta_version:
                    version_info = f"{source_version} (meta: {meta_version})"
            result[name] = version_info
        except PackageNotFoundError:
            # print(name, "Not installed")
            pass
    return result


if __name__ == "__main__":
    from pprint import pprint
    pprint(get_software_versions())
