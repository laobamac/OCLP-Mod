import wx
import requests
import threading
from wx.lib.agw.customtreectrl import CustomTreeCtrl
import time
import os
import json

from .. import constants
from ..constants import Constants

# 导入 network_handler 模块
from ..support import network_handler
from ..support.network_handler import DownloadObject, DownloadStatus

kdkurl = ""

KDK_API_LINK_PROXY: str = "https://next.oclpapi.simplehac.cn/KdkSupportPkg/manifest.json"
KDK_API_LINK_ORIGIN: str = "https://dortania.github.io/KdkSupportPkg/manifest.json"

class DownloadProgressFrame(wx.Dialog):
    """下载进度对话框"""
    def __init__(self, parent, title, url, file_path, file_size=0):
        style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        super(DownloadProgressFrame, self).__init__(parent, title=title, size=(520, 250), style=style)
        
        self.parent = parent
        self.url = url
        self.file_path = file_path
        self.file_size = file_size
        self.downloading = True
        self.download_complete = False
        
        self.init_ui()
        self.start_download()

    def init_ui(self):
        """初始化用户界面"""
        # 使用系统颜色，适配夜间模式
        panel = wx.Panel(self)
        
        # 主垂直布局
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 标题
        title_text = wx.StaticText(panel, label="下载文件")
        title_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title_text.SetFont(title_font)
        main_sizer.Add(title_text, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        # 分隔线
        line = wx.StaticLine(panel, style=wx.LI_HORIZONTAL)
        main_sizer.Add(line, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # 文件信息区域
        info_sizer = wx.GridBagSizer(10, 15)
        
        # 文件名
        name_label = wx.StaticText(panel, label="文件名称:")
        self.name_value = wx.StaticText(panel, label=os.path.basename(self.file_path))
        info_sizer.Add(name_label, (0, 0), flag=wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(self.name_value, (0, 1), flag=wx.EXPAND)
        
        # 文件大小
        size_label = wx.StaticText(panel, label="文件大小:")
        size_str = self.format_file_size(self.file_size) if self.file_size > 0 else "计算中..."
        self.size_value = wx.StaticText(panel, label=size_str)
        info_sizer.Add(size_label, (1, 0), flag=wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(self.size_value, (1, 1), flag=wx.EXPAND)
        
        info_sizer.AddGrowableCol(1)
        main_sizer.Add(info_sizer, 0, wx.EXPAND | wx.ALL, 15)
        
        # 进度条区域
        progress_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 进度百分比和详细信息在同一行
        progress_info_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.percent_label = wx.StaticText(panel, label="0%")
        percent_font = wx.Font(20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.percent_label.SetFont(percent_font)
        progress_info_sizer.Add(self.percent_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        # 进度详细信息
        self.detail_label = wx.StaticText(panel, label="准备下载...")
        progress_info_sizer.Add(self.detail_label, 1, wx.ALIGN_CENTER_VERTICAL)
        
        progress_sizer.Add(progress_info_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        # 进度条
        self.progress_bar = wx.Gauge(panel, range=100, size=(460, 20))
        self.progress_bar.SetValue(0)
        progress_sizer.Add(self.progress_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        # 添加一些底部间距，避免按钮被遮挡
        progress_sizer.AddSpacer(10)
        
        main_sizer.Add(progress_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # 按钮区域 - 增加顶部间距
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer()
        
        self.cancel_button = wx.Button(panel, label="取消下载", size=(100, 35))
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        button_sizer.Add(self.cancel_button, 0, wx.ALL, 5)
        
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        
        panel.SetSizer(main_sizer)
        
        # 绑定事件
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_SHOW, self.on_show)

    def on_show(self, event):
        """窗口显示时触发布局刷新"""
        if event.IsShown():
            # 延迟刷新布局，确保窗口完全显示
            wx.CallLater(100, self.force_layout_refresh)
        event.Skip()

    def force_layout_refresh(self):
        """强制刷新布局"""
        self.Layout()
        self.Refresh()
        # 轻微调整大小以触发完整布局计算
        current_size = self.GetSize()
        self.SetSize((current_size[0] + 1, current_size[1]))
        wx.CallLater(50, lambda: self.SetSize(current_size))

    def refresh_layout(self):
        """刷新布局"""
        self.Layout()
        self.Refresh()

    def format_file_size(self, size_bytes):
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"

    def start_download(self):
        """开始下载"""
        # 使用 DownloadObject 进行下载
        self.download_object = DownloadObject(self.url, self.file_path, size=str(self.file_size))
        
        # 启动下载线程
        self.download_thread = threading.Thread(target=self.download_file)
        self.download_thread.daemon = True
        self.download_thread.start()

        # 启动定时器更新界面
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_ui, self.timer)
        self.timer.Start(300)  # 每300ms更新一次

        self.Centre()

    def download_file(self):
        """使用 DownloadObject 进行下载"""
        try:
            # 开始下载（不在单独线程中运行，因为我们已经在后台线程中）
            self.download_object.download(spawn_thread=False, display_progress=False)
            
            # 等待下载完成或出错
            while self.download_object.is_active() and self.downloading:
                time.sleep(0.3)
            
            if self.downloading:
                if self.download_object.download_complete:
                    self.download_complete = True
                    wx.CallAfter(self.on_download_complete)
                else:
                    wx.CallAfter(self.on_download_error, self.download_object.error_msg)
                    
        except Exception as e:
            if self.downloading:  # 只在未取消的情况下显示错误
                wx.CallAfter(self.on_download_error, str(e))
        
        wx.CallAfter(self.timer.Stop)

    def update_ui(self, event):
        """更新界面显示"""
        if self.download_object and self.download_object.is_active():
            # 获取下载进度信息
            percent = self.download_object.get_percent()
            downloaded_bytes = self.download_object.downloaded_file_size
            total_bytes = self.download_object.total_file_size
            speed = self.download_object.get_speed()
            
            # 更新进度条和百分比
            if percent >= 0:
                progress_value = int(percent)
                self.progress_bar.SetValue(progress_value)
                self.percent_label.SetLabel(f"{progress_value}%")
            else:
                # 如果无法获取百分比，使用伪进度
                current_value = self.progress_bar.GetValue()
                if current_value < 90:
                    self.progress_bar.SetValue(current_value + 1)
                    self.percent_label.SetLabel(f"{current_value + 1}%")
            
            # 格式化显示数据
            downloaded_str = self.format_file_size(downloaded_bytes)
            total_str = self.format_file_size(total_bytes) if total_bytes > 0 else "未知"
            speed_str = self.format_file_size(speed) + "/s"
            
            # 更新详细信息标签 - 将所有信息合并到一行
            detail_text = f"速度: {speed_str}  已下载: {downloaded_str} / {total_str}"
            self.detail_label.SetLabel(detail_text)

    def on_download_complete(self):
        """下载完成处理"""
        wx.MessageBox(f"下载完成！\n文件保存至: {self.file_path}", "成功", wx.OK | wx.ICON_INFORMATION)
        self.EndModal(wx.ID_OK)

    def on_download_error(self, error_msg):
        """下载错误处理"""
        wx.MessageBox(f"下载失败: {error_msg}", "错误", wx.OK | wx.ICON_ERROR)
        self.EndModal(wx.ID_CANCEL)

    def on_cancel(self, event):
        """取消下载"""
        self.downloading = False
        if self.download_object:
            self.download_object.stop()
        self.EndModal(wx.ID_CANCEL)

    def on_close(self, event):
        """窗口关闭处理"""
        self.downloading = False
        self.timer.Stop()
        if self.download_object:
            self.download_object.stop()
        if hasattr(self, 'download_thread') and self.download_thread.is_alive():
            self.download_thread.join(timeout=1.0)
        self.Destroy()

class LoadingFrame(wx.Dialog):
    """加载中对话框"""
    def __init__(self, parent, title):
        style = wx.STAY_ON_TOP
        super(LoadingFrame, self).__init__(parent, title=title, size=(350, 120), style=style)
        
        self.init_ui()
        self.Centre()

    def init_ui(self):
        """初始化用户界面"""
        panel = wx.Panel(self)
        
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 加载动画区域
        loading_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 加载文本
        text_sizer = wx.BoxSizer(wx.VERTICAL)
        
        title_label = wx.StaticText(panel, label="正在获取 KDK 信息")
        title_font = wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title_label.SetFont(title_font)
        text_sizer.Add(title_label, 0, wx.ALL, 5)
        
        desc_label = wx.StaticText(panel, label="请稍候，正在从服务器加载数据...")
        text_sizer.Add(desc_label, 0, wx.ALL, 2)
        
        loading_sizer.Add(text_sizer, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        main_sizer.Add(loading_sizer, 1, wx.EXPAND)
        
        # 进度条
        self.progress_bar = wx.Gauge(panel, range=100, size=(300, 20))
        self.progress_bar.SetValue(0)
        main_sizer.Add(self.progress_bar, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        
        panel.SetSizer(main_sizer)
        
        # 启动动画定时器
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(100)
        self.progress_value = 0

    def on_timer(self, event):
        """更新加载动画"""
        self.progress_value = (self.progress_value + 5) % 100
        self.progress_bar.SetValue(self.progress_value)

    def close(self):
        """关闭对话框"""
        self.timer.Stop()
        self.Destroy()

class DownloadListCtrl(wx.ListCtrl):
    """下载列表控件"""
    def __init__(self, parent):
        super(DownloadListCtrl, self).__init__(parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        
        # 添加列 - 调整列宽以消除空白
        self.InsertColumn(0, "版本", width=120)
        self.InsertColumn(1, "系统版本", width=150)
        self.InsertColumn(2, "文件大小", width=120)
        self.InsertColumn(3, "发布日期", width=120)
        self.InsertColumn(4, "下载链接", width=280)  # 增加下载链接列宽
        
        self.data = []  # 存储每个条目的数据

    def format_file_size(self, size_bytes):
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.2f} {size_names[i]}"

    def SetData(self, kdk_data):
        """设置列表数据"""
        self.data = []  # 清空旧数据
        self.DeleteAllItems()  # 清空列表显示
        
        for item in kdk_data:
            version = f"{item['build']}"
            system_version = f"macOS {item['version']}"
            file_size = self.format_file_size(item.get('fileSize', 0))
            date = item['date'].split('T')[0]
            url = item['url']
            
            index = self.InsertItem(self.GetItemCount(), version)
            self.SetItem(index, 1, system_version)
            self.SetItem(index, 2, file_size)
            self.SetItem(index, 3, date)
            self.SetItem(index, 4, url)
            
            self.data.append({
                'version': version, 
                'url': url,
                'fileSize': item.get('fileSize', 0)
            })

    def get_selected_data(self):
        """获取选中项的数据"""
        selected_index = self.GetFirstSelected()
        if selected_index != -1:
            return self.data[selected_index]
        return None

class DownloadKDKFrame(wx.Frame):
    """KDK下载管理器主窗口"""
    def __init__(self, parent, global_constants: Constants):
        self.constants: constants.Constants = global_constants
        super(DownloadKDKFrame, self).__init__(parent, title="KDK 下载管理器", size=(800, 600))
        
        self.init_ui()
        self.Centre()
        self.Show()
        
        # 在后台线程中加载数据
        self.loading_dialog = LoadingFrame(self, "加载中")
        self.loading_dialog.Show()
        threading.Thread(target=self.fetch_kdk_data, daemon=True).start()

    def init_ui(self):
        """初始化用户界面"""
        panel = wx.Panel(self)
        
        # 主垂直布局
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 标题区域
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 标题文字
        title_text = wx.StaticText(panel, label="KDK 下载管理器")
        title_font = wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title_text.SetFont(title_font)
        header_sizer.Add(title_text, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        
        # 刷新按钮
        self.refresh_button = wx.Button(panel, label="刷新列表")
        self.refresh_button.Bind(wx.EVT_BUTTON, self.on_refresh)
        header_sizer.Add(self.refresh_button, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        
        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # 分隔线
        line = wx.StaticLine(panel, style=wx.LI_HORIZONTAL)
        main_sizer.Add(line, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # 说明文字
        desc_text = wx.StaticText(panel, label="选择要下载的 Kernel Debug Kit (KDK) 版本:")
        main_sizer.Add(desc_text, 0, wx.ALL, 10)
        
        # 列表控件
        self.list_ctrl = DownloadListCtrl(panel)
        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # 按钮区域
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer()
        
        self.copy_button = wx.Button(panel, label="复制链接")
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_copy)
        button_sizer.Add(self.copy_button, 0, wx.ALL, 5)
        
        self.download_button = wx.Button(panel, label="下载选中")
        self.download_button.Bind(wx.EVT_BUTTON, self.on_download)
        button_sizer.Add(self.download_button, 0, wx.ALL, 5)
        
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(main_sizer)

    def fetch_kdk_data(self):
        """获取 KDK 数据"""
        time.sleep(1)  # 让加载界面显示一会儿
        
        if self.constants.use_github_proxy == True:
            KDK_API_LINK: str = KDK_API_LINK_PROXY
        else:
            KDK_API_LINK: str = KDK_API_LINK_ORIGIN
            
        try:
            # 使用 NetworkUtilities 来获取数据
            network_utils = network_handler.NetworkUtilities()
            response = network_utils.get(KDK_API_LINK)
            response.raise_for_status()
            kdk_data = response.json()
            wx.CallAfter(self.list_ctrl.SetData, kdk_data)
        except Exception as e:
            wx.CallAfter(wx.MessageBox, f"获取 KDK 信息失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        
        wx.CallAfter(self.loading_dialog.close)

    def on_refresh(self, event):
        """刷新列表"""
        self.loading_dialog = LoadingFrame(self, "加载中")
        self.loading_dialog.Show()
        threading.Thread(target=self.fetch_kdk_data, daemon=True).start()

    def on_copy(self, event):
        """复制链接"""
        selected_data = self.list_ctrl.get_selected_data()
        if selected_data:
            url = selected_data['url']
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(url))
                wx.TheClipboard.Close()
                wx.MessageBox("链接已复制到剪贴板", "成功", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("请选择一个 KDK 版本进行复制", "提示", wx.OK | wx.ICON_INFORMATION)

    def on_download(self, event):
        """下载选中项"""
        selected_data = self.list_ctrl.get_selected_data()
        if selected_data:
            # 设置默认文件名
            default_file = f"Kernel_Debug_Kit_{selected_data['version']}.dmg"
            with wx.FileDialog(self, "保存文件", defaultFile=default_file, 
                             wildcard="DMG Files (*.dmg)|*.dmg", 
                             style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
                if dlg.ShowModal() == wx.ID_OK:
                    file_path = dlg.GetPath()
                    url = selected_data['url']
                    file_size = selected_data.get('fileSize', 0)
                    
                    # 显示下载进度对话框 - 使用 Show() 而不是 ShowModal()
                    download_dialog = DownloadProgressFrame(self, "下载进度", url, file_path, file_size)
                    download_dialog.Show()
        else:
            wx.MessageBox("请选择一个 KDK 版本进行下载", "提示", wx.OK | wx.ICON_INFORMATION)