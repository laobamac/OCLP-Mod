"""
macos_installer_handler.py: Handler for local macOS installers
"""

import logging
import plistlib
import tempfile
import subprocess
import re

from pathlib import Path

from ..datasets import os_data

from . import (
    utilities,
    subprocess_wrapper
)

from ..volume import (
    can_copy_on_write,
    generate_copy_arguments
)


APPLICATION_SEARCH_PATH:  str = "/Applications"

tmp_dir = tempfile.TemporaryDirectory()


class InstallerCreation():

    def __init__(self) -> None:
        pass


    def install_macOS_installer(self, download_path: str) -> bool:
        """
        Installs InstallAssistant.pkg

        Parameters:
            download_path (str): Path to InstallAssistant.pkg

        Returns:
            bool: True if successful, False otherwise
        """

        logging.info("从 InstallAssistant.pkg 提取 macOS 安装程序")
        result = subprocess_wrapper.run_as_root(["/usr/sbin/installer", "-pkg", f"{Path(download_path)}/InstallAssistant.pkg", "-target", "/"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logging.info("安装 InstallAssistant 失败")
            subprocess_wrapper.log(result)
            return False

        logging.info("InstallAssistant 已安装")
        return True


    def generate_installer_creation_script(self, tmp_location: str, installer_path: str, disk: str) -> bool:
        """
        创建要传递给 OCLP-Helper 并以管理员身份运行的 installer.sh

        脚本包括：
        - 将提供的磁盘格式化为 HFS+ GPT
        - 在提供的磁盘上运行 createinstallmedia

        将此实现为单个 installer.sh 脚本允许我们只需调用 OCLP-Helper 一次，以避免不断提示用户权限

        Parameters:
            tmp_location (str): 临时目录路径
            installer_path (str): InstallAssistant.pkg 路径
            disk (str): 要安装的磁盘

        Returns:
            bool: 如果成功则为 True，否则为 False
        """

        additional_args = ""
        script_location = Path(tmp_location) / Path("Installer.sh")

        # 由于 createinstallmedia 中存在一个错误，在 '/Applications' 运行时可能会出错：
        #   'Failed to extract AssetData/boot/Firmware/Manifests/InstallerBoot/*'
        # 这会影响原生 Mac 电脑，即使手动调用 createinstallmedia 也是如此

        # 为了解决这个问题，我们将复制到我们的临时目录并从那里运行

        # 创建一个新的临时目录
        # 我们的当前目录是一个磁盘镜像，因此 CoW 不会生效
        global tmp_dir
        ia_tmp = tmp_dir.name

        logging.info(f"在 {ia_tmp} 创建临时目录")
        # 删除 tmp_dir 中的所有文件
        for file in Path(ia_tmp).glob("*"):
            subprocess.run(["/bin/rm", "-rf", str(file)])

        # 将安装程序复制到临时目录
        if can_copy_on_write(installer_path, ia_tmp) is False:
            # 确保在不支持 CoW 的情况下有足够的空间进行复制
            space_available = utilities.get_free_space()
            space_needed = Path(ia_tmp).stat().st_size
            if space_available < space_needed:
                logging.info("没有足够的可用空间创建 installer.sh")
                logging.info(f"{utilities.human_fmt(space_available)} 可用, {utilities.human_fmt(space_needed)} 所需")
                return False

        subprocess.run(generate_copy_arguments(installer_path, ia_tmp))

        # 调整 installer_path 指向复制的安装程序
        installer_path = Path(ia_tmp) / Path(Path(installer_path).name)
        if not Path(installer_path).exists():
            logging.info(f"无法将安装程序复制到 {ia_tmp}")
            return False

        # 在执行前验证代码签名
        createinstallmedia_path = str(Path(installer_path) / Path("Contents/Resources/createinstallmedia"))
        if subprocess.run(["/usr/bin/codesign", "-v", "-R=anchor apple", createinstallmedia_path]).returncode != 0:
            logging.info(f"安装程序的代码签名已损坏")
            return False

        plist_path = str(Path(installer_path) / Path("Contents/Info.plist"))
        if Path(plist_path).exists():
            plist = plistlib.load(Path(plist_path).open("rb"))
            if "DTPlatformVersion" in plist:
                platform_version = plist["DTPlatformVersion"]
                platform_version = platform_version.split(".")[0]
                if platform_version[0] == "10":
                    if int(platform_version[1]) < 13:
                        additional_args = f" --applicationpath '{installer_path}'"

        if script_location.exists():
            script_location.unlink()
        script_location.touch()

        with script_location.open("w") as script:
            script.write(f'''#!/bin/bash
erase_disk='/usr/sbin/diskutil eraseDisk HFS+ OCLP-Installer {disk}'
if $erase_disk; then
    "{createinstallmedia_path}" --volume /Volumes/OCLP-Installer --nointeraction{additional_args}
fi
            ''')
        if Path(script_location).exists():
            return True
        return False


    def list_disk_to_format(self) -> dict:
        """
        列出适用于 macOS 安装程序创建的磁盘
        仅列出以下磁盘：
        - 14GB 或更大
        - 外部

        当前限制：
        - 不支持基于 PCIe 的 SD 卡读卡器

        Returns:
            dict: 磁盘字典
        """

        all_disks:  dict = {}
        list_disks: dict = {}

        # TODO: AllDisksAndPartitions 在 Snow Leopard 及更早版本中不受支持
        try:
            # High Sierra 及更新版本
            disks = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "list", "-plist", "physical"], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        except ValueError:
            # Sierra 及更早版本
            disks = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "list", "-plist"], stdout=subprocess.PIPE).stdout.decode().strip().encode())

        for disk in disks["AllDisksAndPartitions"]:
            try:
                disk_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", disk["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip().encode())
            except:
                # Chinesium USB 可能在 MediaName 中有垃圾数据
                diskutil_output = subprocess.run(["/usr/sbin/diskutil", "info", "-plist", disk["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip()
                ungarbafied_output = re.sub(r'(<key>MediaName</key>\s*<string>).*?(</string>)', r'\1\2', diskutil_output).encode()
                disk_info = plistlib.loads(ungarbafied_output)
            try:
                all_disks[disk["DeviceIdentifier"]] = {"identifier": disk_info["DeviceNode"], "name": disk_info.get("MediaName", "Disk"), "size": disk_info["TotalSize"], "removable": disk_info["Internal"], "partitions": {}}
            except KeyError:
                # 避免安装 CD 时崩溃
                continue

        for disk in all_disks:
            # 剔除小于 14GB（15,032,385,536 字节）的磁盘
            # createinstallmedia 在检测磁盘是否有足够空间方面不是很好
            if not any(all_disks[disk]['size'] > 15032385536 for partition in all_disks[disk]):
                continue
            # 剔除内部磁盘（避免用户格式化他们的 SSD/HDD）
            # 确保用户不会格式化他们的启动驱动器
            if not any(all_disks[disk]['removable'] is False for partition in all_disks[disk]):
                continue

            list_disks.update({
                disk: {
                    "identifier": all_disks[disk]["identifier"],
                    "name": all_disks[disk]["name"],
                    "size": all_disks[disk]["size"],
                }
            })

        return list_disks


class LocalInstallerCatalog:
    """
    查找本地机器上的所有 macOS 安装程序。
    """

    def __init__(self) -> None:
        self.available_apps: dict = self._list_local_macOS_installers()


    def _list_local_macOS_installers(self) -> dict:
        """
        在 /Applications 中搜索 macOS 安装程序

        Returns:
            dict: 包含本地机器上找到的 macOS 安装程序的字典。

            示例：
                "Install macOS Big Sur Beta.app": {
                    "Short Name": "Big Sur Beta",
                    "Version": "11.0",
                    "Build": "20A5343i",
                    "Path": "/Applications/Install macOS Big Sur Beta.app",
                },
                等等...
        """

        application_list: dict = {}

        for application in Path(APPLICATION_SEARCH_PATH).iterdir():
            # 某些 Microsoft 应用程序具有奇怪的权限，阻止我们读取它们
            try:
                if not (Path(APPLICATION_SEARCH_PATH) / Path(application) / Path("Contents/Resources/createinstallmedia")).exists():
                    continue

                if not (Path(APPLICATION_SEARCH_PATH) / Path(application) / Path("Contents/Info.plist")).exists():
                    continue
            except PermissionError:
                continue

            try:
                application_info_plist = plistlib.load((Path(APPLICATION_SEARCH_PATH) / Path(application) / Path("Contents/Info.plist")).open("rb"))
            except (PermissionError, TypeError, plistlib.InvalidFileException):
                continue

            if "DTPlatformVersion" not in application_info_plist:
                continue
            if "CFBundleDisplayName" not in application_info_plist:
                continue

            app_version:  str = application_info_plist["DTPlatformVersion"]
            clean_name:   str = application_info_plist["CFBundleDisplayName"]
            app_sdk:      str = application_info_plist["DTSDKBuild"] if "DTSDKBuild" in application_info_plist else "Unknown"
            min_required: str = application_info_plist["LSMinimumSystemVersion"] if "LSMinimumSystemVersion" in application_info_plist else "Unknown"

            kernel:       int = 0
            try:
                kernel = int(app_sdk[:2])
            except ValueError:
                pass

            min_required = os_data.os_conversion.os_to_kernel(min_required) if min_required != "Unknown" else 0

            if min_required == os_data.os_data.sierra and kernel == os_data.os_data.ventura:
                # Ventura 的安装程序要求最低为 El Capitan
                # 参考: https://github.com/laobamac/oclp-mod/discussions/1038
                min_required = os_data.os_data.el_capitan

            # app_version 有时会报告 GM 而不是实际版本
            # 这是一个解决方法来获取实际版本
            if app_version.startswith("GM"):
                if kernel == 0:
                    app_version = "Unknown"
                else:
                    app_version = os_data.os_conversion.kernel_to_os(kernel)

            # 检查应用程序版本是否为 High Sierra 或更高版本
            if kernel < os_data.os_data.high_sierra:
                continue

            results = self._parse_sharedsupport_version(Path(APPLICATION_SEARCH_PATH) / Path(application)/ Path("Contents/SharedSupport/SharedSupport.dmg"))
            if results[0] is not None:
                app_sdk = results[0]
            if results[1] is not None:
                app_version = results[1]

            application_list.update({
                application: {
                    "Short Name": clean_name,
                    "Version": app_version,
                    "Build": app_sdk,
                    "Path": application,
                    "Minimum Host OS": min_required,
                    "OS": kernel
                }
            })

        # 按版本对应用程序进行排序
        application_list = {k: v for k, v in sorted(application_list.items(), key=lambda item: item[1]["Version"])}
        return application_list


    def _parse_sharedsupport_version(self, sharedsupport_path: Path) -> tuple:
        """
        通过解析 SharedSupport.dmg 确定 macOS 安装程序的真实版本
        这是必需的，因为 Info.plist 报告的是应用程序版本而不是操作系统版本

        Parameters:
            sharedsupport_path (Path): SharedSupport.dmg 路径

        Returns:
            tuple: 包含构建和操作系统版本的元组
        """

        detected_build: str = None
        detected_os:    str = None

        if not sharedsupport_path.exists():
            return (detected_build, detected_os)

        if not sharedsupport_path.name.endswith(".dmg"):
            return (detected_build, detected_os)


        # 创建临时目录以提取 SharedSupport.dmg
        with tempfile.TemporaryDirectory() as tmpdir:

            output = subprocess.run(
                [
                    "/usr/bin/hdiutil", "attach", "-noverify", sharedsupport_path,
                    "-mountpoint", tmpdir,
                    "-nobrowse",
                ],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )

            if output.returncode != 0:
                return (detected_build, detected_os)


            ss_info_files = [
                Path("SFR/com_apple_MobileAsset_SFRSoftwareUpdate/com_apple_MobileAsset_SFRSoftwareUpdate.xml"),
                Path("com_apple_MobileAsset_MacSoftwareUpdate/com_apple_MobileAsset_MacSoftwareUpdate.xml")
            ]

            for ss_info in ss_info_files:
                if not Path(tmpdir / ss_info).exists():
                    continue
                plist = plistlib.load((tmpdir / ss_info).open("rb"))
                if "Assets" in plist:
                    if "Build" in plist["Assets"][0]:
                        detected_build = plist["Assets"][0]["Build"]
                    if "OSVersion" in plist["Assets"][0]:
                        detected_os = plist["Assets"][0]["OSVersion"]

            # 卸载 SharedSupport.dmg
            subprocess.run(["/usr/bin/hdiutil", "detach", tmpdir], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        return (detected_build, detected_os)