"""
gui_main_menu.py: Generate GUI for main menu
"""

import wx
import wx.html2

import sys
import logging
import requests
import markdown2
import threading
import webbrowser

from .. import constants

from ..support import (
    global_settings,
    updates
)
from ..datasets import (
    os_data,
    css_data
)
from ..wx_gui import (
    gui_build,
    gui_macos_installer_download,
    gui_support,
    gui_help,
    gui_settings,
    gui_sys_patch_display,
    gui_update,
    gui_kdk_dl,
    gui_ml_dl,
)


class MainFrame(wx.Frame):
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None):
        logging.info("Initializing Main Menu Frame")
        super(MainFrame, self).__init__(parent, title=title, size=(600, 400), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, global_constants).generate()

        self.constants: constants.Constants = global_constants
        self.title: str = title

        self.model_label: wx.StaticText = None
        self.build_button: wx.Button = None

        self.constants.update_stage = gui_support.AutoUpdateStages.INACTIVE

        self._generate_elements()

        self.Centre()
        self.Show()


        self._preflight_checks()


    def _generate_elements(self) -> None:
        """
        Generate UI elements for the main menu

        Format:
          - Title label: OCLP Modified By laobamac v{X.Y.Z}
          - Text:        Model: {Build or Host Model}
          - Buttons:
            - Build and Install OpenCore
            - Post-Install Root Patch
            - Create macOS Installer
            - Settings
            - Help
          - Text:        Copyright
        """

        # Title label: OCLP-Mod v{X.Y.Z}
        title_label = wx.StaticText(self, label=f"OCLP Modified By laobamac {'' if self.constants.special_build else ''}{self.constants.patcher_version}{'' if not self.constants.commit_info[0].startswith('refs/tags') else ''}", pos=(-1, 10))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Text: Model: {Build or Host Model}
        model_label = wx.StaticText(self, label=f"型号: {self.constants.custom_model or self.constants.computer.real_model} ，modified by laobamac", pos=(-1, title_label.GetPosition()[1] + 25
                                                                                                                                    ))
        model_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        model_label.Centre(wx.HORIZONTAL)
        self.model_label = model_label

        # Buttons:
        menu_buttons = {
            "创建OpenCore引导": {
                "function": self.on_build_and_install,
                "description": [
                    "提供额外的引导",
                    "来启动高版本的系统",
                    "需要使用.app或者其他安装器"
                ],
                "icon": str(self.constants.icns_resource_path / "OC-Build.icns"),
            },
            "创建macOS安装器": {
                "function": self.on_create_macos_installer,
                "description": [
                    "下载/烧录macOS安装器",
                    "安装新macOS使用.",
                ],
                "icon": str(self.constants.icns_resource_path / "OC-Installer.icns"),
            },
            "⚙️ 设置": {
                "function": self.on_settings,
                "description": [
                ],
            },
            "安装驱动补丁": {
                "function": self.on_post_install_root_patch,
                "description": [
                    "安装硬件驱动补丁",
                    "（在安装新版本macOS后",
                    "进入系统再打）",
                ],
                "icon": str(self.constants.icns_resource_path / "OC-Patch.icns"),
            },

            "获取支持": {
                "function": self.on_help,
                "description": [
                    "OCLP相关资源",
                    "由laobamac汉化",
                ],
                "icon": str(self.constants.icns_resource_path / "OC-Support.icns"),
            },
        }
        button_x = 30
        button_y = model_label.GetPosition()[1] + 30
        rollover = len(menu_buttons) / 2
        if rollover % 1 != 0:
            rollover = int(rollover) + 1
        index = 0
        max_height = 0
        for button_name, button_function in menu_buttons.items():
            # place icon
            if "icon" in button_function:
                icon = wx.StaticBitmap(self, bitmap=wx.Bitmap(button_function["icon"], wx.BITMAP_TYPE_ICON), pos=(button_x - 10, button_y), size=(64, 64))
                if button_name == "安装驱动补丁":
                    icon.SetPosition((-1, button_y + 7))
                if button_name == "创建macOS安装器":
                    icon.SetPosition((button_x - 5, button_y + 3))
                if button_name == "获取支持":
                    # icon_mac.SetSize((80, 80))
                    icon.SetPosition((button_x - 7, button_y + 3))
                if button_name == "创建OpenCore引导":
                    icon.SetSize((70, 70))
            if button_name == "⚙️ 设置":
                button_y += 5
                button_x += 150

            button = wx.Button(self, label=button_name, pos=(button_x + 70, button_y), size=(180, 30))
            button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            button.Bind(wx.EVT_BUTTON, lambda event, function=button_function["function"]: function(event))
            button_y += 30

            # # Text: Description
            description_label = wx.StaticText(self, label='\n'.join(button_function["description"]), pos=(button_x + 75, button.GetPosition()[1] + button.GetSize()[1] + 3))
            description_label.SetFont(gui_support.font_factory(10, wx.FONTWEIGHT_NORMAL))
            # button_y += 15

            for i, line in enumerate(button_function["description"]):
                if line == "":
                    continue
                if i == 0:
                    button_y += 11
                else:
                    button_y += 13

            button_y += 25

            if button_name == "创建OpenCore引导":
                self.build_button = button
                if gui_support.CheckProperties(self.constants).host_can_build() is False:
                    button.Disable()
            elif button_name == "安装驱动补丁":
                if self.constants.detected_os < os_data.os_data.big_sur:
                    button.Disable()
            elif button_name == "⚙️ 设置":
                  button.SetSize((100, -1))
                  #button.Centre(wx.HORIZONTAL)
                  description_label.Centre(wx.HORIZONTAL)
                  kdk_button = wx.Button(self, label="KDK下载", pos=(button_x - 50, button.GetPosition()[1]), size=(100, 30))
                  kdk_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                  kdk_button.Bind(wx.EVT_BUTTON, lambda event: self.on_download_kdk_package(event))
                  ml_button = wx.Button(self, label="MetalLib下载", pos=(button_x + 190, button.GetPosition()[1]), size=(100, 30))
                  ml_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                  ml_button.Bind(wx.EVT_BUTTON, lambda event: self.on_download_ml_package(event))
                  #button_y += 60  # 调整按钮的垂直位置

            index += 1
            if index == rollover:
                max_height = button_y
                button_x = 320
                button_y = model_label.GetPosition()[1] + 30


        # Text: Copyright
        copy_label = wx.StaticText(self, label=self.constants.copyright_date, pos=(-1, max_height - 15))
        copy_label.SetFont(gui_support.font_factory(10, wx.FONTWEIGHT_NORMAL))
        copy_label.Centre(wx.HORIZONTAL)

        # Set window size
        self.SetSize((-1, copy_label.GetPosition()[1] + 50))


    def _preflight_checks(self):
        if (
                self.constants.computer.build_model != None and
                self.constants.computer.build_model != self.constants.computer.real_model and
                self.constants.host_is_hackintosh is False
            ):
            # Notify user they're booting an unsupported configuration
            pop_up = wx.MessageDialog(
                self,
                f"我们发现您当前正在引导为其他单元构建的 OpenCore: {self.constants.computer.build_model}\n\n我们构建配置以匹配各个单元，并且不能与不同的 Mac 混合或重复使用。\n\n请构建并安装新的 OpenCore 配置，然后重新启动您的 Mac。",
                "检测到不支持的配置！",
                style=wx.OK | wx.ICON_EXCLAMATION
            )
            pop_up.ShowModal()
            self.on_build_and_install()
            return

        if "--update_installed" in sys.argv and self.constants.has_checked_updates is False and gui_support.CheckProperties(self.constants).host_can_build():
            # Notify user that the update has been installed
            self.constants.has_checked_updates = True
            pop_up = wx.MessageDialog(
                self,
                f"OCLP-Mod has been updated to the latest version: {self.constants.patcher_version}\n\nWould you like to update OpenCore and your root volume patches?",
                "更新成功!",
                style=wx.YES_NO | wx.YES_DEFAULT | wx.ICON_INFORMATION
            )
            pop_up.ShowModal()

            if pop_up.GetReturnCode() != wx.ID_YES:
                logging.info("Skipping OpenCore and root volume patch update...")
                return


            logging.info("Updating OpenCore and root volume patches...")
            self.constants.update_stage = gui_support.AutoUpdateStages.CHECKING
            self.Hide()
            pos = self.GetPosition()
            gui_build.BuildFrame(
                parent=None,
                title=self.title,
                global_constants=self.constants,
                screen_location=pos
            )
            self.Close()

        threading.Thread(target=self._check_for_updates).start()


    def _check_for_updates(self):
        if self.constants.has_checked_updates is True:
            return

        ignore_updates = global_settings.GlobalEnviromentSettings().read_property("IgnoreAppUpdates")
        if ignore_updates is True:
            self.constants.ignore_updates = True
            return

        self.constants.ignore_updates = False
        self.constants.has_checked_updates = True
        dict = updates.CheckBinaryUpdates(self.constants).check_binary_updates()
        if not dict:
            return

        version = dict["Version"]
        logging.info(f"New version: {version}")

        wx.CallAfter(self.on_update, dict["Link"], version, dict["Github Link"])

    def on_build_and_install(self, event: wx.Event = None):
        self.Hide()
        gui_build.BuildFrame(
            parent=None,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )
        self.Destroy()


    def on_post_install_root_patch(self, event: wx.Event = None):
        gui_sys_patch_display.SysPatchDisplayFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )


    def on_create_macos_installer(self, event: wx.Event = None):
        gui_macos_installer_download.macOSInstallerDownloadFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )


    def on_settings(self, event: wx.Event = None):
        gui_settings.SettingsFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )

    def on_help(self, event: wx.Event = None):
        gui_help.HelpFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )

    def on_update(self, oclp_url: str, oclp_version: str, oclp_github_url: str):

        ID_GITHUB = wx.NewId()
        ID_UPDATE = wx.NewId()

        url = "https://api.github.com/repos/laobamac/OCLP-Mod/releases/latest"
        response = requests.get(url).json()
        try:
            changelog = response["body"].split("## Asset Information")[0]
        except: #if user constantly checks for updates, github will rate limit them
            changelog = """## 获取更新日志失败

请前往Github RELEASE页面查看"""

        html_markdown = markdown2.markdown(changelog, extras=["tables"])
        html_css = css_data.updater_css
        frame = wx.Dialog(None, -1, title="😘OCLP-Mod发现更新了捏！", size=(650, 500))
        frame.SetMinSize((650, 500))
        frame.SetWindowStyle(wx.STAY_ON_TOP)
        panel = wx.Panel(frame)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        self.title_text = wx.StaticText(panel, label="新版本OCLP-Mod可以下载了！")
        self.description = wx.StaticText(panel, label=f"OCLP-Mod {oclp_version} 已发布   你现在安装的是 {self.constants.patcher_version}{'' if not self.constants.commit_info[0].startswith('refs/tags') else ''}， 你想现在更新吗？")
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
        {html_markdown}
        
    </body>
</html>
'''
        self.web_view.SetPage(html_code, "")
        self.web_view.Bind(wx.html2.EVT_WEBVIEW_NEWWINDOW, self._onWebviewNav)
        self.web_view.EnableContextMenu(False)
        self.close_button = wx.Button(panel, label="忽略")
        self.close_button.Bind(wx.EVT_BUTTON, lambda event: frame.EndModal(wx.ID_CANCEL))
        self.view_button = wx.Button(panel, ID_GITHUB, label="在Github上查看")
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
            webbrowser.open(oclp_github_url)
        elif result == ID_UPDATE:
            gui_update.UpdateFrame(
            parent=self,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition(),
            url=oclp_url,
            version_label=oclp_version
        )

        frame.Destroy()
    
    def on_download_kdk_package(self, event: wx.Event = None):
        kdk_window = gui_kdk_dl.DownloadKDKFrame(
            parent=self
        )
        kdk_window.Show()

    def on_download_ml_package(self, event: wx.Event = None):
        ml_window = gui_ml_dl.DownloadMLFrame(
            parent=self
        )
        ml_window.Show()

    def _onWebviewNav(self, event):
        url = event.GetURL()
        webbrowser.open(url)
