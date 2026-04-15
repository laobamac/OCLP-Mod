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
KDK_INFO_JSON:    str  = "KdkSupportPkg/manifest.json"
OMAPIv1:          str  = "https://next.oclpapi.simplehac.cn/"
OMAPIv2:          str  = "https://subsequent.oclpapi.simplehac.cn/"
KDK_API_LINK_ORIGIN:     str  = "https://dortania.github.io/KdkSupportPkg/manifest.json"

KDK_ASSET_LIST:   list = None
KDK_SESSION_SELECTION = None

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
        
        # 根据 constants 配置决定 API 链接
        kdk_api_links = []
        
        # 如果启用了代理，优先使用 SimpleHac API
        if self.constants.use_simplehacapi:
            # 根据配置的 API 节点选择链接
            if self.constants.simplehacapi_url == "OMAPIv1":
                kdk_api_links.append(("OMAPIv1", f"{OMAPIv1}{KDK_INFO_JSON}"))
            else:
                # 默认为 OMAPIv2
                kdk_api_links.append(("OMAPIv2", f"{OMAPIv2}{KDK_INFO_JSON}"))
            
            # 添加备用链接
            kdk_api_links.append(("Github - 海外", KDK_API_LINK_ORIGIN))
        else:
            # 不使用代理，优先使用原始链接
            kdk_api_links.append(("Github - 海外", KDK_API_LINK_ORIGIN))
            
            # 添加备用 SimpleHac API 链接
            if self.constants.simplehacapi_url == "OMAPIv1":
                kdk_api_links.append(("OMAPIv1", f"{OMAPIv1}{KDK_INFO_JSON}"))
            else:
                kdk_api_links.append(("OMAPIv2", f"{OMAPIv2}{KDK_INFO_JSON}"))
        
        # 尝试连接 API
        for api_name, api_link in kdk_api_links:
            try:
                logging.info(f"尝试连接 {api_name}: {api_link}")
                results = network_handler.NetworkUtilities().get(
                    api_link,
                    headers={
                        "User-Agent": f"OCLP/{self.constants.patcher_version}"
                    },
                    timeout=5
                )
                
                if results.status_code == 200:
                    logging.info(f"{api_name} 连接成功")
                    KDK_ASSET_LIST = results.json()
                    return KDK_ASSET_LIST
                else:
                    logging.warning(f"{api_name} 返回状态码 {results.status_code}")
                    
            except (requests.exceptions.Timeout, requests.exceptions.TooManyRedirects, requests.exceptions.ConnectionError) as e:
                logging.warning(f"{api_name} 连接失败: {e}")

        logging.info("所有 API 连接均失败")
        return None


    def _get_latest_kdk(self, host_build: str = None, host_version: str = None) -> None:
        """
        获取当前 macOS 版本的最新 KDK
        """
        global KDK_SESSION_SELECTION
        if host_build is None and host_version is None:
            host_build   = self.host_build
            host_version = self.host_version

        parsed_version = cast(packaging.version.Version, packaging.version.parse(host_version))

        if os_data.os_conversion.os_to_kernel(str(parsed_version.major)) < os_data.os_data.ventura:
            self.error_msg = "macOS Monterey 或更早版本不需要 KDK"
            logging.warning(f"{self.error_msg}")
            return

        # 检查当前系统是否已安装完全匹配的 KDK
        self.kdk_installed_path = self._local_kdk_installed()
        if self.kdk_installed_path:
            logging.info(f"KDK 已安装 ({Path(self.kdk_installed_path).name})，跳过")
            self.kdk_already_installed = True
            self.success = True
            return

        remote_kdk_version = self._get_remote_kdks()

        # 如果 API 无法访问，回退到原有的本地模糊匹配逻辑
        if remote_kdk_version is None:
            logging.warning("无法获取 KDK 列表，回退到本地 KDK 匹配")
            loose_version = f"{parsed_version.major}.{parsed_version.minor}"
            self.kdk_installed_path = self._local_kdk_installed(match=loose_version, check_version=True)
            if self.kdk_installed_path:
                self.kdk_already_installed = True
                self.success = True
                return
            self.error_msg = "无法连接 API 且本地无匹配 KDK。"
            return

        # 尝试精确匹配当前 Build
        for kdk in remote_kdk_version:
            if (kdk["build"] == host_build):
                self.kdk_url = kdk["url"]
                self.kdk_url_build = kdk["build"]
                self.kdk_url_version = kdk["version"]
                self.kdk_url_expected_size = kdk["fileSize"]
                self.kdk_url_is_exactly_match = True
                logging.info(f"找到 {host_build} ({host_version}) 的直接匹配")
                break

        # 如果没有精确匹配，检查本次运行的内存缓存或磁盘记录
        if self.kdk_url == "":
            cached_choice = None
            if KDK_SESSION_SELECTION:
                cached_choice = KDK_SESSION_SELECTION
                logging.info(f"使用本次运行中已记录的手动选择: {cached_choice['build']}")
            else:
                kdk_plist_path = Path(self.constants.kdk_download_path).parent / KDK_INFO_PLIST
                if kdk_plist_path.exists():
                    try:
                        kdk_info = plistlib.load(kdk_plist_path.open("rb"))
                        for kdk in remote_kdk_version:
                            if kdk["build"] == kdk_info.get("build"):
                                cached_choice = kdk
                                logging.info(f"从磁盘记录中恢复您的选择: {cached_choice['build']}")
                                KDK_SESSION_SELECTION = kdk
                                break
                    except:
                        pass

            if cached_choice:
                self.kdk_url = cached_choice["url"]
                self.kdk_url_build = cached_choice["build"]
                self.kdk_url_version = cached_choice["version"]
                self.kdk_url_expected_size = cached_choice["fileSize"]
                self.kdk_url_is_exactly_match = False
                
                # 检查缓存选择的版本是否已经安装
                self.kdk_installed_path = self._local_kdk_installed(match=self.kdk_url_build)
                if self.kdk_installed_path:
                    logging.info(f"选定的 KDK ({self.kdk_url_build}) 已安装，跳过下载")
                    self.kdk_already_installed = True
                self.success = True
                return

        if self.kdk_url == "":
            for kdk in remote_kdk_version:
                kdk_version = cast(packaging.version.Version, packaging.version.parse(kdk["version"]))
                if kdk_version > parsed_version or kdk_version.major != parsed_version.major:
                    continue
                if kdk_version.minor not in range(parsed_version.minor - 1, parsed_version.minor + 1):
                    continue
                self.kdk_closest_match_url = kdk["url"]
                self.kdk_closest_match_url_build = kdk["build"]
                self.kdk_closest_match_url_version = kdk["version"]
                self.kdk_closest_match_url_expected_size = kdk["fileSize"]
                break

            # 触发交互窗口
            logging.warning(f"未找到 {host_build} 的直接匹配，等待用户手动选择")
            selection = self._show_manual_selection_ui(remote_kdk_version)
            
            if selection == "AUTO":
                if self.kdk_closest_match_url == "":
                    self.error_msg = "未找到推荐的 KDK 且无精确匹配。"
                    return
                self.kdk_url = self.kdk_closest_match_url
                self.kdk_url_build = self.kdk_closest_match_url_build
                self.kdk_url_version = self.kdk_closest_match_url_version
                self.kdk_url_expected_size = self.kdk_closest_match_url_expected_size
                logging.info("用户选择了自动匹配")
            elif selection: # 用户从列表选择了特定版本
                KDK_SESSION_SELECTION = selection # 存入全局变量
                self.kdk_url = selection["url"]
                self.kdk_url_build = selection["build"]
                self.kdk_url_version = selection["version"]
                self.kdk_url_expected_size = selection["fileSize"]
                self.kdk_url_is_exactly_match = False
                logging.info(f"用户手动选择了: {self.kdk_url_build}")
            else:
                self.error_msg = "用户取消了 KDK 选择，无法继续。"
                logging.warning(self.error_msg)
                return

        self.kdk_installed_path = self._local_kdk_installed(match=self.kdk_url_build)
        if self.kdk_installed_path:
            logging.info(f"选定的 KDK ({self.kdk_url_build}) 已安装，跳过下载")
            self.kdk_already_installed = True
            self.success = True
            return

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

    def _show_manual_selection_ui(self, remote_kdks: list) -> any:
        """
        通过 AppleScript 弹出原生对话框（无需新模块）
        """
        warning_msg = (
            f"⚠️ 警告：未找到与当前系统 ({self.host_build}) 精确匹配的 KDK。\\n\\n"
            "安装不匹配的版本可能会导致内核崩溃或系统无法启动。\\n建议优先手动选择！建议优先手动选择！建议优先手动选择！。"
        )

        # 第一步：弹出带有“自动选择”按钮的警告框
        btn_script = (
            f'display dialog "{warning_msg}" '
            'with title "KDK 匹配警告" '
            'buttons {"手动选择列表", "自动选择"} '
            'default button "手动选择列表" '
            'with icon caution'
        )

        try:
            # 使用已有的 subprocess 模块调用 osascript
            res = subprocess.run(["osascript", "-e", btn_script], capture_output=True, text=True)
            user_response = res.stdout.strip()

            if "自动选择" in user_response:
                return "AUTO"
            
            if "手动选择列表" in user_response:
                options = [f"{k['version']} ({k['build']})" for k in remote_kdks[:20]] # 取前20个
                as_list = '{"' + '", "'.join(options) + '"}'
                
                list_script = (
                    f'choose from list {as_list} '
                    'with title "选择 KDK 版本" '
                    'with prompt "请从下方列表中选择一个您认为合适的版本：" '
                    'OK button name "确认" cancel button name "取消"'
                )
                
                res_list = subprocess.run(["osascript", "-e", list_script], capture_output=True, text=True)
                list_choice = res_list.stdout.strip()

                if list_choice == "false" or not list_choice:
                    return None # 用户取消了列表选择
                
                # 提取括号内的 build 号并匹配回对象
                selected_build = list_choice.split("(")[-1].split(")")[0]
                for kdk in remote_kdks:
                    if kdk["build"] == selected_build:
                        return kdk
            
            return None # 取消或关闭窗口
        except Exception as e:
            logging.error(f"无法调起原生交互窗口: {e}")
            return "AUTO" # 出错时保守起见回退到自动逻辑

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