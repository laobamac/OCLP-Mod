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


    def name(self) -> str:
        """
        Display name for end users
        """
        return f"{self.hardware_variant()}: Intel/BCM无线网卡"


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
        return bcmwl_condition or intelwl_condition


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
            "Modern Wireless": {
                PatchType.OVERWRITE_SYSTEM_VOLUME: {
                    "/usr/libexec": {
                        "airportd": "13.6.5",
                        "wifip2pd": "13.6.5",
                    },
                    "/System/Library/CoreServices": {
                        **({ "WiFiAgent.app": "14.5" } if self._xnu_major >= os_data.sequoia else {}),
                    },
                },
                PatchType.MERGE_SYSTEM_VOLUME: {
                    "/System/Library/Frameworks": {
                        "CoreWLAN.framework": f"13.6.5-{self._xnu_major}",
                    },
                    "/System/Library/PrivateFrameworks": {
                        "CoreWiFi.framework":       f"13.6.5-{self._xnu_major}",
                        "IO80211.framework":        f"13.6.5-{self._xnu_major}",
                        "WiFiPeerToPeer.framework": f"13.6.5-{self._xnu_major}",
                    },
                }
            },
        }
