
import logging
import subprocess
import plistlib

from pathlib import Path

from ... import constants

from ...datasets import os_data
from ...support import subprocess_wrapper, kdk_handler
from ...volume import generate_copy_arguments
from ...languages.language_handler import LanguageHandler


class KernelDebugKitMerge:

    def __init__(self, global_constants: constants.Constants, mount_location: str, skip_root_kmutil_requirement: bool) -> None:
        self.constants: constants.Constants = global_constants
        self.mount_location = mount_location
        self.skip_root_kmutil_requirement = skip_root_kmutil_requirement
        self.language_handler = LanguageHandler(global_constants)


    def _matching_kdk_already_merged(self, kdk_path: str) -> bool:
        """
        Check whether the KDK is already merged with the root volume
        """
        oclp_plist = Path("/System/Library/CoreServices/oclp-mod.plist")
        if not oclp_plist.exists():
            return False

        if not (Path(self.mount_location) / Path("System/Library/Extensions/System.kext/PlugIns/Libkern.kext/Libkern")).exists():
            return False

        try:
            oclp_plist_data = plistlib.load(open(oclp_plist, "rb"))
            if "Kernel Debug Kit Used" not in oclp_plist_data:
                return False
            if oclp_plist_data["Kernel Debug Kit Used"] == str(kdk_path):
                logging.info("- 确定已合并的匹配 KDK，跳过")
                return True
        except:
            pass

        return False


    def _backup_hid_cs(self) -> None:
        """
        Due to some IOHIDFamily oddities, we need to ensure their CodeSignature is retained
        """
        cs_path = Path(self.mount_location) / Path("System/Library/Extensions/IOHIDFamily.kext/Contents/PlugIns/IOHIDEventDriver.kext/Contents/_CodeSignature")
        if not cs_path.exists():
            return

        logging.info("- 备份 IOHIDEventDriver CodeSignature")
        subprocess_wrapper.run_as_root(generate_copy_arguments(cs_path, f"{self.constants.payload_path}/IOHIDEventDriver_CodeSignature.bak"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


    def _restore_hid_cs(self) -> None:
        """
        Restore IOHIDEventDriver CodeSignature
        """
        if not Path(f"{self.constants.payload_path}/IOHIDEventDriver_CodeSignature.bak").exists():
            return

        logging.info("- 恢复 IOHIDEventDriver CodeSignature")
        cs_path = Path(self.mount_location) / Path("System/Library/Extensions/IOHIDFamily.kext/Contents/PlugIns/IOHIDEventDriver.kext/Contents/_CodeSignature")
        if not cs_path.exists():
            logging.info("  - CodeSignature 文件夹不存在, 正在创建")
            subprocess_wrapper.run_as_root(["/bin/mkdir", "-p", cs_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        subprocess_wrapper.run_as_root(generate_copy_arguments(f"{self.constants.payload_path}/IOHIDEventDriver_CodeSignature.bak", cs_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        subprocess_wrapper.run_as_root(["/bin/rm", "-rf", f"{self.constants.payload_path}/IOHIDEventDriver_CodeSignature.bak"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


    def _merge_kdk(self, kdk_path: str) -> None:
        """
        Merge Kernel Debug Kit (KDK) with the root volume
        """
        logging.info(f"- 将 KDK 与根卷合并： {Path(kdk_path).name}")
        subprocess_wrapper.run_as_root(
            # Only merge '/System/Library/Extensions'
            # 'Kernels' and 'KernelSupport' is wasted space for root patching (we don't care above dev kernels)
            ["/usr/bin/rsync", "-r", "-i", "-a", f"{kdk_path}/System/Library/Extensions/", f"{self.mount_location}/System/Library/Extensions"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )

        if not (Path(self.mount_location) / Path("System/Library/Extensions/System.kext/PlugIns/Libkern.kext/Libkern")).exists():
            logging.info("- 无法将 KDK 与根卷合并")
            raise Exception("Failed to merge KDK with Root Volume")
        logging.info("- 成功将 KDK 与 Root Volume 合并")


    def merge(self, save_hid_cs: bool = False) -> str:
        """
        Merge the Kernel Debug Kit (KDK) with the root volume

        Returns KDK used
        """
        if self.skip_root_kmutil_requirement is True:
            return None
        if self.constants.detected_os < os_data.os_data.ventura:
            return None

        # If a KDK was pre-downloaded, install it
        if self.constants.kdk_download_path.exists():
            if kdk_handler.KernelDebugKitUtilities(self.constants).install_kdk_dmg(self.constants.kdk_download_path) is False:
                logging.info(self.language_handler.get_translation("kdk_install_kdk_failed", "Failed to install KDK"))
                raise Exception("Failed to install KDK")

        # Next, grab KDK information (ie. what's the latest KDK for this OS)
        kdk_obj = kdk_handler.KernelDebugKitObject(self.constants, self.constants.detected_os_build, self.constants.detected_os_version)
        if kdk_obj.success is False:
            logging.info(self.language_handler.get_translation("kdk_merge_unable_to_get_info", "Unable to get KDK info") + f": {kdk_obj.error_msg}")
            raise Exception(f"Unable to get KDK info: {kdk_obj.error_msg}")

        # If no KDK is installed, download and install it
        if kdk_obj.kdk_already_installed is False:
            kdk_download_obj = kdk_obj.retrieve_download()
            if not kdk_download_obj:
                logging.info(self.language_handler.get_translation("kdk_merge_unable_to_retrieve", "Unable to retrieve KDK") + f": {kdk_obj.error_msg}")
                raise Exception(f"Could not retrieve KDK: {kdk_obj.error_msg}")

            # Hold thread until download is complete
            kdk_download_obj.download(spawn_thread=False)

            if kdk_download_obj.download_complete is False:
                error_msg = kdk_download_obj.error_msg
                logging.info(self.language_handler.get_translation("kdk_merge_unable_to_download", "Unable to download KDK") + f": {error_msg}")
                raise Exception(f"Could not download KDK: {error_msg}")

            if kdk_obj.validate_kdk_checksum() is False:
                logging.info(self.language_handler.get_translation("kdk_merge_checksum_failed", "KDK checksum validation failed") + f": {kdk_obj.error_msg}")
                raise Exception(f"KDK checksum validation failed: {kdk_obj.error_msg}")

            kdk_handler.KernelDebugKitUtilities(self.constants).install_kdk_dmg(self.constants.kdk_download_path)
            # re-init kdk_obj to get the new kdk_installed_path
            kdk_obj = kdk_handler.KernelDebugKitObject(self.constants, self.constants.detected_os_build, self.constants.detected_os_version)
            if kdk_obj.success is False:
                logging.info(self.language_handler.get_translation("kdk_merge_unable_to_get_info", "Unable to get KDK info") + f": {kdk_obj.error_msg}")
                raise Exception(f"Unable to get KDK info: {kdk_obj.error_msg}")

            if kdk_obj.kdk_already_installed is False:
                # We shouldn't get here, but just in case
                logging.warning(f"KDK 未安装，但应该已安装： {kdk_obj.error_msg}")
                raise Exception(f"KDK was not installed, but should have been: {kdk_obj.error_msg}")


        kdk_path = Path(kdk_obj.kdk_installed_path) if kdk_obj.kdk_installed_path != "" else None
        if kdk_path is None:
            logging.info(f"- 找不到 Kernel Debug Kit")
            raise Exception("Unable to find Kernel Debug Kit")

        logging.info(f"- 在以下位置找到 KDK： {kdk_path}")

        if self._matching_kdk_already_merged(kdk_path):
            return kdk_path

        if save_hid_cs is True:
            self._backup_hid_cs()

        self._merge_kdk(kdk_path)

        if save_hid_cs is True:
            self._restore_hid_cs()

        return kdk_path