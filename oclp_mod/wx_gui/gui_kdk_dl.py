import wx
import requests
import threading
from wx.lib.agw.customtreectrl import CustomTreeCtrl
import time
import os

from .. import constants
from ..constants import Constants

kdkurl = ""

KDK_API_LINK_PROXY:     str  = "https://next.oclpapi.simplehac.cn/KdkSupportPkg/manifest.json"
KDK_API_LINK_ORIGIN:     str  = "https://dortania.github.io/KdkSupportPkg/manifest.json"

class DownloadProgressFrame(wx.Frame):
    def __init__(self, parent, title, url, file_path):
        super(DownloadProgressFrame, self).__init__(parent, title=title, size=(400, 150))
        self.parent = parent
        panel = wx.Panel(self)
        
        self.title_label = wx.StaticText(panel, label=f"正在下载: {os.path.basename(file_path)}", pos=(10, 10))
        self.title_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        
        self.progress_bar = wx.Gauge(panel, range=100, pos=(10, 40), size=(380, 25))
        self.progress_bar.SetValue(0)
        
        self.speed_label = wx.StaticText(panel, label="准备下载...", pos=(10, 70))
        self.speed_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))

        self.cancel_button = wx.Button(panel, label="取消", pos=(300, 100))
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)

        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.url = url
        self.file_path = file_path
        self.downloading = True
        self.download_complete = False

        # 启动下载线程
        self.download_thread = threading.Thread(target=self.download_file)
        self.download_thread.daemon = True
        self.download_thread.start()

        # 启动定时器更新界面
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.update_ui, self.timer)
        self.timer.Start(100)  # 每100ms更新一次

        self.Centre()

    def download_file(self):
        try:
            # 禁用 SSL 证书验证
            response = requests.get(self.url, stream=True, verify=False)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            start_time = time.time()
            last_update_time = start_time
            last_downloaded = 0

            with open(self.file_path, "wb") as f:
                for data in response.iter_content(chunk_size=8192):  # 增大块大小
                    if not self.downloading:
                        break
                    
                    downloaded += len(data)
                    f.write(data)
                    
                    # 计算下载速度（每0.5秒更新一次）
                    current_time = time.time()
                    if current_time - last_update_time >= 0.5:
                        speed = (downloaded - last_downloaded) / (current_time - last_update_time)
                        last_downloaded = downloaded
                        last_update_time = current_time
                        
                        # 更新进度信息
                        progress = int((downloaded / total_size) * 100) if total_size > 0 else 0
                        self.progress_info = {
                            'progress': progress,
                            'downloaded': downloaded,
                            'total_size': total_size,
                            'speed': speed
                        }

            if self.downloading:
                self.download_complete = True
                wx.CallAfter(self.on_download_complete)

        except requests.RequestException as e:
            if self.downloading:  # 只在未取消的情况下显示错误
                wx.CallAfter(wx.MessageBox, f"下载失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        
        wx.CallAfter(self.timer.Stop)

    def update_ui(self, event):
        if hasattr(self, 'progress_info'):
            progress_info = self.progress_info
            self.progress_bar.SetValue(progress_info['progress'])
            
            downloaded_mb = progress_info['downloaded'] / 1024 / 1024
            total_mb = progress_info['total_size'] / 1024 / 1024
            speed_mb = progress_info['speed'] / 1024 / 1024
            
            self.speed_label.SetLabel(
                f"{downloaded_mb:.2f} MB / {total_mb:.2f} MB "
                f"({progress_info['progress']}%) @ {speed_mb:.2f} MB/s"
            )

    def on_download_complete(self):
        wx.MessageBox(f"下载完成！\n文件保存至: {self.file_path}", "成功", wx.OK | wx.ICON_INFORMATION)
        self.Close()

    def on_cancel(self, event):
        self.downloading = False
        wx.MessageBox("下载已取消", "提示", wx.OK | wx.ICON_INFORMATION)
        self.Close()

    def on_close(self, event):
        self.downloading = False
        self.timer.Stop()
        if hasattr(self, 'download_thread') and self.download_thread.is_alive():
            self.download_thread.join(timeout=1.0)
        self.Destroy()

class LoadingFrame(wx.Frame):
    def __init__(self, parent, title):
        super(LoadingFrame, self).__init__(parent, title=title, size=(300, 100), style=wx.STAY_ON_TOP)
        panel = wx.Panel(self)

        # Title
        self.title_label = wx.StaticText(panel, label="正在获取KDK信息...", pos=(50, 10))
        self.title_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

        # Progress bar
        self.progress_bar = wx.Gauge(panel, range=100, pos=(50, 40), size=(200, 20))
        self.progress_bar.SetValue(50)  # 50%表示正在加载

        self.Centre()
        self.Show()

    def close(self):
        self.Destroy()

class DownloadListCtrl(wx.ListCtrl):
    def __init__(self, parent):
        super(DownloadListCtrl, self).__init__(parent, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.InsertColumn(0, "版本", width=80)
        self.InsertColumn(1, "系统", width=100)
        self.InsertColumn(2, "日期", width=120)
        self.InsertColumn(3, "下载链接", width=225)
        self.data = []  # 存储每个条目的数据

    def SetData(self, MetalLib_data):
        self.data = []  # 清空旧数据
        self.DeleteAllItems()  # 清空列表显示
        
        for item in MetalLib_data:
            version = f"{item['build']}"
            size = f"macOS {item['version']}"
            date = item['date'].split('T')[0]
            url = item['url']
            index = self.InsertItem(self.GetItemCount(), version)
            self.SetItem(index, 1, size)
            self.SetItem(index, 2, date)
            self.SetItem(index, 3, url)
            self.data.append({'version': version, 'url': url})  # 存储数据

    def get_selected_data(self):
        selected_index = self.GetFirstSelected()
        if selected_index != -1:
            return self.data[selected_index]
        return None

class DownloadKDKFrame(wx.Frame):
    def __init__(self, parent, global_constants: Constants):
        self.constants: constants.Constants = global_constants
        super(DownloadKDKFrame, self).__init__(parent, title="KDK下载", size=(600, 400))
        panel = wx.Panel(self)

        self.list_ctrl = DownloadListCtrl(panel)
        self.download_button = wx.Button(panel, label="下载")
        self.copy_button = wx.Button(panel, label="复制链接")
        
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_copy)
        self.download_button.Bind(wx.EVT_BUTTON, self.on_download)

        sizer = wx.BoxSizer(wx.VERTICAL)
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        sizer.Add(self.list_ctrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        
        button_sizer.Add(self.download_button, proportion=0, flag=wx.ALL, border=5)
        button_sizer.Add(self.copy_button, proportion=0, flag=wx.ALL, border=5)
        
        sizer.Add(button_sizer, proportion=0, flag=wx.CENTER | wx.ALL, border=5)
        panel.SetSizer(sizer)
        
        self.Centre()
        self.Show()
        
        # 在后台线程中加载数据
        self.loading_frame = LoadingFrame(self, title="正在加载")
        threading.Thread(target=self.fetch_kdk_data, daemon=True).start()

    def fetch_kdk_data(self):
        time.sleep(1)  # 让加载界面显示一会儿
        if self.constants.use_github_proxy == True:
            KDK_API_LINK: str = KDK_API_LINK_PROXY
        else:
            KDK_API_LINK: str = KDK_API_LINK_ORIGIN
        try:
            # 禁用 SSL 证书验证
            response = requests.get(KDK_API_LINK, verify=False)
            response.raise_for_status()
            kdk_data = response.json()
            wx.CallAfter(self.list_ctrl.SetData, kdk_data)
        except requests.RequestException as e:
            wx.CallAfter(wx.MessageBox, f"获取KDK信息失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        
        wx.CallAfter(self.loading_frame.close)
    
    def on_copy(self, event):
        selected_data = self.list_ctrl.get_selected_data()
        if selected_data:
            url = selected_data['url']
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(url))
                wx.TheClipboard.Close()
                wx.MessageBox("链接已复制到剪贴板", "成功", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("请选择一个KDK版本进行复制", "提示", wx.OK | wx.ICON_INFORMATION)

    def on_download(self, event):
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
                    DPF_Window = DownloadProgressFrame(self, title="下载进度", url=url, file_path=file_path)
                    DPF_Window.Show()
        else:
            wx.MessageBox("请选择一个KDK版本进行下载", "提示", wx.OK | wx.ICON_INFORMATION)