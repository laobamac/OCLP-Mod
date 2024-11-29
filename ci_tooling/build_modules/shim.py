"""
shim.py: Generate Update Shim
"""

from pathlib import Path

from oclp_mod.volume  import generate_copy_arguments
from oclp_mod.support import subprocess_wrapper


class GenerateShim:

    def __init__(self) -> None:
        self._shim_path = "./ci_tooling/update_shim/OCLP-Mod.app"
        self._shim_pkg  = f"{self._shim_path}/Contents/Resources/OCLP-Mod.pkg"

        self._build_pkg   = "./dist/OCLP-Mod.pkg"
        self._output_shim = "./dist/OCLP-Mod (Shim).app"


    def generate(self) -> None:
        """
        Generate Update Shim
        """
        print("Generating Update Shim")
        if Path(self._shim_pkg).exists():
            Path(self._shim_pkg).unlink()

        subprocess_wrapper.run_and_verify(generate_copy_arguments(self._build_pkg, self._shim_pkg))

        if Path(self._output_shim).exists():
            Path(self._output_shim).unlink()

        subprocess_wrapper.run_and_verify(generate_copy_arguments(self._shim_path, self._output_shim))
