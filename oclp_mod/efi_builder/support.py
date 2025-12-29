"""
support.py: Utility class for build functions
"""

import shutil
import typing
import logging
import plistlib
import zipfile
import subprocess

from pathlib import Path

from .. import constants


class BuildSupport:
   """
   Support Library for build.py and related libraries
   """

   def __init__(self, model: str, global_constants: constants.Constants, config: dict) -> None:
       self.model: str = model
       self.config: dict = config
       self.constants: constants.Constants = global_constants
       # Access language_handler from constants
       self.language_handler = getattr(self.constants, 'language_handler', None)


   @staticmethod
   def get_item_by_kv(iterable: dict, key: str, value: typing.Any) -> dict:
       """
       Gets an item from a list of dicts by key and value

       Parameters:
           iterable (list): List of dicts
           key       (str): Key to search for
           value     (any): Value to search for

       """

       item = None
       for i in iterable:
           if i[key] == value:
               item = i
               break
       return item


   def get_kext_by_bundle_path(self, bundle_path: str) -> dict:
       """
       Gets a kext by bundle path

       Parameters:
           bundle_path (str): Relative bundle path of the kext in the EFI folder
       """

       kext: dict = self.get_item_by_kv(self.config["Kernel"]["Add"], "BundlePath", bundle_path)
       if not kext:
           logging.info(self.language_handler.get_translation("build_unable_find_kext").format(kext=bundle_path) if self.language_handler else f"- Unable to find kext {bundle_path}!")
           raise IndexError
       return kext


   def get_efi_binary_by_path(self, bundle_name: str, entry_type: str, efi_type: str) -> dict:
       """
       Gets an EFI binary by name

       Parameters:
           bundle_name (str): Name of the EFI binary
           entry_type  (str): Type of EFI binary (UEFI, Misc)
           efi_type    (str): Type of EFI binary (Drivers, Tools)
       """

       efi_binary: dict = self.get_item_by_kv(self.config[entry_type][efi_type], "Path", bundle_name)
       if not efi_binary:
           logging.info(self.language_handler.get_translation("build_unable_find_efi").format(type=efi_type, name=bundle_name) if self.language_handler else f"- Unable to find {efi_type}: {bundle_name}!")
           raise IndexError
       return efi_binary


   def enable_kext(self, kext_name: str, kext_version: str, kext_path: Path, check: bool = False) -> None:
       """
       Enables a kext in the config.plist

       Parameters:
           kext_name     (str): Name of the kext
           kext_version  (str): Version of the kext
           kext_path    (Path): Path to the kext
       """

       kext: dict = self.get_kext_by_bundle_path(kext_name)

       if callable(check) and not check():
           # Check failed
           return

       if kext["Enabled"] is True:
           return

       logging.info(self.language_handler.get_translation("build_adding_kext").format(name=kext_name, version=kext_version) if self.language_handler else f"- Adding {kext_name} {kext_version}")
       shutil.copy(kext_path, self.constants.kexts_path)
       kext["Enabled"] = True


   def sign_files(self) -> None:
       """
       Signs files for on OpenCorePkg's Vault system
       """

       if self.constants.vault is False:
           return

       logging.info(self.language_handler.get_translation("build_signing_efi") if self.language_handler else "- Signing EFI =========================================")
       popen = subprocess.Popen([str(self.constants.vault_path), f"{self.constants.oc_folder}/"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
       for stdout_line in iter(popen.stdout.readline, ""):
           logging.info(stdout_line.strip())
       logging.info(self.language_handler.get_translation("build_separator") if self.language_handler else "=========================================")

   def validate_pathing(self) -> None:
       """
       Validate whether all files are accounted for on-disk

       This ensures that OpenCore won't hit a critical error and fail to boot
       """

       logging.info(self.language_handler.get_translation("build_validating_config") if self.language_handler else "- Validating generated configuration")
       if not Path(self.constants.opencore_release_folder / Path("EFI/OC/config.plist")):
           logging.info(self.language_handler.get_translation("build_missing_config") if self.language_handler else "- OpenCore configuration file missing!!!")
           raise Exception("OpenCore 配置文件缺失")

       config_plist = plistlib.load(Path(self.constants.opencore_release_folder / Path("EFI/OC/config.plist")).open("rb"))

       for acpi in config_plist["ACPI"]["Add"]:
           if not Path(self.constants.opencore_release_folder / Path("EFI/OC/ACPI") / Path(acpi["Path"])).exists():
               logging.info(self.language_handler.get_translation("build_missing_acpi").format(table=acpi['Path']) if self.language_handler else f"- Missing ACPI table: {acpi['Path']}")
               raise Exception(f"缺少 ACPI 表: {acpi['Path']}")

       for kext in config_plist["Kernel"]["Add"]:
           kext_path = Path(self.constants.opencore_release_folder / Path("EFI/OC/Kexts") / Path(kext["BundlePath"]))
           kext_binary_path = Path(kext_path / Path(kext["ExecutablePath"]))
           kext_plist_path = Path(kext_path / Path(kext["PlistPath"]))
           if not kext_path.exists():
               logging.info(self.language_handler.get_translation("build_missing_kext").format(kext=kext_path) if self.language_handler else f"- Missing kext: {kext_path}")
               raise Exception(f"缺少 {kext_path}")
           if not kext_binary_path.exists():
               logging.info(self.language_handler.get_translation("build_missing_kext_exec").format(kext=kext['BundlePath'], exec=kext_binary_path) if self.language_handler else f"- Missing {kext['BundlePath']}'s executable: {kext_binary_path}")
               raise Exception(f"缺少 {kext_binary_path}")
           if not kext_plist_path.exists():
               logging.info(self.language_handler.get_translation("build_missing_kext_plist").format(kext=kext['BundlePath'], plist=kext_plist_path) if self.language_handler else f"- Missing {kext['BundlePath']}'s plist: {kext_plist_path}")
               raise Exception(f"缺少 {kext_plist_path}")

       for tool in config_plist["Misc"]["Tools"]:
           if not Path(self.constants.opencore_release_folder / Path("EFI/OC/Tools") / Path(tool["Path"])).exists():
               logging.info(self.language_handler.get_translation("build_missing_tool").format(tool=tool['Path']) if self.language_handler else f"- Missing tool: {tool['Path']}")
               raise Exception(f"缺少工具: {tool['Path']}")

       for driver in config_plist["UEFI"]["Drivers"]:
           if not Path(self.constants.opencore_release_folder / Path("EFI/OC/Drivers") / Path(driver["Path"])).exists():
               logging.info(self.language_handler.get_translation("build_missing_driver").format(driver=driver['Path']) if self.language_handler else f"- Missing driver: {driver['Path']}")
               raise Exception(f"缺少驱动: {driver['Path']}")

       # 验证本地文件
       # 报告它们没有关联的 config.plist 条目（即未被使用）
       for tool_files in Path(self.constants.opencore_release_folder / Path("EFI/OC/Tools")).glob("*"):
           if tool_files.name not in [x["Path"] for x in config_plist["Misc"]["Tools"]]:
               logging.info(self.language_handler.get_translation("build_missing_tool_config").format(tool=tool_files.name) if self.language_handler else f"- Missing tool in configuration: {tool_files.name}")
               raise Exception(f"配置中缺少工具: {tool_files.name}")

       for driver_file in Path(self.constants.opencore_release_folder / Path("EFI/OC/Drivers")).glob("*"):
           if driver_file.name not in [x["Path"] for x in config_plist["UEFI"]["Drivers"]]:
               logging.info(self.language_handler.get_translation("build_found_extra_driver").format(driver=driver_file.name) if self.language_handler else f"- Found extra driver: {driver_file.name}")
               raise Exception(f"找到额外的驱动: {driver_file.name}")

       self._validate_malformed_kexts(self.constants.opencore_release_folder / Path("EFI/OC/Kexts"))


   def _validate_malformed_kexts(self, directory: str | Path) -> None:
       """
       Validate Info.plist 和可执行文件路径的 kexts
       """
       for kext_folder in Path(directory).glob("*.kext"):
           if not Path(kext_folder / Path("Contents/Info.plist")).exists():
               continue

           kext_data = plistlib.load(Path(kext_folder / Path("Contents/Info.plist")).open("rb"))
           if "CFBundleExecutable" in kext_data:
               expected_executable = Path(kext_folder / Path("Contents/MacOS") / Path(kext_data["CFBundleExecutable"]))
               if not expected_executable.exists():
                   logging.info(self.language_handler.get_translation("build_missing_kext_exec").format(kext=kext_folder.name, exec=f"Contents/MacOS/{expected_executable.name}") if self.language_handler else f"- Missing {kext_folder.name}'s executable: Contents/MacOS/{expected_executable.name}")
                   raise Exception(f" - 缺少 {kext_folder.name} 的可执行文件: Contents/MacOS/{expected_executable.name}")

           if Path(kext_folder / Path("Contents/PlugIns")).exists():
               self._validate_malformed_kexts(kext_folder / Path("Contents/PlugIns"))


   def cleanup(self) -> None:
       """
       清理文件和条目
       """

       logging.info(self.language_handler.get_translation("build_cleaning_files") if self.language_handler else "- Cleaning up files")
       # 删除未使用的条目
       entries_to_clean = {
           "ACPI":   ["Add", "Delete", "Patch"],
           "Booter": ["Patch"],
           "Kernel": ["Add", "Block", "Force", "Patch"],
           "Misc":   ["Tools"],
           "UEFI":   ["Drivers"],
       }

       for entry in entries_to_clean:
           for sub_entry in entries_to_clean[entry]:
               for item in list(self.config[entry][sub_entry]):
                   if item["Enabled"] is False:
                       self.config[entry][sub_entry].remove(item)

       for kext in self.constants.kexts_path.rglob("*.zip"):
           with zipfile.ZipFile(kext) as zip_file:
               zip_file.extractall(self.constants.kexts_path)
           kext.unlink()

       for item in self.constants.oc_folder.rglob("*.zip"):
           with zipfile.ZipFile(item) as zip_file:
               zip_file.extractall(self.constants.oc_folder)
           item.unlink()

       if not self.constants.recovery_status:
           # 在恢复模式下崩溃，原因未知
           for i in self.constants.build_path.rglob("__MACOSX"):
               shutil.rmtree(i)

       # 删除 kexts 中未使用的插件
       # 有时这些插件未被使用，因为不同机器需要不同的变体
       known_unused_plugins = [
           "AirPortBrcm4331.kext",
           "AirPortAtheros40.kext",
           "AppleAirPortBrcm43224.kext",
           "AirPortBrcm4360_Injector.kext",
           "AirPortBrcmNIC_Injector.kext"
       ]
       for kext in Path(self.constants.opencore_release_folder / Path("EFI/OC/Kexts")).glob("*.kext"):
           for plugin in Path(kext / "Contents/PlugIns/").glob("*.kext"):
               should_remove = True
               for enabled_kexts in self.config["Kernel"]["Add"]:
                   if enabled_kexts["BundlePath"].endswith(plugin.name):
                       should_remove = False
                       break
               if should_remove:
                   if plugin.name not in known_unused_plugins:
                       raise Exception(f" - 发现未知插件: {plugin.name}")
                   shutil.rmtree(plugin)

       Path(self.constants.opencore_zip_copied).unlink()