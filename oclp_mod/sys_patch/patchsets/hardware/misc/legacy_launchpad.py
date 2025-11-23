"""
legacy_launchpad.py: Legacy LaunchPad support for macOS Tahoe and newer
"""

from ..base import BaseHardware, HardwareVariant

from ...base import PatchType

from .....constants import Constants
from ..... import constants
from .....datasets.os_data import os_data
from .....detections.amfi_detect import AmfiConfigDetectLevel


class LegacyLaunchpad(BaseHardware):

    def __init__(self, xnu_major, xnu_minor, os_build, global_constants: Constants) -> None:
        super().__init__(xnu_major, xnu_minor, os_build, global_constants)

        self.constants: constants.Constants = global_constants


    def name(self) -> str:
        """
        Display name for end users
        """
        return f"{self.hardware_variant()}: 旧版启动台"


    def present(self) -> bool:
        """
        Always present as we're targeting system version rather than specific hardware
        """
        return self.constants.allow_launchpad_patch

    def native_os(self) -> bool:
        """
        Only applicable for macOS 26.0 (Tahoe) and newer
        """
        return self._xnu_major < os_data.tahoe.value


    def hardware_variant(self) -> HardwareVariant:
        """
        Type of hardware variant
        """
        return HardwareVariant.MISCELLANEOUS


    def requires_kernel_debug_kit(self) -> bool:
        """
        Apple no longer provides standalone kexts in the base OS
        """
        return False
    
    def required_amfi_level(self) -> AmfiConfigDetectLevel:
        """
        What level of AMFI configuration is required for this patch set
        Currently defaulted to AMFI needing to be disabled
        """
        return AmfiConfigDetectLevel.NO_CHECK


    def patches(self) -> dict:
        """
        Patches for modern audio support
        Replaces AppleHDA.kext with a compatible version
        """
        if self.native_os() is True:
            return {}

        return {
            "旧版启动台": {
                PatchType.OVERWRITE_SYSTEM_VOLUME: {
                    "/System/Library/CoreServices": {
                        "Dock.app": f"{self.constants.launchpad_verison}",
                        "Spotlight.app": f"{self.constants.launchpad_verison}",
                    },
                    "/System/Applications": {
                        "Apps.app": f"{self.constants.launchpad_verison}",
                        **({"Launchpad.app": f"{self.constants.launchpad_verison}"} if f"{self.constants.launchpad_verison}" != f"26.0 Beta 4" else {}),
                    }
                },
            },
        }