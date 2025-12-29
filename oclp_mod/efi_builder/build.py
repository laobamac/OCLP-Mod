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
from ..languages.language_handler import LanguageHandler

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
        # Add language_handler to constants for access by all builder classes
        if not hasattr(self.constants, 'language_handler'):
            self.constants.language_handler = LanguageHandler(self.constants)
        self.language_handler = self.constants.language_handler

        self._build_opencore()


    def _build_efi(self) -> None:
        """
        Build EFI folder
        """

        utilities.cls()
        model_type = self.language_handler.get_translation("build_for_external") if self.constants.custom_model else self.language_handler.get_translation("build_for_model")
        logging.info(f"{self.language_handler.get_translation('build_building_configuration')} {model_type}: {self.model}")

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
            logging.info(self.language_handler.get_translation("build_adding_blessoverride"))
            self.config["Misc"]["BlessOverride"] += ["\\EFI\\Microsoft\\Boot\\bootmgfw.efi"]


    def _generate_base(self) -> None:
        """
        Generate OpenCore base folder and config
        """

        if not Path(self.constants.build_path).exists():
            logging.info(self.language_handler.get_translation("build_creating_folder"))
            Path(self.constants.build_path).mkdir()
        else:
            logging.info(self.language_handler.get_translation("build_folder_exists"))

        if Path(self.constants.opencore_zip_copied).exists():
            logging.info(self.language_handler.get_translation("build_removing_old_zip"))
            Path(self.constants.opencore_zip_copied).unlink()
        if Path(self.constants.opencore_release_folder).exists():
            logging.info(self.language_handler.get_translation("build_removing_old_folder"))
            shutil.rmtree(self.constants.opencore_release_folder, onerror=rmtree_handler, ignore_errors=True)

        logging.info("")
        oc_type = 'DEBUG' if self.constants.opencore_debug is True else 'RELEASE'
        logging.info(self.language_handler.get_translation("build_adding_opencore").format(version=self.constants.opencore_version, type=oc_type))
        shutil.copy(self.constants.opencore_zip_source, self.constants.build_path)
        zipfile.ZipFile(self.constants.opencore_zip_copied).extractall(self.constants.build_path)

        # Setup config.plist for editing
        logging.info(self.language_handler.get_translation("build_adding_configplist"))
        shutil.copy(self.constants.plist_template, self.constants.oc_folder)
        self.config = plistlib.load(Path(self.constants.plist_path).open("rb"))


    def _set_revision(self) -> None:
        """
        Set revision information in config.plist
        """

        self.config["#Revision"]["Build-Version"] = f"{self.constants.patcher_version} - {date.today()}"
        if not self.constants.custom_model:
            self.config["#Revision"]["Build-Type"] = self.language_handler.get_translation("build_type_target")
            computer_copy = copy.copy(self.constants.computer)
            computer_copy.ioregistry = None
            self.config["#Revision"]["Hardware-Probe"] = pickle.dumps(computer_copy)
        else:
            self.config["#Revision"]["Build-Type"] = self.language_handler.get_translation("build_type_external")
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
        logging.info(self.language_handler.get_translation("build_efi_complete").format(model=self.model))
        logging.info(f"    {self.constants.opencore_release_folder}")
        logging.info("")