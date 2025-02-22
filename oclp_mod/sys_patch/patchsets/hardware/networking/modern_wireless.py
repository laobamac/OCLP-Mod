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
            self.patchName = "Intel/BCM双网卡"
            return f"{self.hardware_variant()}: Intel/BCM双网卡"
        elif intel_detected:
            self.patchName = "Intel无线网卡"
            return f"{self.hardware_variant()}: Intel无线网卡"
        elif bcm_detected:
            self.patchName = "BCM无线网卡"
            return f"{self.hardware_variant()}: BCM无线网卡"
        else:
            self.patchName = "未知无线网卡"
            return f"{self.hardware_variant()}: 未知无线网卡"


    def present(self) -> bool:
        """
        Targeting Modern Wireless
        """
        # 检测Broadcom无线网卡
        bcmwl_condition = isinstance(self._computer.wifi, device_probe.Broadcom) and (
            self._computer.wifi.chipset in [
                device_probe.Broadcom.Chipsets.AirPortBrcm4360,
                device_probe.Broadcom.Chipsets.AirportBrcmNIC,
                device_probe.Broadcom.Chipsets.AirPortBrcmNICThirdParty,
        ]
    )

        # 检测Intel无线网卡
        intelwl_condition = isinstance(self._computer.wifi, device_probe.IntelWirelessCard) and (
            self._computer.wifi.chipset in [
                device_probe.IntelWirelessCard.Chipsets.IntelWirelessIDs,
        ]
    )
        if self._xnu_major < os_data.sequoia:
            return bcmwl_condition
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


    def patches(self) -> dict:
        """
        Patches for Modern Wireless
        """
        if self.native_os() is True:
            return {}

        return {
            f"{self.patchName}": {
                PatchType.OVERWRITE_SYSTEM_VOLUME: {
                    "/usr/libexec": {
                        "airportd": f"13.7.2-{self._xnu_major}",
                        "wifip2pd": f"13.7.2-{self._xnu_major}",
                    },
                    "/System/Library/CoreServices": {
                        **({ "WiFiAgent.app": "14.7.2" } if self._xnu_major >= os_data.sequoia else {}),
                    },
                },
                PatchType.MERGE_SYSTEM_VOLUME: {
                    "/System/Library/Frameworks": {
                        "CoreWLAN.framework": f"13.7.2-{self._xnu_major}",
                    },
                    "/System/Library/PrivateFrameworks": {
                        "CoreWiFi.framework":       f"13.7.2-{self._xnu_major}",
                        "IO80211.framework":        f"13.7.2-{self._xnu_major}",
                        "WiFiPeerToPeer.framework": f"13.7.2-{self._xnu_major}",
                    },
                }
            },
        }
