"""
build.py: Class for generating OpenCore Configurations tailored for Macs
"""

import copy
import pickle
import shutil
import logging
import zipfile
import plistlib

from pathlib import Path
from datetime import date

from .. import constants

from ..support import utilities

from .networking import (
    wired,
    wireless
)
from . import (
    bluetooth,
    firmware,
    graphics_audio,
    support,
    storage,
    smbios,
    security,
    misc
)


def rmtree_handler(func, path, exc_info) -> None:
    if exc_info[0] == FileNotFoundError:
        return
    raise  # pylint: disable=misplaced-bare-raise


class BuildOpenCore:
    """
    Core Build Library for generating and validating OpenCore EFI Configurations
    compatible with genuine Macs
    """

    def __init__(self, model: str, global_constants: constants.Constants) -> None:
        self.model: str = model
        self.config: dict = None
        self.constants: constants.Constants = global_constants

        self._build_opencore()


    def _build_efi(self) -> None:
        """
        Build EFI folder
        """

        utilities.cls()
        logging.info(f"正在构建配置 {'针对外部' if self.constants.custom_model else '针对模型'}: {self.model}")

        self._generate_base()
        self._set_revision()

        # Set Lilu and co.
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("Lilu.kext", self.constants.lilu_version, self.constants.lilu_path)
        self.config["Kernel"]["Quirks"]["DisableLinkeditJettison"] = True

        # macOS Sequoia support for Lilu plugins
        self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -lilubetaall"

        # Call support functions
        for function in [
            firmware.BuildFirmware,
            wired.BuildWiredNetworking,
            wireless.BuildWirelessNetworking,
            graphics_audio.BuildGraphicsAudio,
            bluetooth.BuildBluetooth,
            storage.BuildStorage,
            smbios.BuildSMBIOS,
            security.BuildSecurity,
            misc.BuildMiscellaneous
        ]:
            function(self.model, self.constants, self.config)

        # Work-around ocvalidate
        if self.constants.validate is False:
            logging.info("- 添加 bootmgfw.efi BlessOverride")
            self.config["Misc"]["BlessOverride"] += ["\\EFI\\Microsoft\\Boot\\bootmgfw.efi"]


    def _generate_base(self) -> None:
        """
        Generate OpenCore base folder and config
        """

        if not Path(self.constants.build_path).exists():
            logging.info("创建构建文件夹")
            Path(self.constants.build_path).mkdir()
        else:
            logging.info("构建文件夹已存在，跳过")

        if Path(self.constants.opencore_zip_copied).exists():
            logging.info("删除旧的 OpenCore 压缩包副本")
            Path(self.constants.opencore_zip_copied).unlink()
        if Path(self.constants.opencore_release_folder).exists():
            logging.info("删除旧的 OpenCore 文件夹副本")
            shutil.rmtree(self.constants.opencore_release_folder, onerror=rmtree_handler, ignore_errors=True)

        logging.info("")
        logging.info(f"- 添加 OpenCore v{self.constants.opencore_version} {'DEBUG' if self.constants.opencore_debug is True else 'RELEASE'}")
        shutil.copy(self.constants.opencore_zip_source, self.constants.build_path)
        zipfile.ZipFile(self.constants.opencore_zip_copied).extractall(self.constants.build_path)

        # Setup config.plist for editing
        logging.info("- 添加 config.plist 以供 OpenCore 使用")
        shutil.copy(self.constants.plist_template, self.constants.oc_folder)
        self.config = plistlib.load(Path(self.constants.plist_path).open("rb"))


    def _set_revision(self) -> None:
        """
        Set revision information in config.plist
        """

        self.config["#Revision"]["Build-Version"] = f"{self.constants.patcher_version} - {date.today()}"
        if not self.constants.custom_model:
            self.config["#Revision"]["Build-Type"] = "在目标机器上构建的 OpenCore"
            computer_copy = copy.copy(self.constants.computer)
            computer_copy.ioregistry = None
            self.config["#Revision"]["Hardware-Probe"] = pickle.dumps(computer_copy)
        else:
            self.config["#Revision"]["Build-Type"] = "为外部机器构建的 OpenCore"
        self.config["#Revision"]["OpenCore-Version"] = f"{self.constants.opencore_version} - {'DEBUG' if self.constants.opencore_debug is True else 'RELEASE'}"
        self.config["#Revision"]["Original-Model"] = self.model
        self.config["NVRAM"]["Add"]["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"]["OCLP-Version"] = f"{self.constants.patcher_version}"
        self.config["NVRAM"]["Add"]["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"]["OCLP-Model"] = self.model


    def _save_config(self) -> None:
        """
        Save config.plist to disk
        """

        plistlib.dump(self.config, Path(self.constants.plist_path).open("wb"), sort_keys=True)


    def _build_opencore(self) -> None:
        """
        Kick off the build process

        This is the main function:
        - Generates the OpenCore configuration
        - Cleans working directory
        - Signs files
        - Validates generated EFI
        """

        # Generate OpenCore Configuration
        self._build_efi()
        if self.constants.allow_oc_everywhere is False or self.constants.allow_native_spoofs is True or (self.constants.custom_serial_number != "" and self.constants.custom_board_serial_number != ""):
            smbios.BuildSMBIOS(self.model, self.constants, self.config).set_smbios()
        support.BuildSupport(self.model, self.constants, self.config).cleanup()
        self._save_config()

        # Post-build handling
        support.BuildSupport(self.model, self.constants, self.config).sign_files()
        support.BuildSupport(self.model, self.constants, self.config).validate_pathing()

        logging.info("")
        logging.info(f"您的 {self.model} 的 OpenCore EFI 已构建完成，位于:")
        logging.info(f"    {self.constants.opencore_release_folder}")
        logging.info("")