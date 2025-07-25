"""
gui_macos_installer_download.py: macOS Installer Download Frame
"""

import wx
import locale
import logging
import threading
import webbrowser
import json
import requests
import time
import urllib.parse
import hashlib

from pathlib import Path

from .. import (
    constants,
    sucatalog
)

from ..datasets import (
    os_data,
    smbios_data,
    cpu_data
)
from ..wx_gui import (
    gui_main_menu,
    gui_support,
    gui_download,
    gui_macos_installer_flash,
    gui_simplehac_dmg_flash
)
from ..support import (
    macos_installer_handler,
    utilities,
    network_handler,
    integrity_verification
)


class macOSInstallerDownloadFrame(wx.Frame):
    """
    Create a frame for downloading and creating macOS installers
    Uses a Modal Dialog for smoother transition from other frames
    Note: Flashing installers is passed to gui_macos_installer_flash.py
    """
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None):
        logging.info("Initializing macOS Installer Download Frame")
        self.constants: constants.Constants = global_constants
        self.title: str = title
        self.parent: wx.Frame = parent
        self.latest_dmgs=[]
        self.dmgs_all=[]

        self.available_installers = None
        self.available_installers_latest = None
        self.available_simplehac_dmgs = None
        self.fetched_aes_key = None
        self.fetched_aes_key_status = None

        self.catalog_seed: sucatalog.SeedType = sucatalog.SeedType.DeveloperSeed

        self.frame_modal = wx.Dialog(parent, title=title, size=(330, 200))

        self._generate_elements(self.frame_modal)
        self.frame_modal.ShowWindowModal()

        self.icons = [[self._icon_to_bitmap(i), self._icon_to_bitmap(i, (64, 64))] for i in self.constants.icons_path]

    def _icon_to_bitmap(self, icon: str, size: tuple = (32, 32)) -> wx.Bitmap:
        """
        Convert icon to bitmap
        """
        return wx.Bitmap(wx.Bitmap(icon, wx.BITMAP_TYPE_ICON).ConvertToImage().Rescale(size[0], size[1], wx.IMAGE_QUALITY_HIGH))

    def _macos_version_to_icon(self, version: int) -> int:
        """
        Convert macOS version to icon
        """
        try:
            self.constants.icons_path[version - 19]
            return version - 19
        except IndexError:
            return 0


    def _generate_elements(self, frame: wx.Frame = None) -> None:
        """
        Format:
        - Title:  Create macOS Installer
        - Button: Download macOS Installer
        - Button: Use existing macOS Installer
        - Button: Return to Main Menu
        """

        frame = self if not frame else frame

        title_label = wx.StaticText(frame, label="创建macOS安装器", pos=(-1,5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Button: Download macOS Installer
        download_button = wx.Button(frame, label="下载macOS安装器（.app）", pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5), size=(200, 30))
        download_button.Bind(wx.EVT_BUTTON, self.on_download)
        download_button.Centre(wx.HORIZONTAL)

        # Button: Use existing macOS Installer
        existing_button = wx.Button(frame, label="选择本地的安装器（.app）", pos=(-1, download_button.GetPosition()[1] + download_button.GetSize()[1] - 5), size=(200, 30))
        existing_button.Bind(wx.EVT_BUTTON, self.on_existing)
        existing_button.Centre(wx.HORIZONTAL)

        shdmg_button = wx.Button(frame, label="下载三分区镜像（.dmg）", pos=(-1, existing_button.GetPosition()[1] + existing_button.GetSize()[1] - 5), size=(200, 30))
        shdmg_button.Bind(wx.EVT_BUTTON, self.on_downdmg)
        shdmg_button.Centre(wx.HORIZONTAL)

        fldmg_button = wx.Button(frame, label="烧录DMG镜像（.dmg）", pos=(-1, shdmg_button.GetPosition()[1] + shdmg_button.GetSize()[1] - 5), size=(200, 30))
        fldmg_button.Bind(wx.EVT_BUTTON, self.on_flashdmg)
        fldmg_button.Centre(wx.HORIZONTAL)

        # Button: Return to Main Menu
        return_button = wx.Button(frame, label="返回", pos=(-1, fldmg_button.GetPosition()[1] + fldmg_button.GetSize()[1] + 5), size=(150, 30))
        return_button.Bind(wx.EVT_BUTTON, self.on_return)
        return_button.Centre(wx.HORIZONTAL)

        # Set size of frame
        frame.SetSize((-1, return_button.GetPosition()[1] + return_button.GetSize()[1] + 40))


    def _generate_catalog_frame(self) -> None:
        """
        Generate frame to display available installers
        """
        super(macOSInstallerDownloadFrame, self).__init__(None, title=self.title, size=(300, 200), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, self.constants).generate()
        self.Centre()

        # Title: Pulling installer catalog
        title_label = wx.StaticText(self, label="正在查找可下载的版本", pos=(-1,5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Progress bar
        progress_bar = wx.Gauge(self, range=100, pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5), size=(250, 30))
        progress_bar.Centre(wx.HORIZONTAL)
        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # Set size of frame
        self.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))

        self.Show()

        # Grab installer catalog
        def _fetch_installers():
            logging.info(f"Fetching installer catalog: {sucatalog.SeedType.DeveloperSeed.name}")

            sucatalog_contents = sucatalog.CatalogURL(seed=sucatalog.SeedType.DeveloperSeed).url_contents
            if sucatalog_contents is None:
                logging.error("Failed to download Installer Catalog from Apple")
                return

            self.available_installers        = sucatalog.CatalogProducts(sucatalog_contents).products
            self.available_installers_latest = sucatalog.CatalogProducts(sucatalog_contents).latest_products


        thread = threading.Thread(target=_fetch_installers)
        thread.start()

        gui_support.wait_for_thread(thread)

        progress_bar_animation.stop_pulse()
        progress_bar.Hide()
        self._display_available_installers()

    def _generate_dmg_frame(self) -> None:
        """
        生成显示可用DMG的框架。
        """
        super(macOSInstallerDownloadFrame, self).__init__(None, title=self.title, size=(300, 200), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, self.constants).generate()
        self.Centre()

        # 标题: 正在查找可下载的版本
        title_label = wx.StaticText(self, label="正在查找可下载的DMG镜像", pos=(-1, 5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # 进度条
        progress_bar = wx.Gauge(self, range=100, pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5), size=(250, 30))
        progress_bar.Centre(wx.HORIZONTAL)
        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # 设置窗口大小
        self.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))

        self.Show()

        def _fetch_dmg():
            apiurl = "https://oclpapi.simplehac.cn/DMG/api?token=oclpmod"
            aesurl = "https://oclpapi.simplehac.cn/DMG/data/aeskey.txt"

            try:
                # 发送 GET 请求
                response = requests.get(apiurl)
                aes = requests.get(aesurl)

                # 检查响应状态码是否为 200
                if response.status_code == 200:
                    # 解析 JSON 数据
                    dmgdata = response.json()  # 自动将 JSON 字符串解析为 Python 字典
                    logging.info("返回的 JSON 数据:")
                    dmgwell = json.dumps(dmgdata, indent=4, ensure_ascii=False)
                    logging.info(dmgwell)  # 格式化输出 JSON 数据
                    if aes.status_code == 200:
                        self.fetched_aes_key = aes.text.strip()
                        self.fetched_aes_key_status = aes.status_code
                        logging.info(self.fetched_aes_key_status)
                        logging.info(self.fetched_aes_key)
                    else:
                        logging.error(f"请求失败，状态码: {aes.status_code}")
                else:
                    logging.info(f"请求失败，状态码: {response.status_code}")

                dmg_number=[]
                dmg_build=[]
                dmgdata_all=dmgdata
                max_version=[]
                dmgdata=dmgdata['dmgFiles'][::-1]
                for i in range(len(dmgdata)):
                    #self.kdk_data[i].pop("kernel_versions")
                    dmgdata[i]['releaseDate']=((dmgdata[i]['releaseDate']).split("T"))[0]
                for i in range(len(dmgdata)):
                    data=dmgdata[i]["build"][:2]
                    data2=dmgdata[i]["build"]
                    dmg_number.append(data)
                    dmg_build.append(data2)
                for i in range(4):
                    maxn=dmg_number[0]
                    while True:
                        dmg_number.pop(0)
                        if len(dmg_number)==0 or dmg_number[0]<maxn :
                            break
                    max_version.append(maxn)
                i=0
                flag=[0,0,0,0]
                model={
                    "dmgFiles":[]
                }
                latest=[]
                while True:
                    if max_version[0] == dmgdata[i]["build"][:2] and flag[0]==0:
                        latest.append(dmgdata[i])
                        flag[0]=1
                        #print(kdk_data_latest)
                        i+=1
                    if  max_version[1] == dmgdata[i]["build"][:2]and flag[1]==0:
                        latest.append(dmgdata[i])
                        flag[1]=1
                        i+=1
                    if  max_version[2] == dmgdata[i]["build"][:2]and flag[2]==0:
                        latest.append(dmgdata[i])
                        flag[2]=1
                        i+=1
                    if  max_version[3] == dmgdata[i]["build"][:2]and flag[3]==0:
                        latest.append(dmgdata[i])
                        flag[3]=1
                        i+=1
                    if i==len(dmgdata)-1:
                        break
                    else:
                        i+=1
                        continue
                #self.kdk_data_full=self.kdk_data
                dmg_latest_version=latest[::-1]
                model["dmgFiles"]=dmg_latest_version
                self.latest_dmgs=model

            except requests.exceptions.RequestException as e:
                logging.info(f"请求发生异常: {e}")
            finally:
                if dmgdata is not None:
                    logging.info("Got it!")
                    self.available_simplehac_dmgs=self.latest_dmgs
                    self.dmgs_all = dmgdata_all
                    self.dmgs = dmgdata
                    logging.info(type(dmgdata))
                else:
                    logging.error("Lost it!")

        thread = threading.Thread(target=_fetch_dmg, args=())
        thread.start()

        gui_support.wait_for_thread(thread)

        progress_bar_animation.stop_pulse()
        progress_bar.Hide()
        self._display_available_dmgs()

    def generate_signed_url(self, download_url, aeskey):
        API_URL = 'https://oclpapi.simplehac.cn/DMG/api/down.php'

        parsed_url = urllib.parse.urlparse(download_url)
        file_name = urllib.parse.unquote(parsed_url.path.split('/')[-1])

        timestamp = int(time.time())
        expire_time = timestamp + 300  # 秒

        sign_data = f"oclpmod{file_name}{expire_time}{aeskey}"

        sign = hashlib.md5(sign_data.encode('utf-8')).hexdigest()

        signed_url = f"{API_URL}?origin={urllib.parse.quote(file_name)}&sign={sign}&t={expire_time}"
        return signed_url
    def detect_os_build(self, rsr: bool = False) -> str:
        import plistlib
        """
        Detect the booted OS build

        Implementation note:
            With macOS 13.2, Apple implemented the Rapid Security Response system which
            will change the reported build to the RSR version and not the original host

            To get the proper versions:
            - Host: /System/Library/CoreServices/SystemVersion.plist
            - RSR:  /System/Volumes/Preboot/Cryptexes/OS/System/Library/CoreServices/SystemVersion.plist


        Parameters:
            rsr (bool): Whether to use the RSR version of the build

        Returns:
            str: OS build (ex. 21A5522h)
        """

        file_path = "/System/Library/CoreServices/SystemVersion.plist"
        if rsr is True:
            file_path = f"/System/Volumes/Preboot/Cryptexes/OS{file_path}"

        try:
            return plistlib.load(open(file_path, "rb"))["ProductBuildVersion"]
        except Exception as e:
            raise RuntimeError(f"Failed to detect OS build: {e}")
    def _display_available_dmgs(self, event: wx.Event = None, show_full: bool = False) -> None:
        """
        在框架中显示可用的DMG
        """
        bundles = [wx.BitmapBundle.FromBitmaps(icon) for icon in self.icons]
        self.os_build_tahoe=self.detect_os_build(False)
        self.frame_modal.Destroy()
        self.frame_modal = wx.Dialog(self, title="选择SimpleHac DMG镜像", size=(505, 500))

        title_label = wx.StaticText(self.frame_modal, label="选择此镜像 由SimpleHac提供支持", pos=(-1, -1))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))

        id = wx.NewIdRef()

        self.list = wx.ListCtrl(self.frame_modal, id, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER | wx.BORDER_SUNKEN)
        self.list.SetSmallImages(bundles)

        self.list.InsertColumn(0, "Title", width=175)
        self.list.InsertColumn(1, "Version", width=50)
        self.list.InsertColumn(2, "Build", width=75)
        self.list.InsertColumn(3, "Size", width=75)
        self.list.InsertColumn(4, "Release Date", width=100)

        dmgs = self.available_simplehac_dmgs if show_full is False else self.dmgs_all

        if dmgs:
            locale.setlocale(locale.LC_TIME, '')
            for idx, item in enumerate(dmgs['dmgFiles'], start=1):
                logging.info(item)
                if isinstance(item, dict):
                    # 提取字段，带默认值
                    title = str(item.get('title', 'Unknown Title'))
                    version = str(item.get('version', 'Unknown Version'))
                    build = str(item.get('build', 'Unknown Build'))
                    size = str(item.get('size', 'Unknown Size'))
                    release_date = str(item.get('releaseDate', 'Unknown Date'))
                    download_url = str(item.get('downloadUrl', '#'))

                    # 在 GUI 列表中插入数据
                    index = self.list.InsertItem(self.list.GetItemCount(), title)
                    self.list.SetItemImage(index, self._macos_version_to_icon(int(build[:2])))
                    self.list.SetItem(index, 1, version)
                    self.list.SetItem(index, 2, build)
                    self.list.SetItem(index, 3, size)
                    self.list.SetItem(index, 4, release_date)
                else:
                    print(f"数据格式错误: {item}")
            if self.fetched_aes_key_status != 200:
                logging.info(f"无法获取到密钥 {self.fetched_aes_key_status}")
                wx.MessageDialog(self.frame_modal, "未能获取到密钥，请联系laobamac", "错误", wx.OK | wx.ICON_ERROR).ShowModal()
                self.on_return_to_main_menu()
        else:
            logging.error("No dmgs found")
            wx.MessageDialog(self.frame_modal, "未能获取到DMG信息，请联系laobamac", "错误", wx.OK | wx.ICON_ERROR).ShowModal()
            self.on_return_to_main_menu()

        if not show_full:
            self.list.Select(-1)
            self.frame_modal.SetSize((490, 370))

        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_select_list)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_select_list)

        self.select_button = wx.Button(self.frame_modal, label="下载", pos=(-1, -1), size=(150, -1))
        self.select_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        self.select_button.Bind(wx.EVT_BUTTON, lambda event, installers=dmgs: self.on_download_dmg(installers))
        self.dmgs = dmgs
        self.select_button.SetToolTip("下载选定的DMG")
        self.select_button.SetDefault()
        if show_full:
            self.select_button.Disable()

        self.copy_button = wx.Button(self.frame_modal, label="复制链接", pos=(-1, -1), size=(80, -1))
        self.copy_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        if show_full:
            self.copy_button.Disable()
        self.copy_button.SetToolTip("复制选定DMG的下载链接")
        self.copy_button.Bind(wx.EVT_BUTTON, lambda event, installers=dmgs: self.on_copy_dmg_link(installers))

        self.olderversions_checkbox = wx.CheckBox(self.frame_modal, label="显示老版本/测试版本", pos=(-1, -1))
        if show_full is True:
            self.olderversions_checkbox.SetValue(True)
        self.olderversions_checkbox.Bind(wx.EVT_CHECKBOX, lambda event: self._display_available_dmgs(event, self.olderversions_checkbox.GetValue()))

        return_button = wx.Button(self.frame_modal, label="返回", pos=(-1, -1), size=(150, -1))
        return_button.Bind(wx.EVT_BUTTON, self.on_return_to_main_menu)
        return_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        checkboxsizer = wx.BoxSizer(wx.HORIZONTAL)

        if self.os_build_tahoe!='25A5316i':
            rectbox = wx.StaticBox(self.frame_modal, -1)
            rectsizer = wx.StaticBoxSizer(rectbox, wx.HORIZONTAL)
            rectsizer.Add(self.copy_button, 0, wx.EXPAND | wx.RIGHT, 5)
            rectsizer.Add(self.select_button, 0, wx.EXPAND | wx.LEFT, 5)
        checkboxsizer.Add(self.olderversions_checkbox, 0, wx.ALIGN_CENTRE | wx.RIGHT, 5)


        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        sizer.Add(title_label, 0, wx.ALIGN_CENTRE | wx.ALL, 0)
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 10)
        if self.os_build_tahoe!='25A5316i':
             sizer.Add(rectsizer, 0, wx.ALIGN_CENTRE | wx.ALL, 0)
             sizer.AddSpacer(10)
        elif self.os_build_tahoe=='25A5316i':
            mosizer=wx.BoxSizer(wx.HORIZONTAL)
            mosizer.Add(self.copy_button, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
            mosizer.Add(self.select_button, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
            sizer.Add(mosizer, 0, wx.ALIGN_CENTRE | wx.ALL, 0)
            sizer.AddSpacer(8)
        sizer.Add(checkboxsizer, 0, wx.ALIGN_CENTRE | wx.ALL, 15)
        sizer.Add(return_button, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 15)

        self.frame_modal.SetSizer(sizer)
        self.frame_modal.ShowWindowModal()
    def _display_available_installers(self, event: wx.Event = None, show_full: bool = False) -> None:
        """
        Display available installers in frame
        """

        self.os_build_tahoe=self.detect_os_build(False)
        bundles = [wx.BitmapBundle.FromBitmaps(icon) for icon in self.icons]

        self.frame_modal.Destroy()
        self.frame_modal = wx.Dialog(self, title="选择macOS安装器", size=(505, 500))

        # Title: Select macOS Installer
        title_label = wx.StaticText(self.frame_modal, label="选择此macOS", pos=(-1,-1))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))

        # macOS Installers list
        id = wx.NewIdRef()

        self.list = wx.ListCtrl(self.frame_modal, id, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER | wx.BORDER_SUNKEN)
        self.list.SetSmallImages(bundles)

        self.list.InsertColumn(0, "Title",        width=175)
        self.list.InsertColumn(1, "Version",      width=50)
        self.list.InsertColumn(2, "Build",        width=75)
        self.list.InsertColumn(3, "Size",         width=75)
        self.list.InsertColumn(4, "Release Date", width=100)

        installers = self.available_installers_latest if show_full is False else self.available_installers
        if show_full is False:
            self.frame_modal.SetSize((490, 370))

        if installers:
            locale.setlocale(locale.LC_TIME, '')
            logging.info(f"Available installers on SUCatalog ({'All entries' if show_full else 'Latest only'}):")
            for item in installers:
                logging.info(f"- {item['Title']} ({item['Version']} - {item['Build']}):\n  - Size: {utilities.human_fmt(item['InstallAssistant']['Size'])}\n  - Link: {item['InstallAssistant']['URL']}\n")
                index = self.list.InsertItem(self.list.GetItemCount(), f"{item['Title']}")
                self.list.SetItemImage(index, self._macos_version_to_icon(int(item['Build'][:2])))
                self.list.SetItem(index, 1, item['Version'])
                self.list.SetItem(index, 2, item['Build'])
                self.list.SetItem(index, 3, utilities.human_fmt(item['InstallAssistant']['Size']))
                self.list.SetItem(index, 4, item['PostDate'].strftime("%x"))
        else:
            logging.error("No installers found on SUCatalog")
            wx.MessageDialog(self.frame_modal, "Failed to download Installer Catalog from Apple", "Error", wx.OK | wx.ICON_ERROR).ShowModal()

        if show_full is False:
            self.list.Select(-1)

        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_select_list)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_select_list)

        self.select_button = wx.Button(self.frame_modal, label="下载", pos=(-1, -1), size=(150, -1))
        self.select_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        self.select_button.Bind(wx.EVT_BUTTON, lambda event, installers=installers: self.on_download_installer(installers))
        self.select_button.SetToolTip("下载选定的macOS")
        self.select_button.SetDefault()
        if show_full is True:
            self.select_button.Disable()

        self.copy_button = wx.Button(self.frame_modal, label="复制链接", pos=(-1, -1), size=(80, -1))
        self.copy_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        if show_full is True:
            self.copy_button.Disable()
        self.copy_button.SetToolTip("Copy the download link of the selected macOS Installer.")
        self.copy_button.Bind(wx.EVT_BUTTON, lambda event, installers=installers: self.on_copy_link(installers))

        return_button = wx.Button(self.frame_modal, label="返回", pos=(-1, -1), size=(150, -1))
        return_button.Bind(wx.EVT_BUTTON, self.on_return_to_main_menu)
        return_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))

        self.showolderversions_checkbox = wx.CheckBox(self.frame_modal, label="显示老版本/测试版本", pos=(-1, -1))
        if show_full is True:
            self.showolderversions_checkbox.SetValue(True)
        self.showolderversions_checkbox.Bind(wx.EVT_CHECKBOX, lambda event: self._display_available_installers(event, self.showolderversions_checkbox.GetValue()))

        if self.os_build_tahoe!='25A5316i':
            rectbox = wx.StaticBox(self.frame_modal, -1)
            rectsizer = wx.StaticBoxSizer(rectbox, wx.HORIZONTAL)
            rectsizer.Add(self.copy_button, 0, wx.EXPAND | wx.RIGHT, 5)
            rectsizer.Add(self.select_button, 0, wx.EXPAND | wx.LEFT, 5)

        checkboxsizer = wx.BoxSizer(wx.HORIZONTAL)
        checkboxsizer.Add(self.showolderversions_checkbox, 0, wx.ALIGN_CENTRE | wx.RIGHT, 5)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)
        sizer.Add(title_label, 0, wx.ALIGN_CENTRE | wx.ALL, 0)
        sizer.Add(self.list, 1, wx.EXPAND | wx.ALL, 10)
        if self.os_build_tahoe!='25A5316i':
             sizer.Add(rectsizer, 0, wx.ALIGN_CENTRE | wx.ALL, 0)
        elif self.os_build_tahoe=='25A5316i':
            mosizer=wx.BoxSizer(wx.HORIZONTAL)
            mosizer.Add(self.copy_button, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
            mosizer.Add(self.select_button, 0, wx.ALIGN_CENTRE | wx.ALL, 5)
            sizer.Add(mosizer, 0, wx.ALIGN_CENTRE | wx.ALL, 0)
        sizer.Add(checkboxsizer, 0, wx.ALIGN_CENTRE | wx.ALL, 15)
        sizer.Add(return_button, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 15)

        self.frame_modal.SetSizer(sizer)
        self.frame_modal.ShowWindowModal()

    def on_copy_link(self, installers: dict) -> None:

        selected_item = self.list.GetFirstSelected()
        if selected_item != -1:
            clipboard = wx.Clipboard.Get()

            if not clipboard.IsOpened():
                clipboard.Open()

            clipboard.SetData(wx.TextDataObject(installers[selected_item]['InstallAssistant']['URL']))

            clipboard.Close()

            wx.MessageDialog(self.frame_modal, "已复制到剪贴板", "", wx.OK | wx.ICON_INFORMATION).ShowModal()

    def on_copy_dmg_link(self, installers: dict) -> None:

        selected_item = self.list.GetFirstSelected()
        if selected_item != -1:
            clipboard = wx.Clipboard.Get()

            if not clipboard.IsOpened():
                clipboard.Open()
            
            item = installers['dmgFiles'][selected_item]
            origin = item.get('downloadUrl', '')

            if not origin:
                logging.error(f"Download URL not found for selected item: {item}")
                clipboard.Close()
                wx.MessageDialog(self.frame_modal, "未能找到下载链接", "错误", wx.OK | wx.ICON_ERROR).ShowModal()
                return
            
            clipboard.SetData(wx.TextDataObject(self.generate_signed_url(origin, self.fetched_aes_key)))

            clipboard.Close()

            wx.MessageDialog(self.frame_modal, "已复制到剪贴板", "", wx.OK | wx.ICON_INFORMATION).ShowModal()

    def on_select_list(self, event):
        if self.list.GetSelectedItemCount() > 0:
            self.select_button.Enable()
            self.copy_button.Enable()
        else:
            self.select_button.Disable()
            self.copy_button.Disable()

    def on_download_dmg(self, installers: dict) -> None:
        """
        Download macOS installer
        """

        selected_item = self.list.GetFirstSelected()
        if selected_item != -1:
            selected_installer = installers['dmgFiles'][selected_item]

            logging.info(f"Selected macOS DMG {selected_installer['version']} ({selected_installer['build']})")

            item = installers['dmgFiles'][selected_item]
            download_url = item.get('downloadUrl', '')
            title = item.get('title', '')
            version = item.get('version', '')
            build = item.get('build', '')
            size = item.get('size', '')

            self.frame_modal.Close()

            dir_dialog = wx.DirDialog(self, "选择保存目录", "", wx.DD_DIR_MUST_EXIST)
        
            if dir_dialog.ShowModal() == wx.ID_OK:
            # 获取用户选择的目录路径
                save_path = dir_dialog.GetPath()
                logging.info(f"选择了目录: {save_path}")
            dir_dialog.Destroy()
            file_name = f"/Install+{title}+{version}+{build}+with+OC&FirPE+SimpleHac.dmg"

            download_obj = network_handler.DownloadObject(download_url, save_path+file_name, size)

            gui_download.DownloadFrame(
                self,
                title="从SimpleHac OSS下载镜像",
                global_constants=self.constants,
                download_obj=download_obj,
                item_name=f"SimpleHac's macOS {selected_installer['version']}",
                download_icon=self.constants.icons_path[self._macos_version_to_icon(int(item['build'][:2]))]
            )

            if download_obj.download_complete is False:
                self.on_return_to_main_menu()
                return

    def on_download_installer(self, installers: dict) -> None:
        """
        Download macOS installer
        """

        selected_item = self.list.GetFirstSelected()
        if selected_item != -1:
            selected_installer = installers[selected_item]

            logging.info(f"Selected macOS {selected_installer['Version']} ({selected_installer['Build']})")

            # Notify user whether their model is compatible with the selected installer
            problems = []
            model = self.constants.custom_model or self.constants.computer.real_model
            if model in smbios_data.smbios_dictionary:
                if selected_installer["InstallAssistant"]["XNUMajor"] >= os_data.os_data.ventura:
                    if smbios_data.smbios_dictionary[model]["CPU Generation"] <= cpu_data.CPUGen.penryn or model in ["MacPro4,1", "MacPro5,1", "Xserve3,1"]:
                        if model.startswith("MacBook"):
                            problems.append("Lack of internal Keyboard/Trackpad in macOS installer.")
                        else:
                            problems.append("Lack of internal Keyboard/Mouse in macOS installer.")

            if problems:
                logging.warning(f"Potential issues with {model} and {selected_installer['Version']} ({selected_installer['Build']}): {problems}")
                problems = "\n".join(problems)
                dlg = wx.MessageDialog(self.frame_modal, f"Your model ({model}) may not be fully supported by this installer. You may encounter the following issues:\n\n{problems}\n\nFor more information, see associated page. Otherwise, we recommend using macOS Monterey", "Potential Issues", wx.YES_NO | wx.CANCEL | wx.ICON_WARNING)
                dlg.SetYesNoCancelLabels("View Github Issue", "Download Anyways", "Cancel")
                result = dlg.ShowModal()
                if result == wx.ID_CANCEL:
                    return
                elif result == wx.ID_YES:
                    webbrowser.open("https://github.com/Dortania/OpenCore-Legacy-Patcher/issues/1021")
                    return

            host_space = utilities.get_free_space()
            needed_space = selected_installer['InstallAssistant']['Size'] * 2
            if host_space < needed_space:
                logging.error(f"Insufficient space to download and extract: {utilities.human_fmt(host_space)} available vs {utilities.human_fmt(needed_space)} required")
                dlg = wx.MessageDialog(self.frame_modal, f"You do not have enough free space to download and extract this installer. Please free up some space and try again\n\n{utilities.human_fmt(host_space)} available vs {utilities.human_fmt(needed_space)} required", "Insufficient Space", wx.OK | wx.ICON_WARNING)
                dlg.ShowModal()
                return

            self.frame_modal.Close()

            download_obj = network_handler.DownloadObject(selected_installer['InstallAssistant']['URL'], self.constants.payload_path / "InstallAssistant.pkg")

            gui_download.DownloadFrame(
                self,
                title=self.title,
                global_constants=self.constants,
                download_obj=download_obj,
                item_name=f"macOS {selected_installer['Version']} ({selected_installer['Build']})",
                download_icon=self.constants.icons_path[self._macos_version_to_icon(selected_installer["InstallAssistant"]["XNUMajor"])]
            )

            if download_obj.download_complete is False:
                self.on_return_to_main_menu()
                return

            self._validate_installer(selected_installer['InstallAssistant']['IntegrityDataURL'])


    def _validate_installer(self, chunklist_link: str) -> None:
        """
        Validate macOS installer
        """
        self.SetSize((300, 200))
        for child in self.GetChildren():
            child.Destroy()

        # Title: Validating macOS Installer
        title_label = wx.StaticText(self, label="Validating macOS Installer", pos=(-1,5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Label: Validating chunk 0 of 0
        chunk_label = wx.StaticText(self, label="Validating chunk 0 of 0", pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5))
        chunk_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        chunk_label.Centre(wx.HORIZONTAL)

        # Progress bar
        progress_bar = wx.Gauge(self, range=100, pos=(-1, chunk_label.GetPosition()[1] + chunk_label.GetSize()[1] + 5), size=(270, 30))
        progress_bar.Centre(wx.HORIZONTAL)

        # Set size of frame
        self.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))
        self.Show()

        chunklist_stream = network_handler.NetworkUtilities().get(chunklist_link).content
        if chunklist_stream:
            logging.info("Validating macOS installer")
            utilities.disable_sleep_while_running()
            chunk_obj = integrity_verification.ChunklistVerification(self.constants.payload_path / Path("InstallAssistant.pkg"), chunklist_stream)
            if chunk_obj.chunks:
                progress_bar.SetValue(chunk_obj.current_chunk)
                progress_bar.SetRange(chunk_obj.total_chunks)

                wx.App.Get().Yield()
                chunk_obj.validate()

                while chunk_obj.status == integrity_verification.ChunklistStatus.IN_PROGRESS:
                    progress_bar.SetValue(chunk_obj.current_chunk)
                    chunk_label.SetLabel(f"Validating chunk {chunk_obj.current_chunk} of {chunk_obj.total_chunks}")
                    chunk_label.Centre(wx.HORIZONTAL)
                    wx.App.Get().Yield()

                if chunk_obj.status == integrity_verification.ChunklistStatus.FAILURE:
                    logging.error(f"Chunklist validation failed: Hash mismatch on {chunk_obj.current_chunk}")
                    wx.MessageBox(f"Chunklist validation failed: Hash mismatch on {chunk_obj.current_chunk}\n\nThis generally happens when downloading on unstable connections such as WiFi or cellular.\n\nPlease try redownloading again on a stable connection (ie. Ethernet)", "Corrupted Installer!", wx.OK | wx.ICON_ERROR)
                    self.on_return_to_main_menu()
                    return

        logging.info("macOS installer validated")

        # Extract installer
        title_label.SetLabel("Extracting macOS Installer")
        title_label.Centre(wx.HORIZONTAL)

        chunk_label.SetLabel("May take a few minutes...")
        chunk_label.Centre(wx.HORIZONTAL)

        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # Start thread to extract installer
        self.result = False
        def extract_installer():
            self.result = macos_installer_handler.InstallerCreation().install_macOS_installer(self.constants.payload_path)

        thread = threading.Thread(target=extract_installer)
        thread.start()

        # Show frame
        self.Show()

        # Wait for thread to finish
        gui_support.wait_for_thread(thread)

        progress_bar_animation.stop_pulse()
        progress_bar.Hide()
        chunk_label.SetLabel("Successfully extracted macOS installer" if self.result is True else "Failed to extract macOS installer")
        chunk_label.Centre(wx.HORIZONTAL)

        # Create macOS Installer button
        create_installer_button = wx.Button(self, label="Create macOS Installer", pos=(-1, progress_bar.GetPosition()[1]), size=(170, 30))
        create_installer_button.Bind(wx.EVT_BUTTON, self.on_existing)
        create_installer_button.Centre(wx.HORIZONTAL)
        if self.result is False:
            create_installer_button.Disable()

        # Return to main menu button
        return_button = wx.Button(self, label="Return to Main Menu", pos=(-1, create_installer_button.GetPosition()[1] + create_installer_button.GetSize()[1]), size=(150, 30))
        return_button.Bind(wx.EVT_BUTTON, self.on_return_to_main_menu)
        return_button.Centre(wx.HORIZONTAL)

        # Set size of frame
        self.SetSize((-1, return_button.GetPosition()[1] + return_button.GetSize()[1] + 40))

        # Show frame
        self.Show()

        if self.result is False:
            wx.MessageBox("An error occurred while extracting the macOS installer. Could be due to a corrupted installer", "Error", wx.OK | wx.ICON_ERROR)
            return

        user_input = wx.MessageBox("Finished extracting the installer, would you like to continue and create a macOS installer?", "Create macOS Installer?", wx.YES_NO | wx.ICON_QUESTION)
        if user_input == wx.YES:
            self.on_existing()


    def on_download(self, event: wx.Event) -> None:
        """
        Display available macOS versions to download
        """
        self.frame_modal.Close()
        self.parent.Hide()
        self._generate_catalog_frame()
        self.parent.Close()


    def on_existing(self, event: wx.Event = None) -> None:
        """
        Display local macOS installers
        """
        frames = [self, self.frame_modal, self.parent]
        for frame in frames:
            if frame:
                frame.Close()
        gui_macos_installer_flash.macOSInstallerFlashFrame(
            None,
            title=self.title,
            global_constants=self.constants,
            **({"screen_location": self.GetScreenPosition()} if self else {})
        )
        for frame in frames:
            if frame:
                frame.Destroy()
    
    def on_downdmg(self, event: wx.Event) -> None:
        '''
        Download SimpleHac's DMG
        '''
        self.frame_modal.Close()
        self.parent.Hide()
        self._generate_dmg_frame()
        self.parent.Close()

    def on_flashdmg(self, event: wx.Event) -> None:
        '''
        Flash SimpleHac's DMG
        '''
        '''
        frames = [self, self.frame_modal, self.parent]
        for frame in frames:
            if frame:
                frame.Close()
        gui_simplehac_dmg_flash.DMGFlashFrame(
            None,
            title=self.title,
            global_constants=self.constants,
            **({"screen_location": self.GetScreenPosition()} if self else {})
        )
        for frame in frames:
            if frame:
                frame.Destroy()
        '''
        wx.MessageDialog(self.frame_modal, "学业繁忙，此处未完工（gui_simplehac_dmg_flash.py为残品），请下载etcher自行刻录！\n现在为你打开SimpleHac加速镜像下载etcher", "", wx.OK | wx.ICON_INFORMATION).ShowModal()
        webbrowser.open("https://download.simplehac.cn/https://github.com/balena-io/etcher/releases/download/v1.19.25/balenaEtcher-1.19.25-x64.dmg")

    def on_return(self, event: wx.Event) -> None:
        """
        Return to main menu (dismiss frame)
        """
        self.frame_modal.Close()


    def on_return_to_main_menu(self, event: wx.Event = None) -> None:
        """
        Return to main menu
        """
        if self.frame_modal:
            self.frame_modal.Hide()
        main_menu_frame = gui_main_menu.MainFrame(
            None,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetScreenPosition()
        )
        main_menu_frame.Show()
        if self.frame_modal:
            self.frame_modal.Destroy()
        self.Destroy()
