from pathlib import Path
import tempfile
import subprocess
import os
import sys
import multiprocessing
import shutil

SO_FILE = {
    "linux": "libmdbx.so",
    "linux2": "libmdbx.so",
    "darwin": "libmdbx.dylib",
    "win32": "mdbx.dll",
}.get(sys.platform, "libmdbx.so")

def ensure_dependency():
    subprocess.check_call(["cmake", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(["ninja", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def build(setup_kws: dict):
    ensure_dependency()
    debug = "DEBUG" in os.environ
    pwd = Path(__file__).parent.resolve()
    out_lib = pwd / "mdbx" / "lib"
    libmdbx_source = pwd / "libmdbx"

    tmpdir = None
    if debug:
        tmpdir = pwd / "build_libmdbx"
        if tmpdir.exists():
            shutil.rmtree(tmpdir)
        os.makedirs(tmpdir, exist_ok=True)
        tmpdir_path = tmpdir
    else:
        tmpdir = tempfile.TemporaryDirectory()
        tmpdir_path = Path(tmpdir.name)
    
    if debug:
        build_type = ["-DCMAKE_BUILD_TYPE=Debug"]
    else:
        build_type = ["-DCMAKE_BUILD_TYPE=Release"]
        
    subprocess.check_call(
        ["cmake", "-G", "Ninja", "-S", str(libmdbx_source.absolute()), "-B", str(tmpdir_path.absolute())] + build_type,
        cwd=tmpdir_path
    )
    threads = multiprocessing.cpu_count()
    if "THREADS" in os.environ:
        threads = int(os.environ["THREADS"])
    
    subprocess.check_call(
        ["cmake", "--build", str(tmpdir_path.absolute()), "-j", str(threads)],
        cwd=tmpdir_path
    )

    if out_lib.exists():
        shutil.rmtree(out_lib)
    os.makedirs(out_lib, exist_ok=True)
    
    if sys.platform == "win32":
        if debug:
            dyn_path = tmpdir_path / "Debug" / SO_FILE
        else:
            dyn_path = tmpdir_path / "Release" / SO_FILE
    else:
        dyn_path = tmpdir_path / SO_FILE
    
    shutil.copy(dyn_path, out_lib)
    shutil.copy(libmdbx_source / "LICENSE", out_lib)
    
if __name__ == "__main__":
    build({})