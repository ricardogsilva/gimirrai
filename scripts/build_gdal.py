"""Standalone script to download, compile and install GDAL"""

import argparse
import logging
import os
import shlex
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def main(base_dir: Path, install_dir: Path, git_ref: str, force_rebuild: bool):
    if is_library_installed("gdal") and not force_rebuild:
        logger.info("gdal is already present.")
    else:
        base_gdal_dir = get_gdal(base_dir, git_ref)
        if (patches_dir := Path(__file__).parents[1] / "patches/gdal").is_dir():
            apply_gdal_patches(base_gdal_dir, patches_dir)
        build_gdal(base_gdal_dir, install_dir)


def build_gdal(base_dir: Path, install_dir: Path):
    build_dir = base_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        shlex.split(
            f"""
            cmake
            -DCMAKE_INSTALL_PREFIX={str(install_dir)}
            -DCMAKE_BUILD_TYPE=Release \
            -DGDAL_BUILD_OPTIONAL_DRIVERS=OFF \
            -DOGR_BUILD_OPTIONAL_DRIVERS=OFF \
            -DGDAL_ENABLE_DRIVER_JP2OPENJPEG=ON \
            -DGDAL_ENABLE_DRIVER_PNG=ON \
            -DGDAL_ENABLE_DRIVER_JPEG=ON \
            -DOGR_ENABLE_DRIVER_GPKG=ON \
            -DOGR_ENABLE_DRIVER_MVT=ON \
            -DGDAL_ENABLE_DRIVER_OGCAPI=ON \
            -DOGR_ENABLE_DRIVER_SQLITE=ON \
            -DGDAL_ENABLE_DRIVER_MBTILES=ON \
            -DGDAL_ENABLE_DRIVER_HEIF=ON \
            ..
            """
        ),
        cwd=build_dir,
        check=True
    )
    subprocess.run(shlex.split("make -j4"), cwd=build_dir, check=True)
    subprocess.run(shlex.split(f"sudo make install"), cwd=build_dir, check=True)
    subprocess.run(shlex.split("sudo ldconfig"), cwd=build_dir, check=True)


def apply_gdal_patches(base_dir: Path, patches_dir: Path):
    subprocess.run(
        shlex.split("git restore ."),
        cwd=base_dir,
        check=True
    )
    for item in patches_dir.iterdir():
        if item.is_file():
            subprocess.run(
                shlex.split(f"git apply {str(item)}"),
                cwd=base_dir,
                check=True
            )


def get_gdal(base_dir: Path, git_ref: str) -> Path:
    """Ensure GDAL git repo is present locally set to the relevant commit/branch/tag."""
    base_gdal_dir = base_dir / "gdal"
    if not base_gdal_dir.exists():
        logger.debug(f"Cloning gdal to {base_gdal_dir}...")
        subprocess.run(
            shlex.split("git clone https://github.com/OSGeo/gdal.git"),
            cwd=base_dir,
            check=True
        )
    subprocess.run(
        shlex.split(f"git switch --detach {git_ref}"),
        cwd=base_gdal_dir,
        check=True
    )
    return base_gdal_dir


def is_library_installed(name: str) -> bool:
    if name.find("main") != -1 and name.find("reference") != -1:
        raise RuntimeError(
            "`name` param can not contain `main` and `reference` substrings.")
    _r = subprocess.run(
        shlex.split(f"gcc -l{name}"),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False
    )
    if _r.stdout:
        _ = _r.stdout.decode("utf-8")
        if _.find("main") != -1 and _.find("reference") != -1:
            return True
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gdal-git-ref", default="v3.7.2")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    base_dir = Path(os.getenv("GDAL_GIT_CLONE_DIR", Path.home() / "dev"))
    install_dir = Path(os.getenv("GDAL_INSTALL_DIR", "/usr/local/"))
    main(
        base_dir=base_dir,
        install_dir=install_dir,
        git_ref=args.gdal_git_ref,
        force_rebuild=args.force_rebuild
    )

