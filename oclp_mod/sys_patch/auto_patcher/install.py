"""
install.py: Install the auto patcher launch services
"""

import hashlib
import logging
import plistlib
import subprocess

from pathlib import Path

from ... import constants

from ...volume import generate_copy_arguments

from ...support import (
    utilities,
    subprocess_wrapper
)


class InstallAutomaticPatchingServices:
    """
    Install the auto patcher launch services
    """

    def __init__(self, global_constants: constants.Constants):
        self.constants: constants.Constants = global_constants


    def install_auto_patcher_launch_agent(self, kdk_caching_needed: bool = False):
        """
        Install patcher launch services

        See start_auto_patch() comments for more info
        """

        if self.constants.launcher_script is not None:
            logging.info("- 跳过自动补丁启动代理，从源代码运行时不支持")
            return

        services = {
            self.constants.auto_patch_launch_agent_path:        "/Library/LaunchAgents/com.laobamac.oclp-mod.auto-patch.plist",
            self.constants.update_launch_daemon_path:           "/Library/LaunchDaemons/com.laobamac.oclp-mod.macos-update.plist",
            **({ self.constants.rsr_monitor_launch_daemon_path: "/Library/LaunchDaemons/com.laobamac.oclp-mod.rsr-monitor.plist" } if self._create_rsr_monitor_daemon() else {}),
            **({ self.constants.kdk_launch_daemon_path:         "/Library/LaunchDaemons/com.laobamac.oclp-mod.os-caching.plist" } if kdk_caching_needed is True else {} ),
        }

        for service in services:
            name = Path(service).name
            logging.info(f"- 安装 {name}")
            if Path(services[service]).exists():
                if hashlib.sha256(open(service, "rb").read()).hexdigest() == hashlib.sha256(open(services[service], "rb").read()).hexdigest():
                    logging.info(f"  - {name} 校验和匹配，跳过")
                    continue
                logging.info(f"  - 发现现有服务，正在移除")
                subprocess_wrapper.run_as_root_and_verify(["/bin/rm", services[service]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            # 创建父目录
            if not Path(services[service]).parent.exists():
                logging.info(f"  - 创建 {Path(services[service]).parent} 目录")
                subprocess_wrapper.run_as_root_and_verify(["/bin/mkdir", "-p", Path(services[service]).parent], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            subprocess_wrapper.run_as_root_and_verify(generate_copy_arguments(service, services[service]), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            # 设置服务的权限
            subprocess_wrapper.run_as_root_and_verify(["/bin/chmod", "644", services[service]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            subprocess_wrapper.run_as_root_and_verify(["/usr/sbin/chown", "root:wheel", services[service]], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


    def _create_rsr_monitor_daemon(self) -> bool:
        # 获取 /Library/Extensions 中具有 'GPUCompanionBundles' 属性的 kext 列表
        # 这用于确定是否需要运行 RSRMonitor
        logging.info("- 检查是否需要 RSRMonitor")

        cryptex_path = f"/System/Volumes/Preboot/{utilities.get_preboot_uuid()}/cryptex1/current/OS.dmg"
        if not Path(cryptex_path).exists():
            logging.info("- 没有 OS.dmg，跳过 RSRMonitor")
            return False

        kexts = []
        for kext in Path("/Library/Extensions").glob("*.kext"):
            try:
                if not Path(f"{kext}/Contents/Info.plist").exists():
                    continue
            except Exception as e:
                logging.info(f"  - 检查 {kext.name} 是否为目录失败: {e}")
                continue
            try:
                kext_plist = plistlib.load(open(f"{kext}/Contents/Info.plist", "rb"))
            except Exception as e:
                logging.info(f"  - 加载 {kext.name} 的 plist 失败: {e}")
                continue
            if "GPUCompanionBundles" not in kext_plist:
                continue
            logging.info(f"  - 找到具有 GPUCompanionBundles 的 kext: {kext.name}")
            kexts.append(kext.name)

        # 如果没有 kext，我们不需要运行 RSRMonitor
        if not kexts:
            logging.info("- 没有找到具有 GPUCompanionBundles 的 kext，跳过 RSRMonitor")
            return False

        # 加载 RSRMonitor plist
        rsr_monitor_plist = plistlib.load(open(self.constants.rsr_monitor_launch_daemon_path, "rb"))

        arguments = ["/bin/rm", "-Rfv"]
        arguments += [f"/Library/Extensions/{kext}" for kext in kexts]

        # 将参数添加到 RSRMonitor plist
        rsr_monitor_plist["ProgramArguments"] = arguments

        # 接下来添加对 '/System/Volumes/Preboot/{UUID}/cryptex1/OS.dmg' 的监控
        logging.info(f"  - 添加监控: {cryptex_path}")
        rsr_monitor_plist["WatchPaths"] = [
            cryptex_path,
        ]

        # 写入 RSRMonitor plist
        plistlib.dump(rsr_monitor_plist, Path(self.constants.rsr_monitor_launch_daemon_path).open("wb"))

        return True