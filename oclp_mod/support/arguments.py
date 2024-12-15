"""
arguments.py: CLI argument handling
"""

import sys
import time
import logging
import plistlib
import threading
import subprocess

from pathlib import Path

from . import subprocess_wrapper

from .. import constants

from ..wx_gui import gui_entry
from ..efi_builder import build
from ..sys_patch import sys_patch
from ..sys_patch.auto_patcher import StartAutomaticPatching

from ..datasets import (
    model_array,
    os_data
)

from . import (
    utilities,
    defaults,
    validation
)



# Generic building args
class arguments:

    def __init__(self, global_constants: constants.Constants) -> None:
        self.constants: constants.Constants = global_constants

        self.args = utilities.check_cli_args()

        self._parse_arguments()


    def _parse_arguments(self) -> None:
        """
        Parses arguments passed to the patcher
        """

        if self.args.validate:
            self._validation_handler()
            return

        if self.args.build:
            self._build_handler()
            return

        if self.args.patch_sys_vol:
            self._sys_patch_handler()
            return

        if self.args.unpatch_sys_vol:
            self._sys_unpatch_handler()
            return

        if self.args.prepare_for_update:
            self._prepare_for_update_handler()
            return

        if self.args.cache_os:
            self._cache_os_handler()
            return

        if self.args.auto_patch:
            self._sys_patch_auto_handler()
            return
    def _validation_handler(self) -> None:
        """
        进入验证模式
        """
        logging.info("设置验证模式")
        validation.PatcherValidation(self.constants)


    def _sys_patch_handler(self) -> None:
        """
        开始根卷修补
        """

        logging.info("设置系统卷修补")
        if "Library/InstallerSandboxes/" in str(self.constants.payload_path):
            logging.info("- 从安装沙盒运行，阻止操作系统更新程序")
            thread = threading.Thread(target=sys_patch.PatchSysVolume(self.constants.custom_model or self.constants.computer.real_model, self.constants, None).start_patch)
            thread.start()
            while thread.is_alive():
                utilities.block_os_updaters()
                time.sleep(1)
        else:
            sys_patch.PatchSysVolume(self.constants.custom_model or self.constants.computer.real_model, self.constants, None).start_patch()


    def _sys_unpatch_handler(self) -> None:
        """
        开始根卷取消修补
        """
        logging.info("设置系统卷取消修补")
        sys_patch.PatchSysVolume(self.constants.custom_model or self.constants.computer.real_model, self.constants, None).start_unpatch()


    def _sys_patch_auto_handler(self) -> None:
        """
        开始根卷自动修补
        """

        logging.info("设置自动修补")
        StartAutomaticPatching(self.constants).start_auto_patch()


    def _prepare_for_update_handler(self) -> None:
        """
        准备主机进行macOS更新
        """
        logging.info("准备主机进行macOS更新")

        os_data = utilities.fetch_staged_update(variant="Update")
        if os_data[0] is None:
            logging.info("没有计划中的更新，跳过")
            return

        os_version = os_data[0]
        os_build   = os_data[1]

        logging.info(f"准备更新到 {os_version} ({os_build})")

        self._clean_le_handler()


    def _cache_os_handler(self) -> None:
        """
        获取即将安装的OS的KDK
        """
        results = subprocess.run(["/bin/ps", "-ax"], stdout=subprocess.PIPE)
        if results.stdout.decode("utf-8").count("OCLP-Mod --cache_os") > 1:
            logging.info("另一个OS缓存实例正在运行，退出")
            return

        gui_entry.EntryPoint(self.constants).start(entry=gui_entry.SupportedEntryPoints.OS_CACHE)


    def _clean_le_handler(self) -> None:
        """
        清理/Library/Extensions中的有问题的kext
        注意macOS Ventura及更早版本会自动执行此操作
        """

        if self.constants.detected_os < os_data.os_data.sonoma:
            return

        logging.info("清理/Library/Extensions")

        for kext in Path("/Library/Extensions").glob("*.kext"):
            if not Path(f"{kext}/Contents/Info.plist").exists():
                continue
            try:
                kext_plist = plistlib.load(open(f"{kext}/Contents/Info.plist", "rb"))
            except Exception as e:
                logging.info(f"  - 无法加载{kext.name}的plist: {e}")
                continue
            if "GPUCompanionBundles" not in kext_plist:
                continue
            logging.info(f"  - 移除{kext.name}")
            subprocess_wrapper.run_as_root(["/bin/rm", "-rf", kext])


    def _build_handler(self) -> None:
        """
        开始配置构建过程
        """
        logging.info("设置OpenCore构建")

        if self.args.model:
            if self.args.model:
                logging.info(f"- 使用自定义型号: {self.args.model}")
                self.constants.custom_model = self.args.model
                defaults.GenerateDefaults(self.constants.custom_model, False, self.constants)
            elif self.constants.computer.real_model not in model_array.SupportedSMBIOS and self.constants.allow_oc_everywhere is False:
                logging.info(
                    """您的型号不支持此补丁程序以运行不受支持的操作系统！

如果您打算为另一台机器创建USB，请在菜单中选择“更改型号”选项。"""
                )
                sys.exit(1)
            else:
                logging.info(f"- 使用检测到的型号: {self.constants.computer.real_model}")
                defaults.GenerateDefaults(self.constants.custom_model, True, self.constants)

        if self.args.verbose:
            logging.info("- 设置详细配置")
            self.constants.verbose_debug = True
        else:
            self.constants.verbose_debug = False  # 覆盖默认检测

        if self.args.debug_oc:
            logging.info("- 设置OpenCore调试配置")
            self.constants.opencore_debug = True

        if self.args.debug_kext:
            logging.info("- 设置kext调试配置")
            self.constants.kext_debug = True

        if self.args.hide_picker:
            logging.info("- 设置隐藏启动选择器配置")
            self.constants.showpicker = False

        if self.args.disable_sip:
            logging.info("- 设置禁用SIP配置")
            self.constants.sip_status = False
        else:
            self.constants.sip_status = True  # 覆盖默认检测

        if self.args.disable_smb:
            logging.info("- 设置禁用安全启动模型配置")
            self.constants.secure_status = False
        else:
            self.constants.secure_status = True  # 覆盖默认检测

        if self.args.vault:
            logging.info("- 设置Vault配置")
            self.constants.vault = True

        if self.args.firewire:
            logging.info("- 设置FireWire启动配置")
            self.constants.firewire_boot = True

        if self.args.nvme:
            logging.info("- 设置NVMe启动配置")
            self.constants.nvme_boot = True

        if self.args.wlan:
            logging.info("- 设置Wake on WLAN配置")
            self.constants.enable_wake_on_wlan = True

        if self.args.disable_tb:
            logging.info("- 设置禁用Thunderbolt配置")
            self.constants.disable_tb = True

        if self.args.force_surplus:
            logging.info("- 强制SurPlus覆盖配置")
            self.constants.force_surplus = True

        if self.args.moderate_smbios:
            logging.info("- 设置中度SMBIOS修补配置")
            self.constants.serial_settings = "Moderate"

        if self.args.smbios_spoof:
            if self.args.smbios_spoof == "Minimal":
                self.constants.serial_settings = "Minimal"
            elif self.args.smbios_spoof == "Moderate":
                self.constants.serial_settings = "Moderate"
            elif self.args.smbios_spoof == "Advanced":
                self.constants.serial_settings = "Advanced"
            else:
                logging.info(f"- 传递了未知的SMBIOS参数: {self.args.smbios_spoof}")

        if self.args.support_all:
            logging.info("- 为原生支持的型号构建")
            self.constants.allow_oc_everywhere = True
            self.constants.serial_settings = "None"

        build.BuildOpenCore(self.constants.custom_model or self.constants.computer.real_model, self.constants)