"""
package.py: Generate packages (Installer, Uninstaller, AutoPkg-Assets)
"""

import tempfile
import macos_pkg_builder

from oclp_mod import constants

from .package_scripts import GenerateScripts


class GeneratePackage:
    """
    Generate OCLP-Mod.pkg
    """

    def __init__(self) -> None:
        """
        Initialize
        """
        self._files = {
            "./dist/OCLP-Mod.app": "/Library/Application Support/laobamac/OCLP-Mod.app",
            "./ci_tooling/privileged_helper_tool/com.laobamac.oclp-mod.privileged-helper": "/Library/PrivilegedHelperTools/com.laobamac.oclp-mod.privileged-helper",
        }
        self._autopkg_files = {
            "./payloads/Launch Services/com.laobamac.oclp-mod.auto-patch.plist": "/Library/LaunchAgents/com.laobamac.oclp-mod.auto-patch.plist",
        }
        self._autopkg_files.update(self._files)


    def _generate_installer_welcome(self) -> str:
        """
        Generate Welcome message for installer PKG
        """
        _welcome = ""

        _welcome += "# Overview\n"
        _welcome += "## OCLP-Mod [Github](https://github.com/laobamac/OCLP-Mod)\n\n"
        _welcome += "### Obey the MIT License & laobamac's License\n\n"
        _welcome += f"This package will install the OCLP-Mod application (v{constants.Constants().patcher_version}) on your system."

        _welcome += "\n\nAdditionally, a shortcut for OCLP-Mod will be added in the '/Applications' folder."
        _welcome += "\n\nThis package will not 'Build and Install OpenCore' or install any 'Root Patches' on your machine. If required, you can run OCLP-Mod to install any patches you may need."
        _welcome += f"\n\nFor more information on OCLP-Mod usage, see our [documentation]({constants.Constants().guide_link}) and [GitHub repository]({constants.Constants().repo_link})."
        _welcome += "\n\n"

        _welcome += "## Files Installed"
        _welcome += "\n\nInstallation of this package will add the following files to your system:"
        for key, value in self._files.items():
            _welcome += f"\n\n- `{value}`"

        return _welcome


    def _generate_uninstaller_welcome(self) -> str:
        """
        Generate Welcome message for uninstaller PKG
        """
        _welcome = ""

        _welcome += "# Application Uninstaller\n"
        _welcome += "This package will uninstall the OCLP-Mod application and its Privileged Helper Tool from your system.\n\n"
        _welcome += "## OCLP-Mod [Github](https://github.com/laobamac/OCLP-Mod)\n\n"
        _welcome += "### Obey the MIT License & laobamac's License\n\n"
        _welcome += "\n\n"
        _welcome += "This will not remove any root patches or OpenCore configurations that you may have installed using OCLP-Mod."
        _welcome += "\n\n"
        _welcome += f"For more information on OCLP-Mod, see our [documentation]({constants.Constants().guide_link}) and [GitHub repository]({constants.Constants().repo_link})."

        return _welcome


    def _generate_autopkg_welcome(self) -> str:
        """
        Generate Welcome message for AutoPkg-Assets PKG
        """
        _welcome = ""

        _welcome += "# DO NOT RUN AUTOPKG-ASSETS MANUALLY!\n\n"
        _welcome += "## THIS CAN BREAK YOUR SYSTEM'S INSTALL!\n\n"
        _welcome += "This package should only ever be invoked by the Patcher itself, never downloaded or run by the user. Download the OCLP-Mod.pkg on the Github Repository.\n\n"
        _welcome += f"[OCLP-Mod GitHub Release]({constants.Constants().repo_link})"

        return _welcome


    def generate(self) -> None:
        """
        Generate OCLP-Mod.pkg
        """
        print("Generating OCLP-Mod-Uninstaller.pkg")
        _tmp_uninstall = tempfile.NamedTemporaryFile(delete=False)
        with open(_tmp_uninstall.name, "w") as f:
            f.write(GenerateScripts().uninstall())

        assert macos_pkg_builder.Packages(
            pkg_output="./dist/OCLP-Mod-Uninstaller.pkg",
            pkg_bundle_id="com.laobamac.oclp-mod-uninstaller",
            pkg_version=constants.Constants().patcher_version,
            pkg_background="./ci_tooling/pkg_assets/PkgBackground-Uninstaller.png",
            pkg_preinstall_script=_tmp_uninstall.name,
            pkg_as_distribution=True,
            pkg_title="OCLP-Mod Uninstaller",
            pkg_welcome=self._generate_uninstaller_welcome(),
        ).build() is True

        print("Generating OCLP-Mod.pkg")

        _tmp_pkg_preinstall = tempfile.NamedTemporaryFile(delete=False)
        _tmp_pkg_postinstall = tempfile.NamedTemporaryFile(delete=False)
        with open(_tmp_pkg_preinstall.name, "w") as f:
            f.write(GenerateScripts().preinstall_pkg())
        with open(_tmp_pkg_postinstall.name, "w") as f:
            f.write(GenerateScripts().postinstall_pkg())

        assert macos_pkg_builder.Packages(
            pkg_output="./dist/OCLP-Mod.pkg",
            pkg_bundle_id="com.laobamac.oclp-mod",
            pkg_version=constants.Constants().patcher_version,
            pkg_allow_relocation=False,
            pkg_as_distribution=True,
            pkg_background="./ci_tooling/pkg_assets/PkgBackground-Installer.png",
            pkg_preinstall_script=_tmp_pkg_preinstall.name,
            pkg_postinstall_script=_tmp_pkg_postinstall.name,
            pkg_file_structure=self._files,
            pkg_title="OCLP-Mod",
            pkg_welcome=self._generate_installer_welcome(),
        ).build() is True

        print("Generating AutoPkg-Assets.pkg")

        _tmp_auto_pkg_preinstall = tempfile.NamedTemporaryFile(delete=False)
        _tmp_auto_pkg_postinstall = tempfile.NamedTemporaryFile(delete=False)
        with open(_tmp_auto_pkg_preinstall.name, "w") as f:
            f.write(GenerateScripts().preinstall_autopkg())
        with open(_tmp_auto_pkg_postinstall.name, "w") as f:
            f.write(GenerateScripts().postinstall_autopkg())

        assert macos_pkg_builder.Packages(
            pkg_output="./dist/AutoPkg-Assets.pkg",
            pkg_bundle_id="com.laobamac.pkg.AutoPkg-Assets",
            pkg_version=constants.Constants().patcher_version,
            pkg_allow_relocation=False,
            pkg_as_distribution=True,
            pkg_background="./ci_tooling/pkg_assets/PkgBackground-AutoPkg.png",
            pkg_preinstall_script=_tmp_auto_pkg_preinstall.name,
            pkg_postinstall_script=_tmp_auto_pkg_postinstall.name,
            pkg_file_structure=self._autopkg_files,
            pkg_title="AutoPkg Assets",
            pkg_welcome=self._generate_autopkg_welcome(),
        ).build() is True
