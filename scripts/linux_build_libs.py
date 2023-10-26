"""
File containing code to build Linux libraries for LibHeif and the LibHeif itself.

This file was modified from pillow-heif's `libheif/linux_build_libs.py` in order
to allow modifying the version of libheif that gets downloaded and built.

"""

import argparse
import shlex
import sys
import os
import re
import subprocess
from pathlib import Path
from platform import machine

# 0
BUILD_DIR = os.environ.get("BUILD_DIR", "/tmp/ph_build_stuff")
INSTALL_DIR_LIBS = os.environ.get("INSTALL_DIR_LIBS", "/usr")
PH_LIGHT_VERSION = sys.maxsize <= 2**32 or os.getenv("PH_LIGHT_ACTION", "0") != "0"

LIBX265_URL = "https://bitbucket.org/multicoreware/x265_git/get/0b75c44c10e605fe9e9ebed58f04a46271131827.tar.gz"
LIBAOM_URL = "https://aomedia.googlesource.com/aom/+archive/v3.6.1.tar.gz"
LIBDE265_URL = "https://github.com/strukturag/libde265/releases/download/v1.0.12/libde265-1.0.12.tar.gz"


def build_libheif(
        base_dir: Path, 
        install_dir: Path, 
        git_ref: str,
        build_examples: bool = True
):
    """Get, compile and install libheif."""
    base_libheif_dir = get_libheif(base_dir, git_ref)
    subprocess.run(
        shlex.split("git restore ."),
        cwd=base_libheif_dir,
        check=True
    )
    for item in (Path(__file__).parents[1] / "patches/libheif").iterdir():
        if item.is_file():
            subprocess.run(
                shlex.split(f"git apply {str(item)}"),
                # shlex.split(f"patch --strip 1 --forward --input {str(item)}"),
                cwd=base_libheif_dir,
                check=True
            )
    build_dir = base_libheif_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        shlex.split(
            f"""
            cmake
            -DCMAKE_INSTALL_PREFIX={str(install_dir)}
            -DCMAKE_BUILD_TYPE=Release
            -DWITH_EXAMPLES={'ON' if build_examples else 'OFF'}
            -DWITH_RAV1E=OFF 
            -DWITH_DAV1D=OFF 
            -DWITH_SvtEnc=OFF
            -DWITH_LIBSHARPYUV=OFF 
            -DENABLE_PLUGIN_LOADING=OFF
            ..
            """
        ), 
        cwd=build_dir, 
        check=True
    )
    subprocess.run(shlex.split("make -j4"), cwd=build_dir, check=True)
    subprocess.run(shlex.split(f"sudo make install"), cwd=build_dir, check=True)
    subprocess.run(shlex.split("sudo ldconfig"), cwd=build_dir, check=True)


def get_libheif(base_dir: Path, git_ref: str) -> Path:
    """Ensure libheif git repo is present locally set to the relevant commit/branch/tag."""
    base_libheif_dir = base_dir / "libheif"
    if not base_libheif_dir.exists():
        print(f"Cloning libheif to {base_libheif_dir}...")
        subprocess.run(
            shlex.split("git clone https://github.com/strukturag/libheif.git"), 
            cwd=base_dir,
            check=True
        )
    subprocess.run(
        shlex.split(f"git switch --detach {git_ref}"),
        cwd=base_libheif_dir,
        check=True
    )
    return base_libheif_dir


def download_file(url: str, out_path: str) -> bool:
    n_download_clients = 2
    for _ in range(2):
        try:
            subprocess.run(
                ["wget", "-q", "--no-check-certificate", url, "-O", out_path],
                timeout=90,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                check=True,
            )
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            break
        except FileNotFoundError:
            n_download_clients -= 1
            break
    for _ in range(2):
        try:
            subprocess.run(["curl", "-L", url, "-o", out_path], timeout=90, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL, check=True)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            break
        except FileNotFoundError:
            n_download_clients -= 1
            break
    if not n_download_clients:
        raise OSError("Both curl and wget cannot be found.")
    return False


def download_extract_to(url: str, out_path: str, strip: bool = True):
    os.makedirs(out_path, exist_ok=True)
    _archive_path = os.path.join(out_path, "download.tar.gz")
    download_file(url, _archive_path)
    _tar_cmd = f"tar -xf {_archive_path} -C {out_path}"
    if strip:
        _tar_cmd += " --strip-components 1"
    subprocess.run(_tar_cmd.split(), check=True)
    os.remove(_archive_path)


def tool_check_version(name: str, min_version: str) -> bool:
    try:
        _ = subprocess.run([name, "--version"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    _regexp = r"version\s*(\d+(\.\d+){2})" if name == "nasm" else r"(\d+(\.\d+){2})$"  # cmake
    m_groups = re.search(_regexp, _.stdout.decode("utf-8"), flags=re.MULTILINE + re.IGNORECASE)
    if m_groups is None:
        return False
    current_version = tuple(map(int, str(m_groups.groups()[0]).split(".")))
    min_version = tuple(map(int, min_version.split(".")))
    if current_version >= min_version:
        print(f"Tool {name} with version {m_groups.groups()[0]} satisfy requirements.", flush=True)
        return True
    return False


def check_install_nasm(version: str):
    if not re.match("(i[3-6]86|x86_64)$", machine()):
        return True
    if tool_check_version("nasm", version):
        return True
    print(f"Can not find `nasm` with version >={version}, installing...")
    _tool_path = os.path.join(BUILD_DIR, "nasm")
    if os.path.isdir(_tool_path):
        print("Cache found for nasm", flush=True)
        os.chdir(_tool_path)
    else:
        download_extract_to(f"https://www.nasm.us/pub/nasm/releasebuilds/{version}/nasm-{version}.tar.gz", _tool_path)
        os.chdir(_tool_path)
        subprocess.run(["./configure"], check=True)
        subprocess.run("make".split(), check=True)
    subprocess.run("make install".split(), check=True)
    subprocess.run("nasm --version".split(), check=True)
    subprocess.run(f"chmod -R 774 {_tool_path}".split(), check=True)
    return True


def is_musllinux() -> bool:
    _ = subprocess.run("ldd --version".split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if _.stdout and _.stdout.decode("utf-8").find("musl") != -1:
        return True
    return False


def is_library_installed(name: str) -> bool:
    if name.find("main") != -1 and name.find("reference") != -1:
        raise Exception("`name` param can not contain `main` and `reference` substrings.")
    _r = subprocess.run(f"gcc -l{name}".split(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if _r.stdout:
        _ = _r.stdout.decode("utf-8")
        if _.find("main") != -1 and _.find("reference") != -1:
            return True
    return False


def run_print_if_error(args) -> None:
    _ = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if _.returncode != 0:
        print(_.stdout.decode("utf-8"), flush=True)
        raise ChildProcessError(f"Failed: {args}")


def build_lib_linux(url: str, name: str, musl: bool = False):
    _lib_path = os.path.join(BUILD_DIR, name)
    if os.path.isdir(_lib_path):
        print(f"Cache found for {name}", flush=True)
        os.chdir(os.path.join(_lib_path, "build")) if name != "x265" else os.chdir(_lib_path)
    else:
        _hide_build_process = True
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        _linux_dir = os.path.join(_script_dir, "linux")
        if name == "x265":
            download_extract_to(url, _lib_path)
            os.chdir(_lib_path)
        else:
            _build_path = os.path.join(_lib_path, "build")
            os.makedirs(_build_path)
            if name == "aom":
                download_extract_to(url, os.path.join(_lib_path, "aom"), False)
                if musl:
                    patch_path = os.path.join(_linux_dir, "aom-musl/fix-stack-size-e53da0b-2.patch")
                    os.chdir(os.path.join(_lib_path, "aom"))
                    subprocess.run(f"patch -p 1 -i {patch_path}".split(), check=True)
            else:
                download_extract_to(url, _lib_path)
                if name == "libde265":  # noqa
                    os.chdir(_lib_path)
                    # for patch in (
                    #     "libde265/CVE-2022-1253.patch",
                    # ):
                    #     patch_path = os.path.join(_linux_dir, patch)
                    #     subprocess.run(f"patch -p 1 -i {patch_path}".split(), check=True)
                elif name == "libheif":
                    os.chdir(_lib_path)
                    # for patch in (
                    #     "libheif/001-void-unused-variable.patch",
                    # ):
                    #     patch_path = os.path.join(_linux_dir, patch)
                    #     subprocess.run(f"patch -p 1 -i {patch_path}".split(), check=True)
            os.chdir(_build_path)
        print(f"Preconfiguring {name}...", flush=True)
        if name == "aom":
            cmake_args = "-DENABLE_TESTS=0 -DENABLE_TOOLS=0 -DENABLE_EXAMPLES=0 -DENABLE_DOCS=0".split()
            cmake_args += "-DENABLE_TESTDATA=0 -DCONFIG_AV1_ENCODER=1 -DCMAKE_BUILD_TYPE=Release".split()
            cmake_args += "-DCMAKE_INSTALL_LIBDIR=lib -DBUILD_SHARED_LIBS=1".split()
            cmake_args += f"-DCMAKE_INSTALL_PREFIX={INSTALL_DIR_LIBS} ../aom".split()
        elif name == "x265":
            cmake_high_bits = "-DHIGH_BIT_DEPTH=ON -DEXPORT_C_API=OFF".split()
            cmake_high_bits += "-DENABLE_SHARED=OFF -DENABLE_CLI=OFF".split()
            os.mkdir("12bit")
            os.mkdir("10bit")
            os.chdir("10bit")
            subprocess.run("cmake ./../source -DENABLE_HDR10_PLUS=ON".split() + cmake_high_bits, check=True)
            run_print_if_error("make -j4".split())
            subprocess.run("mv libx265.a ../libx265_main10.a".split(), check=True)
            os.chdir("../12bit")
            subprocess.run(["cmake", "./../source", "-DMAIN12=ON", *cmake_high_bits], check=True)
            run_print_if_error("make -j4".split())
            subprocess.run("mv libx265.a ../libx265_main12.a".split(), check=True)
            os.chdir("..")
            cmake_args = f"-DCMAKE_INSTALL_PREFIX={INSTALL_DIR_LIBS} ./source".split()
            cmake_args += ["-G", "Unix Makefiles"]
            cmake_args += "-DLINKED_10BIT=ON -DLINKED_12BIT=ON -DEXTRA_LINK_FLAGS=-L.".split()
            cmake_args += "-DEXTRA_LIB='x265_main10.a;x265_main12.a'".split()
        else:
            cmake_args = f"-DCMAKE_INSTALL_PREFIX={INSTALL_DIR_LIBS} ..".split()
            cmake_args += ["-DCMAKE_BUILD_TYPE=Release"]
            if name == "libheif":
                cmake_args += (
                    "-DWITH_EXAMPLES=OFF -DWITH_RAV1E=OFF -DWITH_DAV1D=OFF -DWITH_SvtEnc=OFF"
                    " -DWITH_LIBSHARPYUV=OFF -DENABLE_PLUGIN_LOADING=OFF".split()
                )
                _hide_build_process = False
                if musl:
                    cmake_args += [f"-DCMAKE_INSTALL_LIBDIR={INSTALL_DIR_LIBS}/lib"]
        subprocess.run(["cmake", *cmake_args], check=True)
        print(f"{name} configured. building...", flush=True)
        if _hide_build_process:
            run_print_if_error("make -j4".split())
        else:
            subprocess.run("make -j4".split(), check=True)
        print(f"{name} build success.", flush=True)
    subprocess.run("make install".split(), check=True)
    if musl:
        subprocess.run(f"ldconfig {INSTALL_DIR_LIBS}/lib".split(), check=True)
    else:
        subprocess.run("ldconfig", check=True)


def build_libs(force_libheif_rebuild: bool) -> str:
    _is_musllinux = is_musllinux()
    is_libheif_installed = is_library_installed("heif") or is_library_installed("libheif") 
    if is_libheif_installed and not force_libheif_rebuild:
        print("libheif is already present.")
        return INSTALL_DIR_LIBS
    _original_dir = os.getcwd()
    try:
        if not tool_check_version("cmake", "3.13.4"):
            raise ValueError("Can not find `cmake` with version >=3.13.4")
        if not is_library_installed("x265"):
            if not PH_LIGHT_VERSION:
                if not check_install_nasm("2.15.05"):
                    raise ValueError("Can not find/install `nasm` with version >=2.15.05")
                build_lib_linux(LIBX265_URL, "x265", _is_musllinux)
        else:
            print("x265 already installed.")
        if not is_library_installed("aom"):
            if not PH_LIGHT_VERSION:
                if not check_install_nasm("2.15.05"):
                    raise ValueError("Can not find/install `nasm` with version >=2.15.05")
                build_lib_linux(LIBAOM_URL, "aom", _is_musllinux)
        else:
            print("aom already installed.")
        if not is_library_installed("libde265") and not is_library_installed("de265"):
            build_lib_linux(LIBDE265_URL, "libde265", _is_musllinux)
        else:
            print("libde265 already installed.")
        # build_lib_linux(LIBHEIF_URL, "libheif", _is_musllinux)
        build_libheif(
            base_dir=os.getenv("LIBHEIF_GIT_CLONE_DIR", Path.home() / "dev"),
            install_dir=Path(INSTALL_DIR_LIBS),
            git_ref="v1.17.1",
            build_examples=True,
        )
    finally:
        os.chdir(_original_dir)
    return INSTALL_DIR_LIBS


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-libheif-rebuild", action="store_true")
    args = parser.parse_args()
    build_libs(force_libheif_rebuild=args.force_libheif_rebuild)
