"""
updates.py: Check for OpenCore Legacy Patcher binary updates

Call check_binary_updates() to determine if any updates are available
Returns dict with Link and Version of the latest binary update if available
"""

import logging

from typing import Optional, Union
from packaging import version

from . import network_handler

from .. import constants


REPO_LATEST_RELEASE_URL: str = "https://api.github.com/repos/dortania/OpenCore-Legacy-Patcher/releases/latest"


class CheckBinaryUpdates:
    def __init__(self, global_constants: constants.Constants) -> None:
        self.constants: constants.Constants = global_constants
        try:
            self.binary_version = version.parse(self.constants.patcher_version)
        except version.InvalidVersion:
            assert self.constants.special_build is True, "Invalid version number for binary"
            self.binary_version = version.parse("0.0.0")

        self.latest_details = None

    def check_if_newer(self, version: Union[str, version.Version]) -> bool:
        return False

    def _check_if_build_newer(self, first_version: Union[str, version.Version], second_version: Union[str, version.Version]) -> bool:
        return False

    def check_binary_updates(self) -> Optional[dict]:
        return None