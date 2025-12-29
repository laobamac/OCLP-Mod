import wx
import requests
import threading
from wx.lib.agw.customtreectrl import CustomTreeCtrl
import time

from .. import constants
from ..languages.language_handler import LanguageHandler


kdkurl = ""

class DownloadProgressFrame(wx.Frame):
    def __init__(self, parent, title, global_constants: constants.Constants,url, file_path):
        super(DownloadProgressFrame, self).__init__(parent, title=title, size=(400, 150))
        panel = wx.Panel(self)
        self.constants: constants.Constants = global_constants
        self.language_handler = LanguageHandler(self.constants)
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
            wx.MessageBox(f"{self.language_handler.get_translation('Download_failed')} {e}", self.language_handler.get_translation('Error'), wx.OK | wx.ICON_ERROR)

        wx.CallAfter(self.Close)

    def on_close(self, event):
        self.downloading = False
        self.download_thread.join()
        self.Destroy()

class LoadingFrame(wx.Frame):
    def __init__(self, parent,global_constants: constants.Constants, title):
        self.constants: constants.Constants = global_constants
        self.language_handler = LanguageHandler(self.constants)
        super(LoadingFrame, self).__init__(parent, title=title, size=(300, 100), style=wx.STAY_ON_TOP)
        panel = wx.Panel(self)
        
        # Title
        self.title_label = wx.StaticText(panel, label=self.language_handler.get_translation("Retrieving_KDK_information..."), pos=(50, 10))
        self.title_label.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

        # Progress bar
        self.progress_bar = wx.Gauge(panel, range=100, pos=(50, 40), size=(200, 20))
        self.progress_bar.SetValue(50)  # 50% indicates loading

        self.Centre()
        self.Show()

    def close(self):
        self.Destroy()

class DownloadListCtrl(wx.ListCtrl):
    def __init__(self, parent,global_constants: constants.Constants):
        self.constants: constants.Constants = global_constants
        self.language_handler = LanguageHandler(self.constants)
        super(DownloadListCtrl, self).__init__(parent, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.InsertColumn(0, self.language_handler.get_translation("Versions"), width=80)
        self.InsertColumn(1, self.language_handler.get_translation("System"), width=100)
        self.InsertColumn(2, self.language_handler.get_translation("Date"), width=120)
        self.InsertColumn(3, self.language_handler.get_translation("Download_link"), width=225)
        self.data = []  # Store entry data

    def SetData(self, MetalLib_data):
        self.data = []  # Clear old data
        for item in MetalLib_data:
            version = f"{item['build']}"
            size = f"macOS {item['version']}"
            date = item['date'].split('T')[0]
            url = item['url']
            index = self.InsertItem(self.GetItemCount(), version)
            self.SetItem(index, 1, size)
            self.SetItem(index, 2, date)
            self.SetItem(index, 3, url)
            self.data.append({'version': version, 'url': url})  # Store data

    def get_selected_data(self):
        selected_index = self.GetFirstSelected()
        if selected_index != -1:
            return self.data[selected_index]
        return None
            #kdkurl = item['url']

class DownloadKDKFrame(wx.Frame):
    def __init__(self, parent,global_constants: constants.Constants,):
        self.constants: constants.Constants = global_constants
        self.language_handler = LanguageHandler(self.constants)
        super(DownloadKDKFrame, self).__init__(parent, title=self.language_handler.get_translation("kdk_download"), size=(600, 400))
        panel = wx.Panel(self)
        self.list_ctrl = DownloadListCtrl(panel,self.constants)
        self.download_button = wx.Button(panel, label=self.language_handler.get_translation("Download"), pos=(-250, 35))
        self.copy_button = wx.Button(panel, label=self.language_handler.get_translation("Copy_link"), pos=(30, 350))
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_copy)
        self.download_button.Bind(wx.EVT_BUTTON, self.on_download)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.list_ctrl, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(self.download_button, proportion=0, flag=wx.CENTER | wx.ALL, border=5)
        sizer.Add(self.copy_button, proportion=0, flag=wx.CENTER | wx.ALL, border=5)

        panel.SetSizer(sizer)
        self.Show()
        self.loading_frame = LoadingFrame(self, self.constants,title=self.language_handler.get_translation("Loading"))
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
            wx.MessageBox(f"{self.language_handler.get_translation('Failed_to_retrieve_KDK_information:')} {e}", self.language_handler.get_translation('Error'), wx.OK | wx.ICON_ERROR)
            wx.CallAfter(self.loading_frame.close)
    
    def on_copy(self, event):
        selected_data = self.list_ctrl.get_selected_data()
        if selected_data:
            url = selected_data['url']
            wx.TheClipboard.Open()
            wx.TheClipboard.SetData(wx.TextDataObject(url))
            wx.TheClipboard.Close()
            wx.MessageBox(self.language_handler.get_translation("Copied_to_clipboard"), self.language_handler.get_translation("Success"), wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox(self.language_handler.get_translation("Please_select_a_KDK_version_to_copy."), self.language_handler.get_translation("Guide"), wx.OK | wx.ICON_INFORMATION)


    def on_download(self, event):
        selected_data = self.list_ctrl.get_selected_data()
        if selected_data:
            with wx.FileDialog(self, self.language_handler.get_translation("Save_the_file"), wildcard="PKG Files (*.dmg)|*.dmg", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
                if dlg.ShowModal() == wx.ID_CANCEL:
                    return
                file_path = dlg.GetPath()
            url = selected_data['url']
            DPF_Window = DownloadProgressFrame(self, title=self.language_handler.get_translation("Download_progress"), url=url, file_path=file_path)
            DPF_Window.Show()
        else:
            wx.MessageBox(self.language_handler.get_translation("Please_select_a_KDK_version_to_download."),self.language_handler.get_translation("Guide"), wx.OK | wx.ICON_INFORMATION)
