"""
start.py: 启动主机自动修补
"""

import wx
import wx.html2

import logging
import plistlib
import requests
import markdown2
import subprocess
import webbrowser


from ... import constants

from ...datasets import css_data

from ...wx_gui import (
    gui_entry,
    gui_support
)
from ...support import (
    utilities,
    updates,
    global_settings,
    network_handler,
)
from ..patchsets import (
    HardwarePatchsetDetection,
    HardwarePatchsetValidation
)


class StartAutomaticPatching:
    """
    启动主机自动修补
    """

    def __init__(self, global_constants: constants.Constants):
        self.constants: constants.Constants = global_constants


    def start_auto_patch(self):
        """
        启动自动修补

        自动修补的主要目的是告诉用户他们缺少根修补
        新用户可能不知道操作系统更新会移除我们的修补，所以我们尽量在必要时运行

        运行条件：
            - 验证正在运行GUI（TUI用户可以编写自己的脚本）
            - 验证快照封印完好（如果不完整，假设用户正在运行修补）
            - 验证此型号需要修补（如果不，假设用户升级了硬件且OCLP未被移除）
            - 验证没有OCLP更新（确保我们有最新的修补集）

        如果所有这些测试通过，启动根修补器

        """

        logging.info("- 启动自动修补")
        if self.constants.wxpython_variant is False:
            logging.info("- TUI不支持自动修补选项，请使用GUI")
            return

        dict = updates.CheckBinaryUpdates(self.constants).check_binary_updates()
        if dict:
            version = dict["Version"]
            logging.info(f"- 发现新版本: {version}")

            app = wx.App()
            mainframe = wx.Frame(None, -1, "OCLP-Mod")

            ID_GITHUB = wx.NewId()
            ID_UPDATE = wx.NewId()

            url = "https://api.github.com/repos/laobamac/OCLP-Mod/releases/latest"
            response = requests.get(url).json()
            try:
                changelog = response["body"].split("## Asset Information")[0]
            except: #如果用户不断检查更新，github将对其进行速率限制
                changelog = """## 无法获取变更日志

请查看Github页面以获取有关此版本的更多信息。"""

            html_markdown = markdown2.markdown(changelog, extras=["tables"])
            html_css = css_data.updater_css
            frame = wx.Dialog(None, -1, title="", size=(650, 500))
            frame.SetMinSize((650, 500))
            frame.SetWindowStyle(wx.STAY_ON_TOP)
            panel = wx.Panel(frame)
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.AddSpacer(10)
            self.title_text = wx.StaticText(panel, label="OCLP-Mod有新版本可用！")
            self.description = wx.StaticText(panel, label=f"OCLP-Mod {version}现已可用 - 您当前版本为 {self.constants.patcher_version}{' (Nightly)' if not self.constants.commit_info[0].startswith('refs/tags') else ''}. 您想要更新吗？")
            self.title_text.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
            self.description.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            self.web_view = wx.html2.WebView.New(panel, style=wx.BORDER_SUNKEN)
            html_code = f'''
<html>
    <head>
        <style>
            {html_css}
        </style>
    </head>
    <body class="markdown-body">
        {html_markdown.replace("<a href=", "<a target='_blank' href=")}
    </body>
</html>
'''
            self.web_view.SetPage(html_code, "")
            self.web_view.Bind(wx.html2.EVT_WEBVIEW_NEWWINDOW, self._onWebviewNav)
            self.web_view.EnableContextMenu(False)
            self.close_button = wx.Button(panel, label="忽略")
            self.close_button.Bind(wx.EVT_BUTTON, lambda event: frame.EndModal(wx.ID_CANCEL))
            self.view_button = wx.Button(panel, ID_GITHUB, label="在GitHub上查看")
            self.view_button.Bind(wx.EVT_BUTTON, lambda event: frame.EndModal(ID_GITHUB))
            self.install_button = wx.Button(panel, label="下载并安装")
            self.install_button.Bind(wx.EVT_BUTTON, lambda event: frame.EndModal(ID_UPDATE))
            self.install_button.SetDefault()

            buttonsizer = wx.BoxSizer(wx.HORIZONTAL)
            buttonsizer.Add(self.close_button, 0, wx.ALIGN_CENTRE | wx.RIGHT, 5)
            buttonsizer.Add(self.view_button, 0, wx.ALIGN_CENTRE | wx.LEFT|wx.RIGHT, 5)
            buttonsizer.Add(self.install_button, 0, wx.ALIGN_CENTRE | wx.LEFT, 5)
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(self.title_text, 0, wx.ALIGN_CENTRE | wx.TOP, 20)
            sizer.Add(self.description, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 20)
            sizer.Add(self.web_view, 1, wx.EXPAND | wx.LEFT|wx.RIGHT, 10)
            sizer.Add(buttonsizer, 0, wx.ALIGN_RIGHT | wx.ALL, 20)
            panel.SetSizer(sizer)
            frame.Centre()

            result = frame.ShowModal()


            if result == ID_GITHUB:
                webbrowser.open(dict["Github Link"])
            elif result == ID_UPDATE:
                gui_entry.EntryPoint(self.constants).start(entry=gui_entry.SupportedEntryPoints.UPDATE_APP)


            return

        if utilities.check_seal() is True:
            logging.info("- 检测到快照封印完好，检测修补")
            patches = HardwarePatchsetDetection(self.constants).device_properties
            if not any(not patch.startswith("设置") and not patch.startswith("验证") and patches[patch] is True for patch in patches):
                patches = {}
            if patches:
                logging.info("- 检测到适用的修补，确定是否可以修补")
                if patches[HardwarePatchsetValidation.PATCHING_NOT_POSSIBLE] is True:
                    logging.info("- 无法运行修补")
                    return

                logging.info("- 确定可以修补，检查OCLP更新")
                patch_string = ""
                for patch in patches:
                    if patches[patch] is True and not patch.startswith("设置") and not patch.startswith("验证"):
                        patch_string += f"- {patch}\n"

                logging.info("- 在Github上未发现新二进制文件，继续进行修补")

                warning_str = ""
                #if network_handler.NetworkUtilities("https://api.github.com/repos/laobamac/oclp-mod/releases/latest").verify_network_connection() is False:
                #    warning_str = f"""\n\n警告：我们无法验证Github上是否有OCLP-Mod的新版本。请注意，您可能正在使用一个过时的版本。如果您不确定，请在Github上验证OCLP-Mod {self.constants.patcher_version}是否为最新官方版本"""

                args = [
                    "/usr/bin/osascript",
                    "-e",
                    f"""display dialog "OCLP-Mod检测到您并没有安装驱动补丁,你想现在安装吗？\n\nmacOS每次更新都会覆盖驱动补丁（烦死了）, 以至于更新后需要重新安装。\n\n你的电脑可以安装以下补丁： \n{patch_string}\n现在开始安装驱动补丁？{warning_str}" """
                    f'with icon POSIX file "{self.constants.app_icon_path}"',
                ]
                output = subprocess.run(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT
                )
                if output.returncode == 0:
                    gui_entry.EntryPoint(self.constants).start(entry=gui_entry.SupportedEntryPoints.SYS_PATCH, start_patching=True)
                return

            else:
                logging.info("- 未检测到修补")
        else:
            logging.info("- 检测到快照封印不完整，跳过")

        if self._determine_if_versions_match():
            self._determine_if_boot_matches()


    def _onWebviewNav(self, event):
        url = event.GetURL()
        webbrowser.open(url)


    def _determine_if_versions_match(self):
        """
        确定引导的OCLP版本是否与已安装的版本匹配

        即。已安装的应用程序为0.2.0，但EFI版本为0.1.0

        返回：
            bool: 如果版本匹配则为True，否则为False
        """

        logging.info("- 检查引导版本与已安装版本")
        if self.constants.computer.oclp_version is None:
            logging.info("- 未找到引导版本")
            return True

        if self.constants.computer.oclp_version == self.constants.patcher_version:
            logging.info("- 版本匹配")
            return True

        if self.constants.special_build is True:
            # 版本不匹配且为特殊版本
            # 特殊版本没有良好的比较版本的方式
            logging.info("- 检测到特殊版本，假设已安装版本较旧")
            return False

        # 检查已安装版本是否比引导版本新
        if updates.CheckBinaryUpdates(self.constants).check_if_newer(self.constants.computer.oclp_version):
            logging.info("- 已安装版本比引导版本新")
            return True

        args = [
            "/usr/bin/osascript",
            "-e",
            f"""display dialog "OCLP-Mod检测到您正在引导{'不同的' if self.constants.special_build else '过时的'}OpenCore版本\n- 引导: {self.constants.computer.oclp_version}\n- 已安装: {self.constants.patcher_version}\n\n您想要更新OpenCore引导加载程序吗？" """
            f'with icon POSIX file "{self.constants.app_icon_path}"',
        ]
        output = subprocess.run(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        if output.returncode == 0:
            logging.info("- 启动GUI的构建/安装菜单")
            self.constants.start_build_install = True
            gui_entry.EntryPoint(self.constants).start(entry=gui_entry.SupportedEntryPoints.BUILD_OC)

        return False


    def _determine_if_boot_matches(self):
        """
        确定macOS驱动器是否与引导驱动器匹配
        即。从USB启动，但macOS位于内部磁盘

        此函数的目标是确定用户是否使用USB驱动器引导OpenCore，
        但macOS并不位于与USB相同的驱动器上。

        如果我们确定它们不匹配，则通知用户并询问他们是否想要安装到磁盘。
        """

        logging.info("- 确定macOS驱动器是否与引导驱动器匹配")

        should_notify = global_settings.GlobalEnviromentSettings().read_property("AutoPatch_Notify_Mismatched_Disks")
        if should_notify is False:
            logging.info("- 根据用户偏好跳过")
            return
        if self.constants.host_is_hackintosh is True:
            logging.info("- 跳过，因为是黑苹果")
            return
        if not self.constants.booted_oc_disk:
            logging.info("- 未能找到引导OpenCore的磁盘")
            return

        root_disk = self.constants.booted_oc_disk.strip("disk")
        root_disk = "disk" + root_disk.split("s")[0]

        logging.info(f"  - 引导驱动器: {self.constants.booted_oc_disk} ({root_disk})")
        macOS_disk = utilities.get_disk_path()
        logging.info(f"  - macOS驱动器: {macOS_disk}")
        physical_stores = utilities.find_apfs_physical_volume(macOS_disk)
        logging.info(f"  - APFS物理存储: {physical_stores}")

        disk_match = False
        for disk in physical_stores:
            if root_disk in disk:
                logging.info(f"- 引导驱动器与macOS驱动器匹配 ({disk})")
                disk_match = True
                break

        if disk_match is True:
            return

        # 检查OpenCore是否在USB驱动器上
        logging.info("- 引导驱动器与macOS驱动器不匹配，检查OpenCore是否在USB驱动器上")

        disk_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", root_disk], stdout=subprocess.PIPE).stdout)
        try:
            if disk_info["Ejectable"] is False:
                logging.info("- 引导磁盘不是可弹出的，跳过提示")
                return

            logging.info("- 引导磁盘是可弹出的，提示用户安装到内部")

            args = [
                "/usr/bin/osascript",
                "-e",
                f"""display dialog "OCLP-Mod检测到您正在从 USB 或外部驱动器启动 OpenCore。\n\n如果您想在不插入 USB 驱动器的情况下正常启动 Mac，您可以将 OpenCore 安装到内部硬盘驱动器。\n\n是否要启动OCLP-Mod并安装到硬盘？" """
                f'with icon POSIX file "{self.constants.app_icon_path}"',
            ]
            output = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT
            )
            if output.returncode == 0:
                logging.info("- 启动GUI的构建/安装菜单")
                self.constants.start_build_install = True
                gui_entry.EntryPoint(self.constants).start(entry=gui_entry.SupportedEntryPoints.BUILD_OC)

        except KeyError:
            logging.info("- 无法确定引导磁盘是否可弹出，跳过提示")