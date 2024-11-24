import wx
import requests
import threading
from wx.lib.agw.customtreectrl import CustomTreeCtrl
import time

kdkurl = ""

class DownloadProgressFrame(wx.Frame):
    def __init__(self, parent, title, url, file_path):
        super(DownloadProgressFrame, self).__init__(parent, title=title, size=(400, 150))
        panel = wx.Panel(self)
        self.title_label = wx.StaticText(panel, label="", pos=(10, 10))
        self.title_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        self.progress_bar = wx.Gauge(panel, range=100, pos=(10, 40), size=(380, 25))
        self.progress_bar.SetValue(0)
        self.speed_label = wx.StaticText(panel, label="", pos=(10, 70))
        self.speed_label.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))

        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.url = url
        self.file_path = file_path
        self.downloading = True

        self.download_thread = threading.Thread(target=self.download_file)
        self.download_thread.start()

    def download_file(self):
        try:
            response = requests.get(self.url, stream=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            last_downloaded = 0
            start_time = time.time()

            with open(self.file_path, "wb") as f:
                for data in response.iter_content(chunk_size=4096):
                    if not self.downloading:
                        break
                    downloaded += len(data)
                    f.write(data)
                    current_time = time.time()
                    speed = (downloaded - last_downloaded) / (current_time - start_time)
                    last_downloaded = downloaded
                    start_time = current_time

                    wx.CallAfter(self.progress_bar.SetValue, int((downloaded / total_size) * 100))
                    wx.CallAfter(self.speed_label.SetLabel, f"{downloaded/1024/1024:.2f} MB / {total_size/1024/1024:.2f} MB @ {speed/1024/1024:.2f} MB/s")
        except requests.RequestException as e:
            wx.MessageBox(f"下载失败: {e}", "错误", wx.OK | wx.ICON_ERROR)

        wx.CallAfter(self.Close)

    def on_close(self, event):
        self.downloading = False
        self.download_thread.join()
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
        self.InsertColumn(0, "版本", width=100)
        self.InsertColumn(1, "大小", width=80)
        self.InsertColumn(2, "日期", width=120)
        self.InsertColumn(3, "下载链接", width=225)

    def SetData(self, kdk_data):
        for item in kdk_data:
            global kdkurl
            version = f"{item['build']} {item['version']}"
            size = f"{item['fileSize']/1024/1024:.2f} MB"
            date = item['date'].split('T')[0]
            kdkurl = item['url']
            index = self.InsertItem(self.GetItemCount(), version)
            self.SetItem(index, 1, size)
            self.SetItem(index, 2, date)
            self.SetItem(index, 3, "那能告诉你吗，哥们，万一刷我流量（")
            #kdkurl = item['url']

class DownloadKDKFrame(wx.Frame):
    def __init__(self, parent):
        super(DownloadKDKFrame, self).__init__(parent, title="KDK下载", size=(600, 400))
        panel = wx.Panel(self)

        self.list_ctrl = DownloadListCtrl(panel)
        self.download_button = wx.Button(panel, label="下载", pos=(250, 350))
        self.download_button.Bind(wx.EVT_BUTTON, self.on_download)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.list_ctrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.download_button, proportion=0, flag=wx.CENTER | wx.ALL, border=5)

        panel.SetSizer(sizer)
        self.Show()
        self.loading_frame = LoadingFrame(self, title="正在加载")
        self.loading_frame.Show()
        self.fetch_kdk_data()

    def fetch_kdk_data(self):
        time.sleep(1)
        try:
            response = requests.get("https://oclpapi.simplehac.cn/KdkSupportPkg/manifest.json")
            response.raise_for_status()
            kdk_data = response.json()
            wx.CallAfter(self.list_ctrl.SetData, kdk_data)
            wx.CallAfter(self.loading_frame.close)
        except requests.RequestException as e:
            wx.MessageBox(f"获取KDK信息失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.loading_frame.close)

    def on_download(self, event):
        selected_index = self.list_ctrl.GetFirstSelected()
        if selected_index != -1:
            with wx.FileDialog(self, "保存文件", wildcard="DMG Files (*.dmg)|*.dmg", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
                if dlg.ShowModal() == wx.ID_CANCEL:
                    return
                file_path = dlg.GetPath()
            url = kdkurl
            DPF_Window = DownloadProgressFrame(self, title="下载进度", url=url, file_path=file_path)
            DPF_Window.Show()
        else:
            wx.MessageBox("请选择一个KDK版本进行下载", "提示", wx.OK | wx.ICON_INFORMATION)