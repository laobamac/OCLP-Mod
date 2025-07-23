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
)
from ..support import (
    
    utilities,
    network_handler,
    integrity_verification
)
kdkurl = ""
KDK_API_LINK_PROXY:str  = "https://oclpapi.simplehac.cn/KdkSupportPkg/manifest.json"
KDK_API_LINK_ORIGIN:str  = "https://dortania.github.io/KdkSupportPkg/manifest.json"
class NewKDKDownloadFrame(wx.Frame):
    """
    创建用于下载和制作macOS安装器的窗口框架
    使用模态对话框以实现与其他窗口的平滑过渡
    注意：刻录安装器的功能在 gui_macos_installer_flash.py 中实现
    """
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants,screen_location: tuple = None):
        """
        初始化 macOS 安装器下载控件
        :param parent: 父窗口
        :param title: 窗口标题
        :param global_constants: 全局常量
        :param screen_location: 屏幕位置
        """
        logging.info("初始化 KDK 下载控件")
        self.constants: constants.Constants = global_constants
        self.title: str = title
        self.parent: wx.Frame = parent
        icon_path = str(self.constants.icns_resource_path / "Package.icns")
        self.icons = [self._icon_to_bitmap(icon_path), self._icon_to_bitmap(icon_path, (64, 64))]
        self.repl=False
        # 存储可用的安装器信息
        self.available_installers = None
        self.available_installers_latest = None
        self.fetched_aes_key = None
        self.fetched_aes_key_status = None
        self.kdk_data = None
        self.kdk_data_full=None
        self.kdk_data_latest = None
        # 指定拉取的种子类型（开发者种子）
        self.catalog_seed: sucatalog.SeedType = sucatalog.SeedType.DeveloperSeed

        # 创建模态对话框，防止用户误操作
        self.frame_modal = wx.Dialog(parent, title=title, size=(330, 200))
       
        # 生成界面元素
        self.on_download()
        

    def _icon_to_bitmap(self, icon: str, size: tuple = (32, 32)) -> wx.Bitmap:
        """
        将图标文件转换为指定大小的位图
        :param icon: 图标路径
        :param size: 位图大小
        :return: wx.Bitmap 对象
        用法：用于 KDK版本列表的图标展示
        """
        return wx.Bitmap(wx.Bitmap(icon, wx.BITMAP_TYPE_ICON).ConvertToImage().Rescale(size[0], size[1], wx.IMAGE_QUALITY_HIGH))

    def _generate_catalog_frame(self) -> None:
        """
        生成用于显示可用安装器的窗口
        用法：拉取 Apple 官方安装器目录，展示给用户选择
        """
        super(NewKDKDownloadFrame, self).__init__(None, title=self.title, size=(300, 200), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, self.constants).generate()
        self.Centre()

        # 标题：拉取安装器目录
        title_label = wx.StaticText(self, label="正在查找可下载的KDK", pos=(-1,5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # 进度条，提示用户正在加载
        progress_bar = wx.Gauge(self, range=100, pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5), size=(250, 30))
        progress_bar.Centre(wx.HORIZONTAL)
        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()
        # 设置窗口大小，适配内容
        self.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))
        self.Show()

        # 拉取安装器目录的线程，避免界面卡死
        def _fetch_installers():
            try:
                #logging.info(f"Fetching installer catalog: {sucatalog.SeedType.DeveloperSeed.name}")
                if self.constants.use_github_proxy == True:
                    KDK_API_LINK: str = KDK_API_LINK_PROXY
                else:
                    KDK_API_LINK: str = KDK_API_LINK_ORIGIN
                response = requests.get(KDK_API_LINK)
                self.kdk_data = response.json()
                self.kdk_data_latest = []
                kdk_data_number=[]
                kdk_data_build=[]
                maxnx=[]
                for i in range(len(self.kdk_data)):
                    self.kdk_data[i].pop("kernel_versions")
                    self.kdk_data[i]['seen']=((self.kdk_data[i]['seen']).split("T"))[0]
                for i in range(len(self.kdk_data)):
                    data=self.kdk_data[i]["build"][:2]
                    data2=self.kdk_data[i]["build"]
                    kdk_data_number.append(data)
                    kdk_data_build.append(data2)
                #print(kdk_data_number)
                for i in range(4):
                    maxn=kdk_data_number[0]
                    while True:
                        kdk_data_number.pop(0)
                        if len(kdk_data_number)==0 or kdk_data_number[0]<maxn :
                            break
                    maxnx.append(maxn)
                #print(kdk_data[0]['build'])
                i=0
                fl=[0,0,0,0]
                while True:
                    if maxnx[0] == self.kdk_data[i]["build"][:2] and fl[0]==0:
                        self.kdk_data_latest.append(self.kdk_data[i])
                        fl[0]=1
                        #print(kdk_data_latest)
                        i+=1
                    if  maxnx[1] == self.kdk_data[i]["build"][:2]and fl[1]==0:
                        self.kdk_data_latest.append(self.kdk_data[i])
                        fl[1]=1
                        i+=1
                    if  maxnx[2] == self.kdk_data[i]["build"][:2]and fl[2]==0:
                        self.kdk_data_latest.append(self.kdk_data[i])
                        fl[2]=1
                        i+=1
                    if  maxnx[3] == self.kdk_data[i]["build"][:2]and fl[3]==0:
                        self.kdk_data_latest.append(self.kdk_data[i])
                        fl[3]=1
                        i+=1
                    if i==len(self.kdk_data)-1:
                        break
                    else:
                        i+=1
                        continue
                self.kdk_data_full=self.kdk_data
                self.kdk_data_latest=self.kdk_data_latest
                #return
            except requests.RequestException as e:
                wx.MessageBox(f"获取KDK信息失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
                #wx.CallAfter(self.loading_frame.close)
                self.on_return_to_main_menu()
        thread = threading.Thread(target=_fetch_installers)
        thread.start()
        # 等待线程完成，期间进度条动画持续
        gui_support.wait_for_thread(thread)
        progress_bar_animation.stop_pulse()
        progress_bar.Hide()
        self._display_available_installers()
    def convert_size(self,size_bytes):
        """将字节转换为可读格式 (KB, MB, GB)"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} TB"
    def _display_available_installers(self, event: wx.Event = None, show_full: bool = False) -> None:
        """
        在窗口中显示可用的 macOS 安装器列表
        :param event: 事件对象
        :param show_full: 是否显示所有版本（True 显示所有，False 只显示最新）
        用法：供用户选择需要下载的 macOS 版本
        """
        #super(NewKDKDownloadFrame, self).__init__(None, title=self.title, size=(300, 200), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        # bundles 用于 wx.ListCtrl 的图标绑定 
        
        bundles = [wx.BitmapBundle.FromBitmaps(self.icons)]

        self.frame_modal.Destroy()
        self.frame_modal = wx.Dialog(self, title="选择KDK版本", size=(640, 580))

        # 标题
        title_label = wx.StaticText(self.frame_modal, label="选择此KDK", pos=(-1,-1))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))

        # macOS 安装器列表控件
        id = wx.NewIdRef()
        self.list = wx.ListCtrl(self.frame_modal, id, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_NO_HEADER | wx.BORDER_SUNKEN)
        self.list.SetSmallImages(bundles)

        # 设置列表列名和宽度
        self.list.InsertColumn(0, "name",        width=300)
        self.list.InsertColumn(1, "version",      width=50)
        self.list.InsertColumn(2, "build",        width=75)
        self.list.InsertColumn(3, "size",         width=85)
        self.list.InsertColumn(4, "seen", width=105)

        # 选择展示最新还是全部安装器
        
        if show_full is False:
            self.frame_modal.SetSize((640, 400))

        installers = self.kdk_data_latest[::-1] if show_full is False else self.kdk_data_full[::-1]
        # 填充列表内容
        if installers:
            locale.setlocale(locale.LC_TIME, '')
            logging.info(f"Available installers on SUCatalog ({'All entries' if show_full else 'Latest only'}):")
            for item in installers:
                logging.info(f"- {item['name']} (macOS {item['version']} - {item['build']}):\n  - Size: {self.convert_size(item['fileSize'])}\n  - Link: {item['url']}\n")
                index = self.list.InsertItem(self.list.GetItemCount(), f"{item['name']}")
                # 用 build 号前两位推算图标索引
                self.list.SetItemImage(index, 0)
                self.list.SetItem(index, 1, f"{item['version']}")
                self.list.SetItem(index, 2, f"{item['build']}")
                self.list.SetItem(index, 3, f"{self.convert_size(item['fileSize'])}")
                self.list.SetItem(index, 4, f"{item['seen']}")
               # self.list.SetItem(index, 1, f"{item['version']}")
        else:
            logging.error("没有在SUCatalog发现任何安装器")
            wx.MessageDialog(self.frame_modal, "Failed to download Installer Catalog from Apple", "Error", wx.OK | wx.ICON_ERROR).ShowModal()
            self.on_return_to_main_menu()

        if show_full is False:
            self.list.Select(-1)

        # 绑定列表选择事件，控制按钮可用性
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_select_list)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_select_list)

        # 下载按钮
        self.select_button = wx.Button(self.frame_modal, label="下载", pos=(-1, -1), size=(150, -1))
        self.select_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        self.select_button.Bind(wx.EVT_BUTTON, lambda event, installers=installers: self.on_download_installer(installers))
        self.select_button.SetToolTip("下载选定的KDK")
        self.select_button.SetDefault()
        if show_full is True:
            self.select_button.Disable()

        # 复制链接按钮
        self.copy_button = wx.Button(self.frame_modal, label="复制链接", pos=(-1, -1), size=(80, -1))
        self.copy_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        if show_full is True:
            self.copy_button.Disable()
        self.copy_button.SetToolTip("复制所选KDK安装器的下载链接")
        self.copy_button.Bind(wx.EVT_BUTTON, lambda event, installers=installers: self.on_copy_link(installers))

        # 返回按钮
        return_button = wx.Button(self.frame_modal, label="返回", pos=(-1, -1), size=(150, -1))
        return_button.Bind(wx.EVT_BUTTON, self.on_return_to_main_menu)
        return_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))

        if self.constants.use_github_proxy==True:
            text="Laobamac"
        else:
            text="Dortania"

        bo_label = wx.StaticText(self.frame_modal, label=f"由 {text} 提供", pos=(-1,-1))
        bo_label.SetFont(gui_support.font_factory(9, wx.FONTWEIGHT_BOLD))

        # 显示老版本/测试版本复选框
        self.showolderversions_checkbox = wx.CheckBox(self.frame_modal, label="显示所有版本", pos=(-1, -1))
        if show_full is True:
            self.showolderversions_checkbox.SetValue(True)
        self.showolderversions_checkbox.Bind(wx.EVT_CHECKBOX, lambda event: self._display_available_installers(event, self.showolderversions_checkbox.GetValue()))

        # 按钮布局
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
        sizer.Add(rectsizer, 0, wx.ALIGN_CENTRE | wx.ALL, 0)
        sizer.Add(checkboxsizer, 0, wx.ALIGN_CENTRE | wx.ALL, 15)
        sizer.Add(return_button, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 15)
        sizer.Add(bo_label, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 15)

        self.frame_modal.SetSizer(sizer)
        self.frame_modal.ShowWindowModal()

    def on_copy_link(self, installers: dict) -> None:
        """
        复制所选KDK安装器的下载链接到剪贴板
        用法：点击“复制链接”按钮后触发
        """
        selected_item = self.list.GetFirstSelected()
        if selected_item != -1:
            clipboard = wx.Clipboard.Get()

            if not clipboard.IsOpened():
                clipboard.Open()

            clipboard.SetData(wx.TextDataObject(installers[selected_item]['url']))

            clipboard.Close()

            wx.MessageDialog(self.frame_modal, "已复制到剪贴板", "", wx.OK | wx.ICON_INFORMATION).ShowModal()

    def on_select_list(self, event):
        """
        控制按钮可用性：有选择时启用下载和复制按钮，无选择时禁用
        """
        if self.list.GetSelectedItemCount() > 0:
            self.select_button.Enable()
            self.copy_button.Enable()
        else:
            self.select_button.Disable()
            self.copy_button.Disable()   
    def on_download_installer(self, installers: dict) -> None:
        """
        下载 macOS 安装器
        用法：点击“下载”按钮后触发，自动检测兼容性和空间
        """
        selected_item = self.list.GetFirstSelected()
        if selected_item != -1:
            
            selected_installer = installers[selected_item]
            while True:
                dir_dialog = wx.DirDialog(self, "选择保存目录", "", wx.DD_DIR_MUST_EXIST)
                if dir_dialog.ShowModal() == wx.ID_OK:
                    save_path = dir_dialog.GetPath()
                    def is_dir_writable(dirpath):
                        """跨平台目录可写性检查"""
                        import os
                        return os.access(dirpath, os.W_OK | os.X_OK)
                    if not is_dir_writable(save_path):
                        wx.MessageBox(
                            "无法写入该目录，请选择可写目录", 
                            "目录只读", 
                            wx.OK | wx.ICON_WARNING
                        )  
                        dir_dialog.Destroy()
                    else:
                        logging.info(f"选择了目录: {save_path}")
                        dir_dialog.Destroy()
                        break
                else:
                    self.on_return_to_main_menu()
                    return
                
            file_name = selected_installer['name']+".pkg"
            self.frame_modal.Close()
            download_obj = network_handler.DownloadObject(selected_installer['url'], save_path+"/"+file_name)
            # 弹出下载进度窗口
            gui_download.DownloadFrame(
                self,
                title=self.title,
                global_constants=self.constants,
                download_obj=download_obj,
                item_name=f"KDK {selected_installer['version']} {selected_installer['build']}",
                download_icon=str(self.constants.icns_resource_path / "Package.icns")
            )
            # 下载未完成则返回主菜单
            if download_obj.download_complete is False:
                import os
                os.remove(save_path+"/"+file_name)
                self.on_return_to_main_menu()
                return
            # 下载完成后校验完整性
            user_input = wx.MessageBox("安装程序下载完成，您想退出吗？", "Return to main menu?", wx.YES_NO | wx.ICON_QUESTION)
            if user_input == wx.YES:
                self.on_return_to_main_menu()

    def _validate_installer(self, chunklist: str) -> None:
        """
        验证KDK安装器
        用法：下载完成后自动校验 chunklist，确保文件未损坏
        未完工
        """
        self.SetSize((300, 200))
        for child in self.GetChildren():
            child.Destroy()

        # 标题：正在校验
        title_label = wx.StaticText(self, label="校验KDK安装器的哈希值...", pos=(-1,5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # 校验进度标签
        chunk_label = wx.StaticText(self, label="Validating chunk 0 of 0", pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5))
        chunk_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        chunk_label.Centre(wx.HORIZONTAL)

        # 校验进度条
        progress_bar = wx.Gauge(self, range=100, pos=(-1, chunk_label.GetPosition()[1] + chunk_label.GetSize()[1] + 5), size=(270, 30))
        progress_bar.Centre(wx.HORIZONTAL)

        # 设置窗口大小
        self.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))
        self.Show()

        # 下载 chunklist 并校验
        chunklist=chunklist
        logging.info("校验KDK")
        utilities.disable_sleep_while_running()
        
            

        logging.info("KDK installer validated")

        user_input = wx.MessageBox("安装程序提取完成，您想退出吗？", "Return to main menu?", wx.YES_NO | wx.ICON_QUESTION)
        if user_input == wx.YES:
            self.on_return_to_main_menu()

    def on_download(self) -> None:
        """
        显示可下载的 macOS 版本
        用法：主菜单点击“下载”后触发，进入安装器选择界面
        """
        self.frame_modal.Close()
        self.parent.Hide()
        self._generate_catalog_frame()
        self.parent.Close()

    def on_return_to_main_menu(self, event: wx.Event = None) -> None:
        """
        返回主菜单
        用法：点击“返回”按钮或流程结束后自动返回主菜单
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
    