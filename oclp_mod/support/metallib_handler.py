"""
metallib_handler.py: Library for handling Metal libraries
"""

import logging
import requests
import subprocess
import packaging.version

from typing  import cast
from pathlib import Path

from .  import network_handler, subprocess_wrapper
from .. import constants

from ..datasets import os_data


METALLIB_INSTALL_PATH: str  = "/Library/Application Support/Dortania/MetallibSupportPkg"
METALLIB_API_LINK_PROXY:     str  = "https://next.oclpapi.simplehac.cn/MetallibSupportPkg/manifest.json"
METALLIB_API_LINK_ORIGIN:     str  = "https://dortania.github.io/MetallibSupportPkg/manifest.json"

METALLIB_ASSET_LIST:   list = None

class MetalLibraryObject:

    def __init__(self, global_constants: constants.Constants,
                 host_build: str, host_version: str,
                 ignore_installed: bool = False, passive: bool = False
        ) -> None:

        self.constants: constants.Constants = global_constants

        self.host_build:   str = host_build    # ex. 20A5384c
        self.host_version: str = host_version  # ex. 11.0.1

        self.passive: bool = passive  # Don't perform actions requiring elevated privileges

        self.ignore_installed:      bool = ignore_installed   # If True, will ignore any installed MetallibSupportPkg PKGs and download the latest
        self.metallib_already_installed: bool = False

        self.metallib_installed_path: str = ""

        self.metallib_url:         str = ""
        self.metallib_url_build:   str = ""
        self.metallib_url_version: str = ""

        self.metallib_url_is_exactly_match: bool = False

        self.metallib_closest_match_url:         str = ""
        self.metallib_closest_match_url_build:   str = ""
        self.metallib_closest_match_url_version: str = ""

        self.success: bool = False

        self.error_msg: str = ""

        self._get_latest_metallib()


    def _get_remote_metallibs(self) -> dict:
        """
        Get the MetallibSupportPkg list from the API
        """

        global METALLIB_ASSET_LIST

        logging.info("从 MetallibSupportPkg API 拉取 metallib 列表")
        if METALLIB_ASSET_LIST:
            return METALLIB_ASSET_LIST
        
        if self.constants.use_github_proxy == True:
            METALLIB_API_LINK:  str = METALLIB_API_LINK_PROXY
        else:
            METALLIB_API_LINK:  str = METALLIB_API_LINK_ORIGIN

        try:
            results = network_handler.NetworkUtilities().get(
                METALLIB_API_LINK,
                headers={
                    "User-Agent": f"OCLP/{self.constants.patcher_version}"
                },
                timeout=5
            )
        except (requests.exceptions.Timeout, requests.exceptions.TooManyRedirects, requests.exceptions.ConnectionError):
            logging.info("无法联系 MetallibSupportPkg API")
            return None

        if results.status_code != 200:
            logging.info("无法获取 Metallib 列表")
            return None

        METALLIB_ASSET_LIST = results.json()

        return METALLIB_ASSET_LIST


    def _get_latest_metallib(self) -> None:
        """
        Get the latest MetallibSupportPkg PKG
        """

        parsed_version = cast(packaging.version.Version, packaging.version.parse(self.host_version))

        if os_data.os_conversion.os_to_kernel(str(parsed_version.major)) < os_data.os_data.sequoia:
            self.error_msg = "macOS Sonoma 或更早版本不需要 MetallibSupportPkg"
            logging.warning(f"{self.error_msg}")
            return

        self.metallib_installed_path = self._local_metallib_installed()
        if self.metallib_installed_path:
            logging.info(f"已安装 metallib ({Path(self.metallib_installed_path).name})，跳过")
            self.metallib_already_installed = True
            self.success = True
            return

        remote_metallib_version = self._get_remote_metallibs()

        if remote_metallib_version is None:
            logging.warning("无法获取 metallib 列表，回退到本地 metallib 匹配")

            # 首先检查是否安装了与当前 macOS 版本匹配的 metallib
            # 例如 13.0.1 vs 13.0
            loose_version = f"{parsed_version.major}.{parsed_version.minor}"
            logging.info(f"检查宽松匹配的 metallibs {loose_version}")
            self.metallib_installed_path = self._local_metallib_installed(match=loose_version, check_version=True)
            if self.metallib_installed_path:
                logging.info(f"找到匹配的 metallib: {Path(self.metallib_installed_path).name}")
                self.metallib_already_installed = True
                self.success = True
                return

            older_version = f"{parsed_version.major}.{parsed_version.minor - 1 if parsed_version.minor > 0 else 0}"
            logging.info(f"检查匹配的 metallibs {older_version}")
            self.metallib_installed_path = self._local_metallib_installed(match=older_version, check_version=True)
            if self.metallib_installed_path:
                logging.info(f"找到匹配的 metallib: {Path(self.metallib_installed_path).name}")
                self.metallib_already_installed = True
                self.success = True
                return

            logging.warning(f"找不到匹配 {self.host_version} 或 {older_version} 的 metallib，请手动安装一个")

            self.error_msg = f"无法联系 MetallibSupportPkg API，并且没有安装匹配 {self.host_version} ({self.host_build}) 或 {older_version} 的 metallib。\n请确保您有网络连接或手动安装一个 metallib."

            return


        # 首先检查精确匹配
        for metallib in remote_metallib_version:
            if (metallib["build"] != self.host_build):
                continue
            self.metallib_url = metallib["url"]
            self.metallib_url_build = metallib["build"]
            self.metallib_url_version = metallib["version"]
            self.metallib_url_is_exactly_match = True
            break

        # 如果没有精确匹配，检查最接近的匹配
        if self.metallib_url == "":
            for metallib in remote_metallib_version:
                metallib_version = cast(packaging.version.Version, packaging.version.parse(metallib["version"]))
                if metallib_version > parsed_version:
                    continue
                if metallib_version.major != parsed_version.major:
                    continue
                if metallib_version.minor not in range(parsed_version.minor - 1, parsed_version.minor + 1):
                    continue

                # metallib 列表已经按版本然后日期排序，所以第一个匹配的就是最接近的
                self.metallib_closest_match_url = metallib["url"]
                self.metallib_closest_match_url_build = metallib["build"]
                self.metallib_closest_match_url_version = metallib["version"]
                self.metallib_url_is_exactly_match = False
                break

        if self.metallib_url == "":
            if self.metallib_closest_match_url == "":
                logging.warning(f"未找到 {self.host_build} ({self.host_version}) 的 metallibs")
                self.error_msg = f"未找到 {self.host_build} ({self.host_version}) 的 metallibs"
                return
            logging.info(f"未找到 {self.host_build} 的直接匹配，回退到最接近的匹配")
            logging.info(f"最接近的匹配: {self.metallib_closest_match_url_build} ({self.metallib_closest_match_url_version})")

            self.metallib_url = self.metallib_closest_match_url
            self.metallib_url_build = self.metallib_closest_match_url_build
            self.metallib_url_version = self.metallib_closest_match_url_version
        else:
            logging.info(f"找到 {self.host_build} ({self.host_version}) 的直接匹配")


        # 检查此 metallib 是否已安装
        self.metallib_installed_path = self._local_metallib_installed(match=self.metallib_url_build)
        if self.metallib_installed_path:
            logging.info(f"已安装 metallib ({Path(self.metallib_installed_path).name})，跳过")
            self.metallib_already_installed = True
            self.success = True
            return

        logging.info("推荐的 metallib 如下:")
        logging.info(f"- metallib 构建: {self.metallib_url_build}")
        logging.info(f"- metallib 版本: {self.metallib_url_version}")
        logging.info(f"- metallib URL: {self.metallib_url}")

        self.success = True


    def _local_metallib_installed(self, match: str = None, check_version: bool = False) -> str:
        """
        Check if a metallib is already installed
        """

        if self.ignore_installed:
            return None

        if not Path(METALLIB_INSTALL_PATH).exists():
            return None

        for metallib_folder in Path(METALLIB_INSTALL_PATH).iterdir():
            if not metallib_folder.is_dir():
                continue
            if check_version:
                if match not in metallib_folder.name:
                    continue
            else:
                if not metallib_folder.name.endswith(f"-{match}"):
                    continue

            return metallib_folder

        return None


    def retrieve_download(self, override_path: str = "") -> network_handler.DownloadObject:
        """
        Retrieve MetallibSupportPkg PKG download object
        """

        self.success = False
        self.error_msg = ""

        if self.metallib_already_installed:
            logging.info("无需下载，已安装 metallib")
            self.success = True
            return None

        if self.metallib_url == "":
            self.error_msg = "无法检索 metallib 目录，没有 metallib 可下载"
            logging.error(self.error_msg)
            return None

        logging.info(f"返回 metallib 的 DownloadObject: {Path(self.metallib_url).name}")
        self.success = True

        metallib_download_path = self.constants.metallib_download_path if override_path == "" else Path(override_path)
        return network_handler.DownloadObject(self.metallib_url, metallib_download_path, 76,000,000)


    def install_metallib(self, metallib: str = None) -> None:
        """
        Install MetallibSupportPkg PKG
        """

        if not self.success:
            logging.error("无法安装 metallib，没有成功检索到 metallib")
            return False

        if self.metallib_already_installed:
            logging.info("无需安装，已安装 metallib")
            return True

        result = subprocess_wrapper.run_as_root([
            "/usr/sbin/installer", "-pkg", metallib if metallib else self.constants.metallib_download_path, "-target", "/"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            subprocess_wrapper.log(result)
            return False

        return True