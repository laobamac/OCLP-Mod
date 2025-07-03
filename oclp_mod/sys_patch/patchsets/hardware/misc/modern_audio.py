"""
modern_audio.py: Modern Audio support for macOS Tahoe and newer
"""

from ..base import BaseHardware, HardwareVariant

from ...base import PatchType

from .....constants import Constants
from ..... import constants
from .....detections import device_probe
from .....datasets.os_data import os_data


class ModernAudio(BaseHardware):

    def __init__(self, xnu_major, xnu_minor, os_build, global_constants: Constants) -> None:
        super().__init__(xnu_major, xnu_minor, os_build, global_constants)

        self.constants: constants.Constants = global_constants


    def name(self) -> str:
        """
        Display name for end users
        """
        return f"{self.hardware_variant()}: 音频补丁"


    def present(self) -> bool:
        """
        Always present as we're targeting system version rather than specific hardware
        """
        '''
        if (
            isinstance(self._computer.hda, device_probe.IntelHDAController)
        ):
            return True
        '''
        return self.constants.allow_hda_patch

    def native_os(self) -> bool:
        """
        Only applicable for macOS 26.0 (Tahoe) and newer
        """
        return self._xnu_major < os_data.tahoe.value


    def hardware_variant(self) -> HardwareVariant:
        """
        Type of hardware variant
        """
        return HardwareVariant.AUDIO


    def requires_kernel_debug_kit(self) -> bool:
        """
        Apple no longer provides standalone kexts in the base OS
        """
        return True


    def patches(self) -> dict:
        """
        Patches for modern audio support
        Replaces AppleHDA.kext with a compatible version
        """
        if self.native_os() is True:
            return {}

        return {
            "音频补丁": {
                PatchType.OVERWRITE_SYSTEM_VOLUME: {
                    "/System/Library/Extensions": {
                        "AppleHDA.kext": "15.5-25",
                    },
                },
            },
        }