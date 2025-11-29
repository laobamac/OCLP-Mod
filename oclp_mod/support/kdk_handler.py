"""
kdk_handler.py: Module for parsing and determining best Kernel Debug Kit for host OS
"""

import logging
import plistlib
import requests
import tempfile
import subprocess
import packaging.version

from typing import cast
from pathlib import Path

from .. import constants

from ..datasets import os_data
from ..volume   import generate_copy_arguments

from . import (
    network_handler,
    subprocess_wrapper
)

KDK_INSTALL_PATH: str  = "/Library/Developer/KDKs"
KDK_INFO_PLIST:   str  = "KDKInfo.plist"
KDK_API_LINK_PROXY:     str  = "https://next.oclpapi.simplehac.cn/KdkSupportPkg/manifest.json"
KDK_API_LINK_ORIGIN:     str  = "https://dortania.github.io/KdkSupportPkg/manifest.json"

KDK_ASSET_LIST:   list = None

class KernelDebugKitObject:
    """
    Library for querying and downloading Kernel Debug Kits (KDK) for macOS

    Usage:
        >>> kdk_object = KernelDebugKitObject(constants, host_build, host_version)

        >>> if kdk_object.success:

        >>>     # Query whether a KDK is already installed
        >>>     if kdk_object.kdk_already_installed:
        >>>         # Use the installed KDK
        >>>         kdk_path = kdk_object.kdk_installed_path

        >>>     else:
        >>>         # Get DownloadObject for the KDK
        >>>         # See network_handler.py's DownloadObject documentation for usage
        >>>         kdk_download_object = kdk_object.retrieve_download()

        >>>         # Once downloaded, recommend verifying KDK's checksum
        >>>         valid = kdk_object.validate_kdk_checksum()

    """

    def __init__(self, global_constants: constants.Constants,
                 host_build: str, host_version: str,
                 ignore_installed: bool = False, passive: bool = False,
                 check_backups_only: bool = False
        ) -> None:

        self.constants: constants.Constants = global_constants

        self.host_build:   str = host_build    # ex. 20A5384c
        self.host_version: str = host_version  # ex. 11.0.1

        self.passive: bool = passive  # Don't perform actions requiring elevated privileges

        self.ignore_installed:      bool = ignore_installed   # If True, will ignore any installed KDKs and download the latest
        self.check_backups_only:    bool = check_backups_only # If True, will only check for KDK backups, not KDKs already installed
        self.kdk_already_installed: bool = False

        self.kdk_installed_path: str = ""

        self.kdk_url:         str = ""
        self.kdk_url_build:   str = ""
        self.kdk_url_version: str = ""

        self.kdk_url_expected_size: int = 0

        self.kdk_url_is_exactly_match: bool = False

        self.kdk_closest_match_url:         str = ""
        self.kdk_closest_match_url_build:   str = ""
        self.kdk_closest_match_url_version: str = ""

        self.kdk_closest_match_url_expected_size: int = 0

        self.success: bool = False

        self.error_msg: str = ""

        self._get_latest_kdk()


    def _get_remote_kdks(self) -> list:
        """
        Fetches a list of available KDKs from the KdkSupportPkg API
        Additionally caches the list for future use, avoiding extra API calls

        Returns:
            list: A list of KDKs, sorted by version and date if available. Returns None if the API is unreachable
        """

        global KDK_ASSET_LIST

        logging.info("从 KdkSupportPkg API 拉取 KDK 列表")
        if KDK_ASSET_LIST:
            return KDK_ASSET_LIST
        
        if self.constants.use_github_proxy == True:
            KDK_API_LINK:  str = KDK_API_LINK_PROXY
        else:
            KDK_API_LINK:  str = KDK_API_LINK_ORIGIN

        try:
            results = network_handler.NetworkUtilities().get(
                KDK_API_LINK,
                headers={
                    "User-Agent": f"OCLP/{self.constants.patcher_version}"
                },
                timeout=5
            )
        except (requests.exceptions.Timeout, requests.exceptions.TooManyRedirects, requests.exceptions.ConnectionError):
            logging.info("无法联系 KDK API")
            return None

        if results.status_code != 200:
            logging.info("无法获取 KDK 列表")
            return None

        KDK_ASSET_LIST = results.json()

        return KDK_ASSET_LIST


    def _get_latest_kdk(self, host_build: str = None, host_version: str = None) -> None:
        """
        获取当前 macOS 版本的最新 KDK

        Parameters:
            host_build (str, optional):   当前 macOS 版本的构建版本。
                                          如果为空，则使用类中的 host_build。默认为 None。
            host_version (str, optional): 当前 macOS 版本。
                                          如果为空，则使用类中的 host_version。默认为 None。
        """

        if host_build is None and host_version is None:
            host_build   = self.host_build
            host_version = self.host_version

        parsed_version = cast(packaging.version.Version, packaging.version.parse(host_version))

        if os_data.os_conversion.os_to_kernel(str(parsed_version.major)) < os_data.os_data.ventura:
            self.error_msg = "macOS Monterey 或更早版本不需要 KDK"
            logging.warning(f"{self.error_msg}")
            return

        self.kdk_installed_path = self._local_kdk_installed()
        if self.kdk_installed_path:
            logging.info(f"KDK 已安装 ({Path(self.kdk_installed_path).name})，跳过")
            self.kdk_already_installed = True
            self.success = True
            return

        remote_kdk_version = self._get_remote_kdks()

        if remote_kdk_version is None:
            logging.warning("无法获取 KDK 列表，回退到本地 KDK 匹配")

            # 首先检查是否安装了与当前 macOS 版本匹配的 KDK
            # 例如 13.0.1 对应 13.0
            loose_version = f"{parsed_version.major}.{parsed_version.minor}"
            logging.info(f"检查松散匹配的 KDK {loose_version}")
            self.kdk_installed_path = self._local_kdk_installed(match=loose_version, check_version=True)
            if self.kdk_installed_path:
                logging.info(f"找到匹配的 KDK: {Path(self.kdk_installed_path).name}")
                self.kdk_already_installed = True
                self.success = True
                return

            older_version = f"{parsed_version.major}.{parsed_version.minor - 1 if parsed_version.minor > 0 else 0}"
            logging.info(f"检查匹配的 KDK {older_version}")
            self.kdk_installed_path = self._local_kdk_installed(match=older_version, check_version=True)
            if self.kdk_installed_path:
                logging.info(f"找到匹配的 KDK: {Path(self.kdk_installed_path).name}")
                self.kdk_already_installed = True
                self.success = True
                return

            logging.warning(f"找不到匹配 {host_version} 或 {older_version} 的 KDK，请手动安装一个")

            self.error_msg = f"无法联系 KdkSupportPkg API，并且没有安装匹配 {host_version} ({host_build}) 或 {older_version} 的 KDK。\n请确保您有网络连接或手动安装一个 KDK."

            return

        # 首先检查精确匹配
        for kdk in remote_kdk_version:
            if (kdk["build"] != host_build):
                continue
            self.kdk_url = kdk["url"]
            self.kdk_url_build = kdk["build"]
            self.kdk_url_version = kdk["version"]
            self.kdk_url_expected_size = kdk["fileSize"]
            self.kdk_url_is_exactly_match = True
            break

        # 如果没有精确匹配，检查最接近的匹配
        if self.kdk_url == "":
            # 收集所有可能的候选版本
            candidate_kdks = []
            for kdk in remote_kdk_version:
                kdk_version = cast(packaging.version.Version, packaging.version.parse(kdk["version"]))
                if kdk_version > parsed_version:
                    continue
                if kdk_version.major != parsed_version.major:
                    continue
                if kdk_version.minor not in range(parsed_version.minor - 1, parsed_version.minor + 1):
                    continue
                
                candidate_kdks.append(kdk)

            # 按构建号排序，选择最接近的上一个版本
            if candidate_kdks:
                # 按构建号排序（降序，最新的在前）
                candidate_kdks.sort(key=lambda x: x["build"], reverse=True)
                
                # 选择构建号小于等于当前构建的最新版本
                closest_kdk = None
                for kdk in candidate_kdks:
                    if kdk["build"] <= host_build:
                        closest_kdk = kdk
                        break
                
                # 如果没有找到小于等于的版本，选择最小的版本（最老的）
                if closest_kdk is None:
                    closest_kdk = candidate_kdks[-1]  # 排序后最后一个是最小的
                
                self.kdk_closest_match_url = closest_kdk["url"]
                self.kdk_closest_match_url_build = closest_kdk["build"]
                self.kdk_closest_match_url_version = closest_kdk["version"]
                self.kdk_closest_match_url_expected_size = closest_kdk["fileSize"]
                self.kdk_url_is_exactly_match = False

        if self.kdk_url == "":
            if self.kdk_closest_match_url == "":
                logging.warning(f"未找到适用于 {host_build} ({host_version}) 的 KDK")
                self.error_msg = f"未找到适用于 {host_build} ({host_version}) 的 KDK"
                return
            logging.info(f"未找到 {host_build} 的直接匹配，回退到最接近的匹配")
            logging.info(f"最接近的匹配: {self.kdk_closest_match_url_build} ({self.kdk_closest_match_url_version})")

            self.kdk_url = self.kdk_closest_match_url
            self.kdk_url_build = self.kdk_closest_match_url_build
            self.kdk_url_version = self.kdk_closest_match_url_version
            self.kdk_url_expected_size = self.kdk_closest_match_url_expected_size
        else:
            logging.info(f"找到 {host_build} ({host_version}) 的直接匹配")


        # 检查此 KDK 是否已安装
        self.kdk_installed_path = self._local_kdk_installed(match=self.kdk_url_build)
        if self.kdk_installed_path:
            logging.info(f"KDK 已安装 ({Path(self.kdk_installed_path).name})，跳过")
            self.kdk_already_installed = True
            self.success = True
            return

        logging.info("推荐的 KDK 如下:")
        logging.info(f"- KDK 构建版本: {self.kdk_url_build}")
        logging.info(f"- KDK 版本: {self.kdk_url_version}")
        logging.info(f"- KDK URL: {self.kdk_url}")

        self.success = True


    def retrieve_download(self, override_path: str = "") -> network_handler.DownloadObject:
        """
        返回 KDK 的 DownloadObject

        Parameters:
            override_path (str): 覆盖默认下载路径

        Returns:
            DownloadObject: KDK 的 DownloadObject，如果没有下载要求则返回 None
        """

        self.success = False
        self.error_msg = ""

        if self.kdk_already_installed:
            logging.info("无需下载，KDK 已安装")
            self.success = True
            return None

        if self.kdk_url == "":
            self.error_msg = "无法检索 KDK 目录，没有 KDK 可下载"
            logging.error(self.error_msg)
            return None

        logging.info(f"返回 KDK 的 DownloadUrl: {self.kdk_url}")
        logging.info(f"返回 KDK 的 DownloadObject: {Path(self.kdk_url).name}")
        logging.info(f"返回的KDK预期大小: {network_handler.DownloadObject.convert_size(self, str(self.kdk_url_expected_size))}")
        self.success = True

        kdk_download_path = self.constants.kdk_download_path if override_path == "" else Path(override_path)
        kdk_plist_path = Path(f"{kdk_download_path.parent}/{KDK_INFO_PLIST}") if override_path == "" else Path(f"{Path(override_path).parent}/{KDK_INFO_PLIST}")

        self._generate_kdk_info_plist(kdk_plist_path)
        return network_handler.DownloadObject(self.kdk_url, kdk_download_path, network_handler.DownloadObject.convert_size(self, str(self.kdk_url_expected_size)))


    def _generate_kdk_info_plist(self, plist_path: str) -> None:
        """
        生成 KDK Info.plist

        """

        plist_path = Path(plist_path)
        if plist_path.exists():
            plist_path.unlink()

        kdk_dict = {
            "build": self.kdk_url_build,
            "version": self.kdk_url_version,
        }

        try:
            plist_path.touch()
            plistlib.dump(kdk_dict, plist_path.open("wb"), sort_keys=False)
        except Exception as e:
            logging.error(f"生成 KDK Info.plist 失败: {e}")

    def _local_kdk_valid(self, kdk_path: Path) -> bool:
        """
        Validates provided KDK, ensure no corruption

        The reason for this is due to macOS deleting files from the KDK during OS updates,
        similar to how Install macOS.app is deleted during OS updates

        Uses Apple's pkg receipt system to verify the original contents of the KDK

        Parameters:
            kdk_path (Path): Path to KDK

        Returns:
            bool: True if valid, False if invalid
        """

        if not Path(f"{kdk_path}/System/Library/CoreServices/SystemVersion.plist").exists():
            logging.info(f"发现损坏的KDK ({kdk_path.name})，由于缺少SystemVersion.plist而删除")
            self._remove_kdk(kdk_path)
            return False

        # Get build from KDK
        kdk_plist_data = plistlib.load(Path(f"{kdk_path}/System/Library/CoreServices/SystemVersion.plist").open("rb"))
        if "ProductBuildVersion" not in kdk_plist_data:
            logging.info(f"发现损坏的KDK ({kdk_path.name})，由于缺少ProductBuildVersion而删除")
            self._remove_kdk(kdk_path)
            return False

        kdk_build = kdk_plist_data["ProductBuildVersion"]

        # Check pkg receipts for this build, will give a canonical list if all files that should be present
        result = subprocess.run(["/usr/sbin/pkgutil", "--files", f"com.apple.pkg.KDK.{kdk_build}"], capture_output=True)
        if result.returncode != 0:
            # If pkg receipt is missing, we'll fallback to legacy validation
            logging.info(f"{kdk_path.name}缺少pkg收据，回退到旧版验证")
            return self._local_kdk_valid_legacy(kdk_path)

        # Go through each line of the pkg receipt and ensure it exists
        for line in result.stdout.decode("utf-8").splitlines():
            if not line.startswith("System/Library/Extensions"):
                continue
            if not Path(f"{kdk_path}/{line}").exists():
                logging.info(f"发现损坏的KDK ({kdk_path.name})，由于缺少文件: {line} 而删除")
                self._remove_kdk(kdk_path)
                return False

        return True


    def _local_kdk_valid_legacy(self, kdk_path: Path) -> bool:
        """
        Legacy variant of validating provided KDK
        Uses best guess of files that should be present
        This should ideally never be invoked, but used as a fallback

        Parameters:
            kdk_path (Path): Path to KDK

        Returns:
            bool: True if valid, False if invalid
        """

        KEXT_CATALOG = [
            "System.kext/PlugIns/Libkern.kext/Libkern",
            "apfs.kext/Contents/MacOS/apfs",
            "IOUSBHostFamily.kext/Contents/MacOS/IOUSBHostFamily",
            "AMDRadeonX6000.kext/Contents/MacOS/AMDRadeonX6000",
        ]

        for kext in KEXT_CATALOG:
            if not Path(f"{kdk_path}/System/Library/Extensions/{kext}").exists():
                logging.info(f"发现损坏的KDK，由于缺少: {kdk_path}/System/Library/Extensions/{kext} 而删除")
                self._remove_kdk(kdk_path)
                return False

        return True


    def _local_kdk_installed(self, match: str = None, check_version: bool = False) -> str:
        """
        Checks if KDK matching build is installed
        If so, validates it has not been corrupted

        Parameters:
            match (str): string to match against (ex. build or version)
            check_version (bool): If True, match against version, otherwise match against build

        Returns:
            str: Path to KDK if valid, None if not
        """

        if self.ignore_installed is True:
            return None

        if match is None:
            if check_version:
                match = self.host_version
            else:
                match = self.host_build

        if not Path(KDK_INSTALL_PATH).exists():
            return None

        # Installed KDKs only
        if self.check_backups_only is False:
            for kdk_folder in Path(KDK_INSTALL_PATH).iterdir():
                if not kdk_folder.is_dir():
                    continue
                if check_version:
                    if match not in kdk_folder.name:
                        continue
                else:
                    if not kdk_folder.name.endswith(f"{match}.kdk"):
                        continue

                if self._local_kdk_valid(kdk_folder):
                    return kdk_folder

        # If we can't find a KDK, next check if there's a backup present
        # Check for KDK packages in the same directory as the KDK
        for kdk_pkg in Path(KDK_INSTALL_PATH).iterdir():
            if kdk_pkg.is_dir():
                continue
            if not kdk_pkg.name.endswith(".pkg"):
                continue
            if check_version:
                if match not in kdk_pkg.name:
                    continue
            else:
                if not kdk_pkg.name.endswith(f"{match}.pkg"):
                    continue

            logging.info(f"找到KDK备份: {kdk_pkg.name}")
            if self.passive is False:
                logging.info("尝试恢复KDK")
                if KernelDebugKitUtilities().install_kdk_pkg(kdk_pkg):
                    logging.info("成功恢复KDK")
                    return self._local_kdk_installed(match=match, check_version=check_version)
            else:
                # When in passive mode, we're just checking if a KDK could be restored
                logging.info("KDK恢复被跳过，处于被动模式")
                return kdk_pkg

        return None


    def _remove_kdk(self, kdk_path: str) -> None:
        """
        Removes provided KDK

        Parameters:
            kdk_path (str): Path to KDK
        """

        if self.passive is True:
            return

        if not Path(kdk_path).exists():
            logging.warning(f"KDK不存在: {kdk_path}")
            return

        rm_args = ["/bin/rm", "-rf" if Path(kdk_path).is_dir() else "-f", kdk_path]

        result = subprocess_wrapper.run_as_root(rm_args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            logging.warning(f"无法删除KDK: {kdk_path}")
            subprocess_wrapper.log(result)
            return

        logging.info(f"成功删除KDK: {kdk_path}")


    def _remove_unused_kdks(self, exclude_builds: list = None) -> None:
        """
        Removes KDKs that are not in use

        Parameters:
            exclude_builds (list, optional): Builds to exclude from removal.
                                             If None, defaults to host and closest match builds.
        """

        if self.passive is True:
            return

        if exclude_builds is None:
            exclude_builds = [
                self.kdk_url_build,
                self.kdk_closest_match_url_build,
            ]

        if self.constants.should_nuke_kdks is False:
            return

        if not Path(KDK_INSTALL_PATH).exists():
            return

        logging.info("清理未使用的KDK")
        for kdk_folder in Path(KDK_INSTALL_PATH).iterdir():
            if kdk_folder.name.endswith(".kdk") or kdk_folder.name.endswith(".pkg"):
                should_remove = True
                for build in exclude_builds:
                    if kdk_folder.name.endswith(f"_{build}.kdk") or kdk_folder.name.endswith(f"_{build}.pkg"):
                        should_remove = False
                        break
                if should_remove is False:
                    continue
                self._remove_kdk(kdk_folder)


    def validate_kdk_checksum(self, kdk_dmg_path: str = None) -> bool:
        """
        Validates KDK DMG checksum

        Parameters:
            kdk_dmg_path (str, optional): Path to KDK DMG. Defaults to None.

        Returns:
            bool: True if valid, False if invalid
        """

        self.success = False
        self.error_msg = ""

        if kdk_dmg_path is None:
            kdk_dmg_path = self.constants.kdk_download_path

        if not Path(kdk_dmg_path).exists():
            logging.error(f"KDK DMG不存在: {kdk_dmg_path}")
            return False

        # TODO: should we use the checksum from the API?
        result = subprocess.run(["/usr/bin/hdiutil", "verify", self.constants.kdk_download_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logging.info("错误: 内核调试工具包校验和验证失败！")
            subprocess_wrapper.log(result)
            msg = "内核调试工具包校验和验证失败，请重试。\n\n如果此问题持续存在，请确保您在稳定的网络连接（例如以太网）上下载"
            logging.info(f"{msg}")

            self.error_msg = msg
            return False

        self._remove_unused_kdks()
        self.success = True
        logging.info("内核调试工具包校验和已验证")
        return True


class KernelDebugKitUtilities:
    """
    Utilities for KDK handling

    """

    def __init__(self) -> None:
        pass


    def install_kdk_pkg(self, kdk_path: Path) -> bool:
        """
        Installs provided KDK packages

        Parameters:
            kdk_path (Path): Path to KDK package

        Returns:
            bool: True if successful, False if not
        """

        logging.info(f"安装KDK包: {kdk_path.name}")
        logging.info(f"- 这可能需要一段时间...")

        # TODO: Check whether enough disk space is available

        result = subprocess_wrapper.run_as_root(["/usr/sbin/installer", "-pkg", kdk_path, "-target", "/"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            logging.info("KDK安装失败:")
            subprocess_wrapper.log(result)
            return False
        return True


    def install_kdk_dmg(self, kdk_path: Path, only_install_backup: bool = False) -> bool:
        """
        Installs provided KDK disk image

        Parameters:
            kdk_path (Path): Path to KDK disk image

        Returns:
            bool: True if successful, False if not
        """

        logging.info(f"提取下载的KDK磁盘镜像")
        with tempfile.TemporaryDirectory() as mount_point:
            result = subprocess_wrapper.run_as_root(["/usr/bin/hdiutil", "attach", kdk_path, "-mountpoint", mount_point, "-nobrowse"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode != 0:
                logging.info("挂载KDK失败:")
                subprocess_wrapper.log(result)
                return False

            kdk_pkg_path = Path(f"{mount_point}/KernelDebugKit.pkg")
            if not kdk_pkg_path.exists():
                logging.warning("在DMG中找不到KDK包，可能是损坏的!!!")
                self._unmount_disk_image(mount_point)
                return False


            if only_install_backup is False:
                if self.install_kdk_pkg(kdk_pkg_path) is False:
                    self._unmount_disk_image(mount_point)
                    return False

            self._create_backup(kdk_pkg_path, Path(f"{kdk_path.parent}/{KDK_INFO_PLIST}"))
            self._unmount_disk_image(mount_point)

        logging.info("成功安装KDK")
        return True

    def _unmount_disk_image(self, mount_point) -> None:
        """
        Unmounts provided disk image silently

        Parameters:
            mount_point (Path): Path to mount point
        """
        subprocess.run(["/usr/bin/hdiutil", "detach", mount_point], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


    def _create_backup(self, kdk_path: Path, kdk_info_plist: Path) -> None:
        """
        Creates a backup of the KDK

        Parameters:
            kdk_path (Path): Path to KDK
            kdk_info_plist (Path): Path to KDK Info.plist
        """

        if not kdk_path.exists():
            logging.warning("KDK does not exist, cannot create backup")
            return
        if not kdk_info_plist.exists():
            logging.warning("KDK Info.plist does not exist, cannot create backup")
            return

        kdk_info_dict = plistlib.load(kdk_info_plist.open("rb"))

        if 'version' not in kdk_info_dict or 'build' not in kdk_info_dict:
            logging.warning("Malformed KDK Info.plist provided, cannot create backup")
            return

        if not Path(KDK_INSTALL_PATH).exists():
            subprocess_wrapper.run_as_root(["/bin/mkdir", "-p", KDK_INSTALL_PATH], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        kdk_dst_name = f"KDK_{kdk_info_dict['version']}_{kdk_info_dict['build']}.pkg"
        kdk_dst_path = Path(f"{KDK_INSTALL_PATH}/{kdk_dst_name}")

        logging.info(f"创建备份: {kdk_dst_name}")
        if kdk_dst_path.exists():
            logging.info("Backup already exists, skipping")
            return

        result = subprocess_wrapper.run_as_root(generate_copy_arguments(kdk_path, kdk_dst_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            logging.info("Failed to create KDK backup:")
            subprocess_wrapper.log(result)