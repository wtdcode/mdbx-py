from pathlib import Path
import tempfile
import subprocess
import os
import sys

def build_library():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        pwd = Path(os.getcwd())
        libmdbx_source = pwd / "libmdbx"

        debug = os.environ.get("DEBUG", False)
        
        if debug:
            build_type = ["-DCMAKE_BUILD_TYPE=Debug"]
        else:
            build_type = ["-DCMAKE_BUILD_TYPE=Release"]
        subprocess.check_call(
            ["cmake", "-G", "Ninja", "-S", str(libmdbx_source.absolute()), "-B", str(tmpdir_path.absolute())] + build_type,
            cwd=tmpdir_path
        )
        
        subprocess.check_call(
            ["cmake", "-S", str(libmdbx_source.absolute()), "-B", str(tmpdir_path.absolute()), "--build", "-j"],
            cwd=tmpdir_path
        )


if __name__ == "__main__":
    build_library()