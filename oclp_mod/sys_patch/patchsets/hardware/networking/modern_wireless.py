"""
modern_wireless.py: Modern Wireless detection
"""

from ..base import BaseHardware, HardwareVariant

from ...base import PatchType

from .....constants  import Constants
from .....detections import device_probe

from .....datasets.os_data import os_data


class ModernWireless(BaseHardware):

    def __init__(self, xnu_major, xnu_minor, os_build, global_constants: Constants) -> None:
        super().__init__(xnu_major, xnu_minor, os_build, global_constants)
        self.patchName = ""


    def name(self) -> str:
        """
        Display name for end users
        """
        bcm_detected = isinstance(self._computer.wifi, device_probe.Broadcom) and (
            self._computer.wifi.chipset in [
                device_probe.Broadcom.Chipsets.AirPortBrcm4360,
                device_probe.Broadcom.Chipsets.AirportBrcmNIC,
                device_probe.Broadcom.Chipsets.AirPortBrcmNICThirdParty,
            ]
        )

        intel_detected = isinstance(self._computer.wifi, device_probe.IntelWirelessCard) and (
            self._computer.wifi.chipset in [
                device_probe.IntelWirelessCard.Chipsets.IntelWirelessIDs,
            ]
        )

        if intel_detected and bcm_detected:
            self.patchName = self._language_handler.get_translation("wireless_intel_bcm_dual", "Intel/BCM Dual Wireless")
            return f"{self._localized_hardware_variant()}: {self.patchName}"
        elif intel_detected:
            self.patchName = self._language_handler.get_translation("wireless_intel", "Intel Wireless")
            return f"{self._localized_hardware_variant()}: {self.patchName}"
        elif bcm_detected:
            self.patchName = self._language_handler.get_translation("wireless_bcm", "BCM Wireless")
            return f"{self._localized_hardware_variant()}: {self.patchName}"
        else:
            self.patchName = self._language_handler.get_translation("wireless_unknown", "Unknown Wireless")
            return f"{self._localized_hardware_variant()}: {self.patchName}"


    def present(self) -> bool:
        """
        Targeting Modern Wireless
        """
        # Detect Broadcom wireless card
        bcmwl_condition = isinstance(self._computer.wifi, device_probe.Broadcom) and (
            self._computer.wifi.chipset in [
                device_probe.Broadcom.Chipsets.AirPortBrcm4360,
                device_probe.Broadcom.Chipsets.AirportBrcmNIC,
                device_probe.Broadcom.Chipsets.AirPortBrcmNICThirdParty,
        ]
    )

        # Detect Intel wireless card
        intelwl_condition = isinstance(self._computer.wifi, device_probe.IntelWirelessCard) and (
            self._computer.wifi.chipset in [
                device_probe.IntelWirelessCard.Chipsets.IntelWirelessIDs,
        ]
    )
    
        if self._xnu_major < os_data.sequoia:
            return bcmwl_condition
        elif self._xnu_major > os_data.sequoia:
            return intelwl_condition or bcmwl_condition
        else:
            return intelwl_condition or bcmwl_condition
        


    def native_os(self) -> bool:
        """
        Dropped support with macOS 14, Sonoma
        """
        return self._xnu_major < os_data.sonoma.value


    def hardware_variant(self) -> HardwareVariant:
        """
        Type of hardware variant
        """
        return HardwareVariant.NETWORKING
    
    def requires_kernel_debug_kit(self) -> bool:
        """
        Apple no longer provides standalone kexts in the base OS
        """
        return self._xnu_major >= os_data.tahoe.value


    def _patches_modern_wireless_common_extended(self) -> dict:
        """
        Extended modern wireless patches
        """
        if self._xnu_major > os_data.sonoma:
            return {}

        return {
            f"{self.patchName} {self._language_handler.get_translation('wireless_extended', 'Extended')}": {
                PatchType.OVERWRITE_SYSTEM_VOLUME: {
                    "/usr/libexec": {
                        "airportd": f"13.7.2-{self._xnu_major}",
                    },
                },
                PatchType.MERGE_SYSTEM_VOLUME: {
                    "/System/Library/Frameworks": {
                        "CoreWLAN.framework": f"13.7.2-{self._xnu_major}",
                    },
                    "/System/Library/PrivateFrameworks": {
                        "CoreWiFi.framework":  f"13.7.2-{self._xnu_major}",
                    },
                },
            },
        }


    def _patches_modern_wireless_common(self) -> dict:
        """
        Common modern wireless patches
        """
        return {
            f"{self.patchName}": {
                PatchType.OVERWRITE_SYSTEM_VOLUME: {
                    "/usr/libexec": {
                        "wifip2pd": f"13.7.2-{self._xnu_major}",
                    },
                },
                PatchType.MERGE_SYSTEM_VOLUME: {
                    "/System/Library/PrivateFrameworks": {
                        "IO80211.framework":        f"13.7.2-{self._xnu_major}",
                        "WiFiPeerToPeer.framework": f"13.7.2-{self._xnu_major}",
                    },
                },
            },
        }

    def patches(self) -> dict:
        """
        Dictionary of patches
        """
        if self.native_os() is True:
            return {}

        return {
            **self._patches_modern_wireless_common(),
            **self._patches_modern_wireless_common_extended(),
        }

        return _base