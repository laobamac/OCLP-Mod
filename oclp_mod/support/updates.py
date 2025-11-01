"""
updates.py: Check for OCLP-Mod binary updates

Call check_binary_updates() to determine if any updates are available
Returns dict with Link and Version of the latest binary update if available
"""

import logging
from typing import Optional
from packaging import version

from . import network_handler
from .. import constants

REPO_LATEST_RELEASE_URL: str = "https://api.github.com/repos/laobamac/OCLP-Mod/releases/latest"

class CheckBinaryUpdates:
    def __init__(self, global_constants: constants.Constants) -> None:
        self.constants: constants.Constants = global_constants
        try:
            self.binary_version = version.parse(self.constants.patcher_version)
        except version.InvalidVersion:
            assert self.constants.special_build is True, "Invalid version number for binary"
            self.binary_version = version.parse("0.0.0")

    def _check_if_build_newer(self, first_version: version.Version, second_version: version.Version) -> bool:
        return first_version > second_version

    def check_binary_updates(self) -> Optional[dict]:
        if self.constants.special_build is True:
            return None

        if not network_handler.NetworkUtilities(REPO_LATEST_RELEASE_URL).verify_network_connection():
            return None

        response = network_handler.NetworkUtilities().get(REPO_LATEST_RELEASE_URL)
        data_set = response.json()

        if "tag_name" not in data_set:
            return None

        try:
            latest_remote_version = version.parse(data_set["tag_name"])
        except version.InvalidVersion:
            return None

        if not self._check_if_build_newer(latest_remote_version, self.binary_version):
            return None

        for asset in data_set["assets"]:
            logging.info(f"Found asset: {asset['name']}")
            if asset["name"] == "OCLP-Mod.pkg":
                return {
                    "Name": asset["name"],
                    "Version": latest_remote_version,
                    "Link": asset["browser_download_url"],
                    "Github Link": f"https://github.com/laobamac/OCLP-Mod/releases/{data_set['tag_name']}",
                }

        return None