"""Standalone script to pull and vendorize pyisobmff."""

import argparse
import io
import logging
import os
import shlex
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

PYISOBMFF_REPO = "https://github.com/chemag/pyisobmff.git"

def main(base_dir: Path):
    base_pyisobmff_dir = get_pyisobmff(base_dir, git_ref="master")
    vendorize_pyisobmff(base_pyisobmff_dir)


def get_pyisobmff(base_dir: Path, git_ref: str) -> Path:
    """Ensure pyisobmff git repo is present locally set to the relevant commit/branch/tag."""
    base_pyisobmff_dir = base_dir / "pyisobmff"
    if not base_pyisobmff_dir.exists():
        logger.debug(f"Cloning pyisobmff to {base_pyisobmff_dir}...")
        subprocess.run(
            shlex.split(f"git clone {PYISOBMFF_REPO}"),
            cwd=base_dir,
            check=True
        )
    if git_ref == "master":
        subprocess.run(
            shlex.split(f"git switch {git_ref}"),
            cwd=base_pyisobmff_dir,
            check=True
        )
        subprocess.run(
            shlex.split(f"git pull origin {git_ref}"),
            cwd=base_pyisobmff_dir,
            check=True
        )
    else:
        subprocess.run(
            shlex.split(f"git switch --detach {git_ref}"),
            cwd=base_pyisobmff_dir,
            check=True
        )
    return base_pyisobmff_dir


def vendorize_pyisobmff(base_pyisobmff_dir: Path):
    completed_process = subprocess.run(
        shlex.split(f"git rev-parse --short HEAD"),
        cwd=base_pyisobmff_dir,
        check=True,
        capture_output=True
    )
    git_hash = completed_process.stdout.decode("utf-8").strip()
    version_file_contents = (
        f"pyisobmff\n"
        f"- license: MIT\n"
        f"- code repository: https://github.com/chemag/pyisobmff\n"
        f"- current version: {git_hash}\n"
    )
    target_dir = Path(__file__).parents[1] / "src/gimirrai/vendorized"
    version_file = target_dir / "pyisobmff_version.txt"
    with version_file.open(mode="w") as fh:
        fh.write(version_file_contents)
    pyisobmff_source_dir = base_pyisobmff_dir / "isobmff"
    pyisobmff_vendorization_dir = target_dir / "isobmff"
    if pyisobmff_vendorization_dir.exists():
        subprocess.run(
            shlex.split(
                f"rm --recursive --force -I {pyisobmff_vendorization_dir}"),
            check=True,
        )
    subprocess.run(
        shlex.split(f"cp --recursive {pyisobmff_source_dir} {target_dir}"),
        check=True,
    )



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    base_dir = Path(os.getenv("GIMIRRAI_VENDORIZATION_GIT_CLONE_DIR", Path.home() / "dev"))
    main(base_dir)
