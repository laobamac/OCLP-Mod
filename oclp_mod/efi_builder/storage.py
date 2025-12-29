"""
storage.py: Class for handling Storage Controller Patches, invocation from build.py
"""

import logging

from . import support

from .. import constants

from ..support import utilities
from ..detections import device_probe
from ..languages.language_handler import LanguageHandler

from ..datasets import (
    model_array,
    smbios_data,
    cpu_data
)


class BuildStorage:
    """
    Build Library for System Storage Support

    Invoke from build.py
    """

    def __init__(self, model: str, global_constants: constants.Constants, config: dict) -> None:
        self.model: str = model
        self.config: dict = config
        self.constants: constants.Constants = global_constants
        self.computer: device_probe.Computer = self.constants.computer
        self._language_handler = LanguageHandler(self.constants)

        self._build()


    def _build(self) -> None:
        """
        Kick off Storage Build Process
        """

        self._ahci_handling()
        self._pata_handling()
        self._misc_handling()
        self._pcie_handling()
        self._trim_handling()


    def _ahci_handling(self) -> None:
        """
        AHCI (SATA) Handler
        """

        # MacBookAir6,x ship with an AHCI over PCIe SSD model 'APPLE SSD TS0128F' and 'APPLE SSD TS0256F'
        # This controller is not supported properly in macOS Ventura, instead populating itself as 'Media' with no partitions
        # To work-around this, use Monterey's AppleAHCI driver to force support
        if not self.constants.custom_model:
            sata_devices = [i for i in self.computer.storage if isinstance(i, device_probe.SATAController)]
            for controller in sata_devices:
                # https://linux-hardware.org/?id=pci:1179-010b-1b4b-9183
                if controller.vendor_id == 0x1179 and controller.device_id == 0x010b:
                    logging.info("- 启用 AHCI SSD 补丁")
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("MonteAHCIPort.kext", self.constants.monterey_ahci_version, self.constants.monterey_ahci_path)
                    break
        elif self.model in ["MacBookAir6,1", "MacBookAir6,2"]:
            logging.info("- 启用 AHCI SSD 补丁")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("MonteAHCIPort.kext", self.constants.monterey_ahci_version, self.constants.monterey_ahci_path)

        # ThirdPartyDrives Check
        if self.constants.allow_3rd_party_drives is True:
            for drive in ["SATA 2.5", "SATA 3.5", "mSATA"]:
                if not self.model in smbios_data.smbios_dictionary:
                    break
                if not "Stock Storage" in smbios_data.smbios_dictionary[self.model]:
                    break
                if drive in smbios_data.smbios_dictionary[self.model]["Stock Storage"]:
                    if not self.constants.custom_model:
                        if self.computer.third_party_sata_ssd is True:
                            logging.info(self._language_handler.get_translation("add_sata_hibernate_patch"))
                            self.config["Kernel"]["Quirks"]["ThirdPartyDrives"] = True
                            break
                    else:
                        logging.info(self._language_handler.get_translation("add_sata_hibernate_patch"))
                        self.config["Kernel"]["Quirks"]["ThirdPartyDrives"] = True
                        break


    def _pata_handling(self) -> None:
        """
        ATA (PATA) Handler
        """

        if not self.model in smbios_data.smbios_dictionary:
            return
        if not "Stock Storage" in smbios_data.smbios_dictionary[self.model]:
            return
        if not "PATA" in smbios_data.smbios_dictionary[self.model]["Stock Storage"]:
            return

        support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleIntelPIIXATA.kext", self.constants.piixata_version, self.constants.piixata_path)


    def _pcie_handling(self) -> None:
        """
        PCIe/NVMe Handler
        """

        if not self.constants.custom_model and (self.constants.allow_oc_everywhere is True or self.model in model_array.MacPro):
            # Use Innie's same logic:
            # https://github.com/cdf/Innie/blob/v1.3.0/Innie/Innie.cpp#L90-L97
            for i, controller in enumerate(self.computer.storage):
                logging.info(f"- 修复 PCIe 存储控制器 ({i + 1}) 报告")
                if controller.pci_path:
                    self.config["DeviceProperties"]["Add"][controller.pci_path] = {"built-in": 1}
                else:
                    logging.info(f"- 未能找到 PCIe 存储控制器 {i} 的设备路径，回退到 Innie")
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("Innie.kext", self.constants.innie_version, self.constants.innie_path)

        if not self.constants.custom_model:
            nvme_devices = [i for i in self.computer.storage if isinstance(i, device_probe.NVMeController)]
            if self.constants.allow_nvme_fixing is True:
                for i, controller in enumerate(nvme_devices):
                    if controller.vendor_id == 0x106b:
                        continue
                    logging.info(f"- 找到第三方 NVMe SSD ({i + 1}): {utilities.friendly_hex(controller.vendor_id)}:{utilities.friendly_hex(controller.device_id)}")
                    self.config["#Revision"][f"Hardware-NVMe-{i}"] = f"{utilities.friendly_hex(controller.vendor_id)}:{utilities.friendly_hex(controller.device_id)}"

                    # 禁用位 0 (L0s)，启用位 1 (L1)
                    nvme_aspm = (controller.aspm & (~0b11)) | 0b10

                    if controller.pci_path:
                        logging.info(f"- 找到 NVMe ({i}) 在 {controller.pci_path}")
                        self.config["DeviceProperties"]["Add"].setdefault(controller.pci_path, {})["pci-aspm-default"] = nvme_aspm
                        self.config["DeviceProperties"]["Add"][controller.pci_path.rpartition("/")[0]] = {"pci-aspm-default": nvme_aspm}
                    else:
                        if "-nvmefaspm" not in self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"]:
                            logging.info("- 回退到 -nvmefaspm")
                            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -nvmefaspm"

                    if (controller.vendor_id != 0x144D and controller.device_id != 0xA804):
                        # 避免在存在原生 Apple NVMe 驱动时注入 NVMeFix
                        # https://github.com/acidanthera/NVMeFix/blob/1.0.9/NVMeFix/NVMeFix.cpp#L220-L225
                        support.BuildSupport(self.model, self.constants, self.config).enable_kext("NVMeFix.kext", self.constants.nvmefix_version, self.constants.nvmefix_path)

            if any((controller.vendor_id == 0x106b and controller.device_id in [0x2001, 0x2003]) for controller in nvme_devices):
                # 恢复在 macOS 14.0 Beta 2 中移除的 S1X/S3X NVMe 支持
                # - APPLE SSD AP0128H, AP0256H, 等
                # - APPLE SSD AP0128J, AP0256J, 等
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOS3XeFamily.kext", self.constants.s3x_nvme_version, self.constants.s3x_nvme_path)

        # 恢复在 macOS 14.0 Beta 2 中移除的 S1X/S3X NVMe 支持
        # Apple 对 S1X 和 S3X 的使用相当随意且不一致，因此我们将尝试为所有带有 NVMe 驱动的机型恢复支持
        # 此外扩展到覆盖所有使用 12+16 引脚 SSD 布局的 Mac 机型，以支持较旧的机器上使用较新的驱动
        if self.constants.custom_model and self.model in smbios_data.smbios_dictionary:
            if "CPU Generation" in smbios_data.smbios_dictionary[self.model]:
                if (cpu_data.CPUGen.haswell <= smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.kaby_lake) or self.model in [ "MacPro6,1" ]:
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOS3XeFamily.kext", self.constants.s3x_nvme_version, self.constants.s3x_nvme_path)

        # Apple RAID Card 检查
        if not self.constants.custom_model:
            if self.computer.storage:
                for storage_controller in self.computer.storage:
                    if storage_controller.vendor_id == 0x106b and storage_controller.device_id == 0x008A:
                        # AppleRAIDCard.kext 仅支持 pci106b,8a
                        support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleRAIDCard.kext", self.constants.apple_raid_version, self.constants.apple_raid_path)
                        break
        elif self.model.startswith("Xserve"):
            # 对于 Xserves，假设存在 RAID
            # 主要是由于 Xserve2,1 仅限于 10.7，因此无法进行硬件检测
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleRAIDCard.kext", self.constants.apple_raid_version, self.constants.apple_raid_path)


    def _misc_handling(self) -> None:
        """
        SDXC Handler
        """

        if not self.model in smbios_data.smbios_dictionary:
            return
        if not "CPU Generation" in smbios_data.smbios_dictionary[self.model]:
            return

        # 自 macOS Monterey 起，Apple 的 SDXC 驱动程序要求系统支持 VT-D
        # 然而，预 Ivy Bridge 的系统不支持此功能
        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.sandy_bridge.value:
            if (self.constants.computer.sdxc_controller and not self.constants.custom_model) or (self.model.startswith("MacBookPro8") or self.model.startswith("Macmini5")):
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("BigSurSDXC.kext", self.constants.bigsursdxc_version, self.constants.bigsursdxc_path)


    def _trim_handling(self) -> None:
        """
        TRIM Handler
        """

        if self.constants.apfs_trim_timeout is False:
            logging.info(f"- 禁用 APFS TRIM 超时")
            self.config["Kernel"]["Quirks"]["SetApfsTrimTimeout"] = 0