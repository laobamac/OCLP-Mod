"""
firmware.py: Class for handling CPU and Firmware Patches, invocation from build.py
"""

import shutil
import logging
import binascii

from pathlib import Path

from . import support

from .. import constants

from ..support import generate_smbios
from ..detections import device_probe

from ..datasets import (
    smbios_data,
    cpu_data,
    os_data
)


class BuildFirmware:
    """
    Build Library for CPU and Firmware Support

    Invoke from build.py
    """

    def __init__(self, model: str, global_constants: constants.Constants, config: dict) -> None:
        self.model: str = model
        self.config: dict = config
        self.constants: constants.Constants = global_constants
        self.computer: device_probe.Computer = self.constants.computer

        self._build()

    def _build(self) -> None:
        """
        Kick off CPU and Firmware Build Process
        """

        self._cpu_compatibility_handling()
        self._power_management_handling()
        self._acpi_handling()
        self._firmware_driver_handling()
        self._firmware_compatibility_handling()
        self._apple_logo_handling()

    def _apple_logo_handling(self) -> None:
        """
        Apple logo Handling
        """

        # Macs that natively support Monterey (excluding MacPro6,1 and Macmini7,1) won't have boot.efi draw the Apple logo.
        # This causes a cosmetic issue when booting through OpenCore, as the Apple logo will be missing.

        if not self.model in smbios_data.smbios_dictionary:
            return

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] >= os_data.os_data.monterey and self.model not in ["MacPro6,1", "Macmini7,1"]:
            logging.info("启用 Boot Logo 补丁")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Booter"]["Patch"], "Comment", "Patch SkipLogo")["Enabled"] = True

    def _power_management_handling(self) -> None:
        """
        Power Management Handling
        """

        if not self.model in smbios_data.smbios_dictionary:
            return
        if not "CPU Generation" in smbios_data.smbios_dictionary[self.model]:
            return

        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.ivy_bridge.value:
            logging.info("启用旧版电源管理支持")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleIntelCPUPowerManagement.kext", self.constants.aicpupm_version, self.constants.aicpupm_path)
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleIntelCPUPowerManagementClient.kext", self.constants.aicpupm_version, self.constants.aicpupm_client_path)

        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.sandy_bridge.value or self.constants.disable_fw_throttle is True:
            logging.info("覆盖 ACPI SMC 匹配")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("ASPP-Override.kext", self.constants.aspp_override_version, self.constants.aspp_override_path)
            if self.constants.disable_fw_throttle is True:
                support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Add"], "BundlePath", "ASPP-Override.kext")["MinKernel"] = ""

        if self.constants.disable_fw_throttle is True and smbios_data.smbios_dictionary[self.model]["CPU Generation"] >= cpu_data.CPUGen.nehalem.value:
            logging.info("禁用固件节流")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("SimpleMSR.kext", self.constants.simplemsr_version, self.constants.simplemsr_path)

    def _acpi_handling(self) -> None:
        """
        ACPI Table Handling
        """

        if not self.model in smbios_data.smbios_dictionary:
            return
        if not "CPU Generation" in smbios_data.smbios_dictionary[self.model]:
            return

        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] == cpu_data.CPUGen.nehalem.value and not (self.model.startswith("MacPro") or self.model.startswith("Xserve")):
            logging.info("添加 SSDT-CPBG.aml")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["ACPI"]["Add"], "Path", "SSDT-CPBG.aml")["Enabled"] = True
            shutil.copy(self.constants.pci_ssdt_path, self.constants.acpi_path)

        if cpu_data.CPUGen.sandy_bridge <= smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.ivy_bridge.value and self.model != "MacPro6,1":
            logging.info("启用 Windows 10 UEFI 音频支持")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["ACPI"]["Add"], "Path", "SSDT-PCI.aml")["Enabled"] = True
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["ACPI"]["Patch"], "Comment", "BUF0 to BUF1")["Enabled"] = True
            shutil.copy(self.constants.windows_ssdt_path, self.constants.acpi_path)

    def _cpu_compatibility_handling(self) -> None:
        """
        CPU Compatibility Handling
        """

        if not self.model in smbios_data.smbios_dictionary:
            return
        if not "CPU Generation" in smbios_data.smbios_dictionary[self.model]:
            return

        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.penryn.value:
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("AAAMouSSE.kext", self.constants.mousse_version, self.constants.mousse_path)
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("telemetrap.kext", self.constants.telemetrap_version, self.constants.telemetrap_path)

        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.ivy_bridge.value:
            logging.info("在 Ventura 中启用 Rosetta Cryptex 支持")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("CryptexFixup.kext", self.constants.cryptexfixup_version, self.constants.cryptexfixup_path)

        if (not self.constants.custom_model and "RDRAND" not in self.computer.cpu.flags) or \
            (smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.sandy_bridge.value):
            logging.info("添加 SurPlus 补丁以解决竞争条件")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Patch"], "Comment", "SurPlus v1 - PART 1 of 2 - Patch read_erandom (inlined in _early_random)")["Enabled"] = True
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Patch"], "Comment", "SurPlus v1 - PART 2 of 2 - Patch register_and_init_prng")["Enabled"] = True
            if self.constants.force_surplus is True:
                logging.info("允许 SurPlus 在所有较新的操作系统上运行")
                support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Patch"], "Comment", "SurPlus v1 - PART 1 of 2 - Patch read_erandom (inlined in _early_random)")["MaxKernel"] = ""
                support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Patch"], "Comment", "SurPlus v1 - PART 2 of 2 - Patch register_and_init_prng")["MaxKernel"] = ""

        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] < cpu_data.CPUGen.sandy_bridge.value:
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("NoAVXFSCompressionTypeZlib.kext", self.constants.apfs_zlib_version, self.constants.apfs_zlib_path)
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("NoAVXFSCompressionTypeZlib-AVXpel.kext", self.constants.apfs_zlib_v2_version, self.constants.apfs_zlib_v2_path)

        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.penryn.value:
            logging.info("添加 IOHIDFamily 补丁")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Patch"], "Identifier", "com.apple.iokit.IOHIDFamily")["Enabled"] = True

        if self.constants.force_quad_thread is True:
            logging.info("添加 CPU 线程限制补丁")
            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " cpus=4"

    def _firmware_driver_handling(self) -> None:
        """
        Firmware Driver Handling (Drivers/*.efi)
        """

        if not self.model in smbios_data.smbios_dictionary:
            return
        if not "CPU Generation" in smbios_data.smbios_dictionary[self.model]:
            return
        
        # APFS check
        # 使用Sequoia 15.5的APFS驱动来启用Tahoe的文件保险箱
        logging.info("- 启用Tahoe 26的文件保险箱")
        self.config["UEFI"]["APFS"]["EnableJumpstart"] = False
        shutil.copy(self.constants.sequoia_apfs_driver_path, self.constants.drivers_path)
        support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("apfs_aligned.efi", "UEFI", "Drivers")["Enabled"] = True

        # Exfat check
        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] < cpu_data.CPUGen.sandy_bridge.value:
            # Sandy Bridge 和更新的 Mac 原生支持 ExFat
            logging.info("- 添加 ExFatDxeLegacy.efi")
            shutil.copy(self.constants.exfat_legacy_driver_path, self.constants.drivers_path)
            support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("ExFatDxeLegacy.efi", "UEFI", "Drivers")["Enabled"] = True

        # NVMe check
        if self.constants.nvme_boot is True:
            logging.info("- 启用 NVMe 启动支持")
            shutil.copy(self.constants.nvme_driver_path, self.constants.drivers_path)
            support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("NvmExpressDxe.efi", "UEFI", "Drivers")["Enabled"] = True

        # USB check
        if self.constants.xhci_boot is True:
            logging.info("- 添加 USB 3.0 控制器补丁")
            logging.info("- 添加 XhciDxe.efi 和 UsbBusDxe.efi")
            shutil.copy(self.constants.xhci_driver_path, self.constants.drivers_path)
            shutil.copy(self.constants.usb_bus_driver_path, self.constants.drivers_path)
            support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("XhciDxe.efi", "UEFI", "Drivers")["Enabled"] = True
            support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("UsbBusDxe.efi", "UEFI", "Drivers")["Enabled"] = True

        # PCIe Link Rate check
        if self.model == "MacPro3,1":
            logging.info("- 添加 PCIe 链路速率补丁")
            shutil.copy(self.constants.link_rate_driver_path, self.constants.drivers_path)
            support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("FixPCIeLinkRate.efi", "UEFI", "Drivers")["Enabled"] = True

        # CSM check
        # 对于型号支持，请检查固件中的 GUID 以及 Bootcamp Assistant 的 Info.plist 中的 'PreUEFIModels' 键
        # 参考: https://github.com/acidanthera/OpenCorePkg/blob/0.9.5/Platform/OpenLegacyBoot/OpenLegacyBoot.c#L19
        if Path(self.constants.drivers_path / Path("OpenLegacyBoot.efi")).exists():
            # if smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.ivy_bridge.value and self.model != "MacPro6,1":
            #     logging.info("- 启用 CSM 支持")
            #     support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("OpenLegacyBoot.efi", "UEFI", "Drivers")["Enabled"] = True
            # else:
            #     # 与 OpenCorePkg 一起发布，因此如果不使用则删除
            #     (self.constants.drivers_path / Path("OpenLegacyBoot.efi")).unlink()

            # 目前出于兼容性原因已禁用
            # 某些机器在启动时使用 OpenLegacyBoot.efi 会冻结
            (self.constants.drivers_path / Path("OpenLegacyBoot.efi")).unlink()

    def _firmware_compatibility_handling(self) -> None:
        """
        Firmware Compatibility Handling (Firmware and Kernel)
        """

        self._dual_dp_handling()

        # Patches IOPCIConfigurator.cpp's IOPCIIsHotplugPort to skip configRead16/32 calls
        # Credit to CaseySJ for original discovery:
        # - Patch: https://github.com/AMD-OSX/AMD_Vanilla/pull/196
        # - Source: https://github.com/apple-oss-distributions/IOPCIFamily/blob/IOPCIFamily-583.40.1/IOPCIConfigurator.cpp#L968-L1022
        #
        # 目前所有预 Sandy Bridge Mac 缺少 iGPU 的机器以及 MacPro6,1 都受益于此补丁
        # 否则某些图形硬件将无法唤醒，macOS 将错误地报告硬件为 ExpressCard 基础的，
        # 阻止 MacPro6,1 以未加速的方式启动并破坏低功耗状态。
        if (
            self.model in ["MacPro6,1", "MacBookPro4,1"] or
            (
                smbios_data.smbios_dictionary[self.model]["CPU Generation"] < cpu_data.CPUGen.sandy_bridge.value and \
                not self.model.startswith("MacBook")
            )
        ):
            logging.info("- 添加 PCI 总线枚举补丁")
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Patch"], "Comment", "CaseySJ - Fix PCI bus enumeration (Ventura)")["Enabled"] = True
            # Sonoma 稍微调整了这一行
            # - https://github.com/apple-oss-distributions/IOPCIFamily/blob/IOPCIFamily-583.40.1/IOPCIConfigurator.cpp#L1009
            support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Patch"], "Comment", "Fix PCI bus enumeration (Sonoma)")["Enabled"] = True

        if self.constants.set_vmm_cpuid is True:
            logging.info("- 启用 VMM 补丁")
            self.config["Kernel"]["Emulate"]["Cpuid1Data"] = binascii.unhexlify("00000000000000000000008000000000")
            self.config["Kernel"]["Emulate"]["Cpuid1Mask"] = binascii.unhexlify("00000000000000000000008000000000")

        if (
            self.model.startswith("MacBook")
            and (
                smbios_data.smbios_dictionary[self.model]["CPU Generation"] == cpu_data.CPUGen.haswell.value or
                smbios_data.smbios_dictionary[self.model]["CPU Generation"] == cpu_data.CPUGen.broadwell.value
            )
        ):
            # 修复虚拟机支持以支持非 macOS 操作系统
            # Haswell 和 Broadwell MacBook 锁定 VMX 位如果启动 UEFI Windows
            logging.info("- 启用 VMX 位以支持非 macOS 操作系统")
            self.config["UEFI"]["Quirks"]["EnableVmx"] = True

        # 解决休眠问题，连接所有固件驱动程序会中断从 S4 过渡
        # 主要适用于 MacBookPro9,1
        if self.constants.disable_connectdrivers is True:
            logging.info("- 禁用 ConnectDrivers")
            self.config["UEFI"]["ConnectDrivers"] = False

        if self.constants.nvram_write is False:
            logging.info("- 禁用硬件 NVRAM 写入")
            self.config["NVRAM"]["WriteFlash"] = False

        if self.constants.serial_settings != "None":
            # AppleMCEReporter 对于哪些模型附加到 kext 非常挑剔
            # 通常它会在多插槽系统上内核崩溃，即使在单插槽系统上也可能导致不稳定
            # 为了避免任何问题，如果伪造的 SMBIOS 受影响，我们将禁用它
            affected_smbios = ["MacPro6,1", "MacPro7,1", "iMacPro1,1"]
            if self.model not in affected_smbios:
                # 如果 MacPro6,1 主机伪造，我们可以安全启用它
                if self.constants.override_smbios in affected_smbios or generate_smbios.set_smbios_model_spoof(self.model) in affected_smbios:
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleMCEReporterDisabler.kext", self.constants.mce_version, self.constants.mce_path)


    def _dual_dp_handling(self) -> None:
        """
        Dual DisplayPort Stream Handler (ex. 5k iMac)

        Apple 在 5K iMac 和 iMac Pro 上有两种显示处理模式
        如果在启动链中的任何时候加载了“不受支持”的条目，固件会让显示控制器进入仅使用单个 DisplayPort 1.2 流的 4K 兼容模式。
        这是为了防止系统进入无法处理 5K 显示使用的自定义双 DisplayPort 1.2 流的环境

        为了绕过此问题，我们欺骗固件通过 Apple 的硬件诊断测试加载 OpenCore
        具体来说，隐藏为 '/System/Library/CoreServices/.diagnostics/Drivers/HardwareDrivers/Product.efi' 下的 Product.efi
        能够通过加密文件缓冲区加载 ./Drivers/HardwareDrivers 的原因是其他驱动程序（如 ./qa_logger.efi）是通过设备路径调用的。
        """

        if "Dual DisplayPort Display" not in smbios_data.smbios_dictionary[self.model]:
            return

        logging.info("- 添加 4K/5K 显示补丁")
        # 设置 LauncherPath 为 '/boot.efi'
        # 这是为了确保只有 Mac 的固件呈现启动选项，而不是 OpenCore
        # https://github.com/acidanthera/OpenCorePkg/blob/0.7.6/Library/OcAppleBootPolicyLib/OcAppleBootPolicyLib.c#L50-L73
        self.config["Misc"]["Boot"]["LauncherPath"] = "\\boot.efi"

        # 设置 diags.efi 链式加载
        Path(self.constants.opencore_release_folder / Path("System/Library/CoreServices/.diagnostics/Drivers/HardwareDrivers")).mkdir(parents=True, exist_ok=True)
        if self.constants.boot_efi is True:
            path_oc_loader = self.constants.opencore_release_folder / Path("EFI/BOOT/BOOTx64.efi")
        else:
            path_oc_loader = self.constants.opencore_release_folder / Path("System/Library/CoreServices/boot.efi")
        shutil.move(path_oc_loader, self.constants.opencore_release_folder / Path("System/Library/CoreServices/.diagnostics/Drivers/HardwareDrivers/Product.efi"))
        shutil.copy(self.constants.diags_launcher_path, self.constants.opencore_release_folder)
        shutil.move(self.constants.opencore_release_folder / Path("diags.efi"), self.constants.opencore_release_folder / Path("boot.efi"))