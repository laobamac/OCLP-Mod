"""
misc.py: Class for handling Misc Patches, invocation from build.py
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
    model_array,
    smbios_data,
    cpu_data,
    os_data
)


class BuildMiscellaneous:
    """
    Build Library for Miscellaneous Hardware and Software Support
xw
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
        Kick off Misc Build Process
        """

        self._feature_unlock_handling()
        self._restrict_events_handling()
        self._firewire_handling()
        self._topcase_handling()
        self._thunderbolt_handling()
        self._webcam_handling()
        self._usb_handling()
        self._debug_handling()
        self._cpu_friend_handling()
        self._general_oc_handling()
        self._t1_handling()

    def _feature_unlock_handling(self) -> None:
        """
        FeatureUnlock Handler
        """

        if self.constants.fu_status is False:
            return

        if not self.model in smbios_data.smbios_dictionary:
            return

        if smbios_data.smbios_dictionary[self.model]["Max OS Supported"] >= os_data.os_data.sonoma:
            return

        support.BuildSupport(self.model, self.constants, self.config).enable_kext("FeatureUnlock.kext", self.constants.featureunlock_version, self.constants.featureunlock_path)
        if self.constants.fu_arguments is not None and self.constants.fu_arguments != "":
            logging.info(f"- 添加额外的 FeatureUnlock 参数: {self.constants.fu_arguments}")
            self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += self.constants.fu_arguments

    def _restrict_events_handling(self) -> None:
        """
        RestrictEvents Handler
        """

        block_args = ",".join(self._re_generate_block_arguments())
        patch_args = ",".join(self._re_generate_patch_arguments())

        if block_args != "":
            logging.info(f"- 设置 RestrictEvents 阻塞参数: {block_args}")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("RestrictEvents.kext", self.constants.restrictevents_version, self.constants.restrictevents_path)
            self.config["NVRAM"]["Add"]["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"]["revblock"] = block_args

        if block_args != "" and patch_args == "":
            # 禁用不必要的用户空间修补（cs_validate_page 相当昂贵）
            patch_args = "none"

        if patch_args != "":
            logging.info(f"- 设置 RestrictEvents 修补参数: {patch_args}")
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("RestrictEvents.kext", self.constants.restrictevents_version, self.constants.restrictevents_path)
            self.config["NVRAM"]["Add"]["4D1FDA02-38C7-4A6A-9CC6-4BCCA8B30102"]["revpatch"] = patch_args

        if support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("RestrictEvents.kext")["Enabled"] is False:
            # 确保这在最后完成，以便应用所有之前的 RestrictEvents 修补
            # RestrictEvents 和 EFICheckDisabler 如果同时注入会冲突
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("EFICheckDisabler.kext", "", self.constants.efi_disabler_path)

    def _re_generate_block_arguments(self) -> list:
        """
        Generate RestrictEvents block arguments

        Returns:
            list: RestrictEvents block arguments
        """

        re_block_args = []

        # 解决 Big Sur+ 中的 GMUX 切换
        if self.model in ["MacBookPro6,1", "MacBookPro6,2", "MacBookPro9,1", "MacBookPro10,1"]:
            re_block_args.append("gmux")

        # 解决 MacPro7,1 SMBIOS 上的内存错误报告
        if self.model in model_array.MacPro:
            logging.info("- 禁用内存错误报告")
            re_block_args.append("pcie")

        # 解决 3802 GPU 上的 mediaanalysisd 崩溃
        # 适用于主要 iCloud 照片库主机系统，具有大量未处理的人脸
        if self.constants.disable_mediaanalysisd is True:
            logging.info("- 禁用 mediaanalysisd")
            re_block_args.append("media")

        return re_block_args

    def _re_generate_patch_arguments(self) -> list:
        """
        Generate RestrictEvents patch arguments

        Returns:
            list: Patch arguments
        """

        re_patch_args = []

        # kern.hv_vmm_present 修补的替代方法
        # 动态设置属性为 1，如果检测到软件更新/安装程序
        # 在安装程序/恢复环境中始终启用
        if self.constants.allow_oc_everywhere is False and (self.constants.serial_settings == "None" or self.constants.secure_status is False):
            re_patch_args.append("sbvmm")

        # 解决 macOS 13.3+ 中 Ivy Bridge 的 CoreGraphics.framework 崩溃
        # 参考: https://github.com/acidanthera/RestrictEvents/pull/12
        if smbios_data.smbios_dictionary[self.model]["CPU Generation"] == cpu_data.CPUGen.ivy_bridge.value:
            logging.info("- 修复 Ivy Bridge 的 CoreGraphics 支持")
            re_patch_args.append("f16c")

        return re_patch_args

    def _cpu_friend_handling(self) -> None:
        """
        CPUFriend Handler
        """

        if self.constants.allow_oc_everywhere is False and self.model not in ["iMac7,1", "Xserve2,1", "laobamac1,1"] and self.constants.disallow_cpufriend is False and self.constants.serial_settings != "None":
            support.BuildSupport(self.model, self.constants, self.config).enable_kext("CPUFriend.kext", self.constants.cpufriend_version, self.constants.cpufriend_path)

            # CPUFriendDataProvider 处理
            pp_map_path = Path(self.constants.platform_plugin_plist_path) / Path(f"{self.model}/Info.plist")
            if not pp_map_path.exists():
                raise Exception(f"{pp_map_path} 不存在!!! 请提出一个问题是缺少 {self.model} 的文件。")
            Path(self.constants.pp_kext_folder).mkdir()
            Path(self.constants.pp_contents_folder).mkdir()
            shutil.copy(pp_map_path, self.constants.pp_contents_folder)
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("CPUFriendDataProvider.kext")["Enabled"] = True

    def _firewire_handling(self) -> None:
        """
        FireWire Handler
        """

        if self.constants.firewire_boot is False:
            return
        if generate_smbios.check_firewire(self.model) is False:
            return

        # 启用 FireWire 引导支持
        # 适用于原生 FireWire 和 Thunderbolt 到 FireWire 适配器
        logging.info("- 启用 FireWire 引导支持")
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOFireWireFamily.kext", self.constants.fw_kext, self.constants.fw_family_path)
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOFireWireSBP2.kext", self.constants.fw_kext, self.constants.fw_sbp2_path)
        support.BuildSupport(self.model, self.constants, self.config).enable_kext("IOFireWireSerialBusProtocolTransport.kext", self.constants.fw_kext, self.constants.fw_bus_path)
        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("IOFireWireFamily.kext/Contents/PlugIns/AppleFWOHCI.kext")["Enabled"] = True

    def _topcase_handling(self) -> None:
        """
        USB/SPI Top Case Handler
        """

        # macOS 14.4 Beta 1 剥离 Broadwell 到 Kaby Lake MacBook（以及 MacBookAir6,x）的 SPI 基础顶盖支持
        if self.model.startswith("MacBook") and self.model in smbios_data.smbios_dictionary:
            if self.model.startswith("MacBookAir6") or (cpu_data.CPUGen.broadwell <= smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.kaby_lake):
                logging.info("- 启用 SPI 基础顶盖支持")
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleHSSPISupport.kext", self.constants.apple_spi_version, self.constants.apple_spi_path)
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleHSSPIHIDDriver.kext", self.constants.apple_spi_hid_version, self.constants.apple_spi_hid_path)
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleTopCaseInjector.kext", self.constants.topcase_inj_version, self.constants.top_case_inj_path)

        # 设备内探测
        if not self.constants.custom_model and self.computer.internal_keyboard_type and self.computer.trackpad_type:

            support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTopCase.kext", self.constants.topcase_version, self.constants.top_case_path)
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCButtons.kext")["Enabled"] = True
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyboard.kext")["Enabled"] = True
            support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyEventDriver.kext")["Enabled"] = True

            if self.computer.internal_keyboard_type == "Legacy":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("LegacyKeyboardInjector.kext", self.constants.legacy_keyboard, self.constants.legacy_keyboard_path)
            if self.computer.trackpad_type == "Legacy":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTrackpad.kext", self.constants.apple_trackpad, self.constants.apple_trackpad_path)
            elif self.computer.trackpad_type == "Modern":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBMultitouch.kext", self.constants.multitouch_version, self.constants.multitouch_path)

        # 预定义回退
        else:
            # macOS Ventura+ 的多点触控顶盖支持
            if smbios_data.smbios_dictionary[self.model]["CPU Generation"] < cpu_data.CPUGen.skylake.value:
                if self.model.startswith("MacBook"):
                    # 这些单位有 Force Touch 顶盖，因此忽略它们
                    if self.model not in ["MacBookPro11,4", "MacBookPro11,5", "MacBookPro12,1", "MacBook8,1"]:
                        support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTopCase.kext", self.constants.topcase_version, self.constants.top_case_path)
                        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCButtons.kext")["Enabled"] = True
                        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyboard.kext")["Enabled"] = True
                        support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("AppleUSBTopCase.kext/Contents/PlugIns/AppleUSBTCKeyEventDriver.kext")["Enabled"] = True
                        support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBMultitouch.kext", self.constants.multitouch_version, self.constants.multitouch_path)

            # macOS High Sierra+ 的两指顶盖支持
            if self.model == "MacBook5,2":
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleUSBTrackpad.kext", self.constants.apple_trackpad, self.constants.apple_trackpad_path) # 也需要 AppleUSBTopCase.kext
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("LegacyKeyboardInjector.kext", self.constants.legacy_keyboard, self.constants.legacy_keyboard_path) # 将旧版个人资料注入 AppleUSBTCKeyboard 和 AppleUSBTCKeyEventDriver

    def _thunderbolt_handling(self) -> None:
        """
        Thunderbolt Handler
        """

        if self.constants.disable_tb is True and self.model in ["MacBookPro11,1", "MacBookPro11,2", "MacBookPro11,3", "MacBookPro11,4", "MacBookPro11,5"]:
            logging.info("- 禁用 2013-2014 笔记本 Thunderbolt 控制器")
            if self.model in ["MacBookPro11,3", "MacBookPro11,5"]:
                # 15" dGPU 模型: IOACPIPlane:/_SB/PCI0@0/PEG1@10001/UPSB@0/DSB0@0/NHI0@0
                tb_device_path = "PciRoot(0x0)/Pci(0x1,0x1)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)"
            else:
                # 13" 和 15" iGPU 2013-2014 模型: IOACPIPlane:/_SB/PCI0@0/P0P2@10000/UPSB@0/DSB0@0/NHI0@0
                tb_device_path = "PciRoot(0x0)/Pci(0x1,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)"

            self.config["DeviceProperties"]["Add"][tb_device_path] = {"class-code": binascii.unhexlify("FFFFFFFF"), "device-id": binascii.unhexlify("FFFF0000")}
    def _webcam_handling(self) -> None:
        """
        iSight Handler
        """
        if self.model in smbios_data.smbios_dictionary:
            if "Legacy iSight" in smbios_data.smbios_dictionary[self.model]:
                if smbios_data.smbios_dictionary[self.model]["Legacy iSight"] is True:
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("LegacyUSBVideoSupport.kext", self.constants.apple_isight_version, self.constants.apple_isight_path)

        if not self.constants.custom_model:
            if self.constants.computer.pcie_webcam is True:
                support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleCameraInterface.kext", self.constants.apple_camera_version, self.constants.apple_camera_path)
        else:
            if self.model.startswith("MacBook") and self.model in smbios_data.smbios_dictionary:
                if cpu_data.CPUGen.haswell <= smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.kaby_lake:
                    support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleCameraInterface.kext", self.constants.apple_camera_version, self.constants.apple_camera_path)

    def _usb_handling(self) -> None:
       """
       USB Handler
       """

       # USB Map
       usb_map_path = Path(self.constants.plist_folder_path) / Path("AppleUSBMaps/Info.plist")
       usb_map_tahoe_path = Path(self.constants.plist_folder_path) / Path("AppleUSBMaps/Info-Tahoe.plist")
       if (
           usb_map_path.exists()
           and (self.constants.allow_oc_everywhere is False or self.constants.allow_native_spoofs is True)
           and self.model not in ["Xserve2,1", "laobamac1,1"]
           and (
               (self.model in model_array.Missing_USB_Map or self.model in model_array.Missing_USB_Map_Ventura)
               or self.constants.serial_settings in ["Moderate", "Advanced"])
       ):
           logging.info("正在添加 USB-Map.kext 和 USB-Map-Tahoe.kext")
           Path(self.constants.map_kext_folder).mkdir()
           Path(self.constants.map_kext_folder_tahoe).mkdir()
           Path(self.constants.map_contents_folder).mkdir()
           Path(self.constants.map_contents_folder_tahoe).mkdir()
           shutil.copy(usb_map_path, self.constants.map_contents_folder)
           shutil.copy(usb_map_tahoe_path, self.constants.map_contents_folder_tahoe / Path("Info.plist"))
           support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map.kext")["Enabled"] = True
           support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map-Tahoe.kext")["Enabled"] = True
           if self.model in model_array.Missing_USB_Map_Ventura and self.constants.serial_settings not in ["Moderate", "Advanced"]:
               support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB-Map.kext")["MinKernel"] = "22.0.0"

       # Add UHCI/OHCI drivers
       # All Penryn Macs lack an internal USB hub to route USB 1.1 devices to the EHCI controller
       # And MacPro4,1, MacPro5,1 and Xserve3,1 are the only post-Penryn Macs that lack an internal USB hub
       # - Ref: https://techcommunity.microsoft.com/t5/microsoft-usb-blog/reasons-to-avoid-companion-controllers/ba-p/270710
       #
       # To be paired for usb11.py's 'Legacy USB 1.1' patchset
       #
       # Note: With macOS 14.1, injection of these kexts causes a panic.
       #       To avoid this, a MaxKernel is configured with XNU 23.0.0 (macOS 14.0).
       #       Additionally sys_patch.py stack will now patches the bins onto disk for 14.1+.
       #       Reason for keeping the dual logic is due to potential conflicts of in-cache vs injection if we start
       #       patching pre-14.1 hosts.
       if (
           smbios_data.smbios_dictionary[self.model]["CPU Generation"] <= cpu_data.CPUGen.penryn.value or \
           self.model in ["MacPro4,1", "MacPro5,1", "Xserve3,1"]
       ):
           logging.info("正在添加 UHCI/OHCI USB 支持")
           shutil.copy(self.constants.apple_usb_11_injector_path, self.constants.kexts_path)
           support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBOHCI.kext")["Enabled"] = True
           support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBOHCIPCI.kext")["Enabled"] = True
           support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBUHCI.kext")["Enabled"] = True
           support.BuildSupport(self.model, self.constants, self.config).get_kext_by_bundle_path("USB1.1-Injector.kext/Contents/PlugIns/AppleUSBUHCIPCI.kext")["Enabled"] = True


    def _debug_handling(self) -> None:
       """
       Debug Handler for OpenCorePkg and Kernel Space
       """

       if self.constants.verbose_debug is True:
           logging.info("正在启用详细启动")
           self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -v"

       if self.constants.kext_debug is True:
           logging.info("正在启用 DEBUG Kexts")
           self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " -liludbgall liludump=90"
           # Disabled due to macOS Monterey crashing shortly after kernel init
           # Use DebugEnhancer.kext instead
           # self.config["NVRAM"]["Add"]["7C436110-AB2A-4BBB-A880-FE41995C9F82"]["boot-args"] += " msgbuf=1048576"
           support.BuildSupport(self.model, self.constants, self.config).enable_kext("DebugEnhancer.kext", self.constants.debugenhancer_version, self.constants.debugenhancer_path)

       if self.constants.opencore_debug is True:
           logging.info("正在启用 DEBUG OpenCore")
           self.config["Misc"]["Debug"]["Target"] = 0x43
           self.config["Misc"]["Debug"]["DisplayLevel"] = 0x80000042


    def _general_oc_handling(self) -> None:
       """
       General OpenCorePkg Handler
       """

       logging.info("正在添加 OpenCanopy GUI")
       shutil.copy(self.constants.gui_path, self.constants.oc_folder)
       support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("OpenCanopy.efi", "UEFI", "Drivers")["Enabled"] = True
       support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("OpenRuntime.efi", "UEFI", "Drivers")["Enabled"] = True
       support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("OpenLinuxBoot.efi", "UEFI", "Drivers")["Enabled"] = True
       support.BuildSupport(self.model, self.constants, self.config).get_efi_binary_by_path("ResetNvramEntry.efi", "UEFI", "Drivers")["Enabled"] = True

       if self.constants.showpicker is False:
           logging.info("正在隐藏 OpenCore 启动选择器")
           self.config["Misc"]["Boot"]["ShowPicker"] = False

       if self.constants.oc_timeout != 5:
           logging.info(f"正在设置自定义 OpenCore 启动选择器超时时间为 {self.constants.oc_timeout} 秒")
           self.config["Misc"]["Boot"]["Timeout"] = self.constants.oc_timeout

       if self.constants.vault is True:
           logging.info("正在设置 Vault 配置")
           self.config["Misc"]["Security"]["Vault"] = "Secure"

    def _t1_handling(self) -> None:
       """
       T1 Security Chip Handler
       """
       if self.model not in ["MacBookPro13,2", "MacBookPro13,3", "MacBookPro14,2", "MacBookPro14,3"]:
           return

       logging.info("正在启用 T1 安全芯片支持")

       support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Block"], "Identifier", "com.apple.driver.AppleSSE")["Enabled"] = True
       support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Block"], "Identifier", "com.apple.driver.AppleKeyStore")["Enabled"] = True
       support.BuildSupport(self.model, self.constants, self.config).get_item_by_kv(self.config["Kernel"]["Block"], "Identifier", "com.apple.driver.AppleCredentialManager")["Enabled"] = True

       support.BuildSupport(self.model, self.constants, self.config).enable_kext("corecrypto_T1.kext", self.constants.t1_corecrypto_version, self.constants.t1_corecrypto_path)
       support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleSSE.kext", self.constants.t1_sse_version, self.constants.t1_sse_path)
       support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleKeyStore.kext", self.constants.t1_key_store_version, self.constants.t1_key_store_path)
       support.BuildSupport(self.model, self.constants, self.config).enable_kext("AppleCredentialManager.kext", self.constants.t1_credential_version, self.constants.t1_credential_path)
       support.BuildSupport(self.model, self.constants, self.config).enable_kext("KernelRelayHost.kext", self.constants.kernel_relay_version, self.constants.kernel_relay_path)