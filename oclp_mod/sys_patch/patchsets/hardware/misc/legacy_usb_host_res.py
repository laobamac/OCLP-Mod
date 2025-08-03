"""
legacy_usb_wireless.py: Legacy USB/Wireless support for macOS Tahoe and newer
"""

from ..base import BaseHardware, HardwareVariant
from ...base import PatchType
from .....datasets.os_data import os_data
from .....detections import device_probe
from ..... import constants


class LegacyUSBHOST(BaseHardware):
    def __init__(self, xnu_major, xnu_minor, os_build, global_constants: constants.Constants) -> None:
        super().__init__(xnu_major, xnu_minor, os_build, global_constants)

        self.constants: constants.Constants = global_constants

    def name(self) -> str:
        """
        Display name for end users
        """
        return f"{self.hardware_variant()}: 旧版USB扩展"

    def present(self) -> bool:
        """
        Always return True as we're targeting system version rather than specific hardware
        """
        return self.constants.allow_usb_patch


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
        Disable KDK requirement as we're only replacing existing kexts
        """
        return True

    def patches(self) -> dict:
        """
        Patches for legacy USB/Wireless support
        
        Replaces following kexts with compatible versions:
        - IOUSBMassStorageDriver.kext (USB)
        - IOUSBDeviceFamily.kext (USB)
        - IOUSBFamily.kext (USB)
        - IOUSBHostFamily.kext (USB)
        """
        if self.native_os() is True:
            return {}
        
        return {
            "旧版USB扩展": {
                PatchType.OVERWRITE_SYSTEM_VOLUME: {
                    "/System/Library/Extensions": {
                        "AppleUSBACM.kext": "14.7.6",  
                        "AppleUSBAudio.kext": "14.7.6",  
                        "AppleUSBCDC.kext": "14.7.6",  
                        "AppleUSBCommon.kext": "14.7.6",  
                        "IOUSBDeviceFamily.kext": "14.7.6",  
                        "IOUSBFamily.kext": "14.7.6",  
                        "IOUSBHostFamily.kext": "14.7.6",  
                        "IOAccessoryManager.kext": "14.7.6",
                        "IOAccessoryPortUSB.kext": "14.7.6",
                    },
                    "/System/Library/Frameworks": {
                        "IOUSBHost.framework": "14.6.1",
                    },
                },
            },
        }