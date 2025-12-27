import wx
import threading
import time
import os
import json
from typing import List, Dict, Optional, Any

from .. import constants
from ..constants import Constants
from ..support import network_handler
from ..support.network_handler import DownloadObject

# 常量定义
OMAPIv1: str = "https://next.oclpapi.simplehac.cn/"
OMAPIv2: str = "https://subsequent.oclpapi.simplehac.cn/"
KDK_API_LINK_ORIGIN: str = "https://dortania.github.io/KdkSupportPkg/manifest.json"
KDK_INFO_JSON: str = "KdkSupportPkg/manifest.json"

class DownloadProgressFrame(wx.Dialog):
    """下载进度对话框"""
    
    def __init__(self, parent, title: str, url: str, file_path: str, file_size: int = 0):
        style = wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        super().__init__(parent, title=title, size=(530, 265), style=style)
        
        self.parent = parent
        self.url = url
        self.file_path = file_path
        self.file_size = file_size
        self.downloading = True
        self.download_complete = False
        self.download_object: Optional[DownloadObject] = None
        self.download_thread: Optional[threading.Thread] = None
        self.timer: Optional[wx.Timer] = None
        
        self._init_ui()
        self._start_download()

    def _init_ui(self) -> None:
        """初始化用户界面"""
        panel = wx.Panel(self)
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
        size_str = self._format_file_size(self.file_size) if self.file_size > 0 else "计算中..."
        self.size_value = wx.StaticText(panel, label=size_str)
        info_sizer.Add(size_label, (1, 0), flag=wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
        info_sizer.Add(self.size_value, (1, 1), flag=wx.EXPAND)
        
        info_sizer.AddGrowableCol(1)
        main_sizer.Add(info_sizer, 0, wx.EXPAND | wx.ALL, 15)
        
        # 进度条区域
        progress_sizer = self._create_progress_section(panel)
        main_sizer.Add(progress_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # 按钮区域
        button_sizer = self._create_button_section(panel)
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(main_sizer)
        
        # 绑定事件
        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_SHOW, self._on_show)

    def _create_progress_section(self, parent) -> wx.BoxSizer:
        """创建进度显示区域"""
        progress_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 进度百分比和详细信息
        progress_info_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.percent_label = wx.StaticText(parent, label="0%  ")
        percent_font = wx.Font(20, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        self.percent_label.SetFont(percent_font)
        progress_info_sizer.Add(self.percent_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 10)
        
        self.detail_label = wx.StaticText(parent, label="准备下载...")
        progress_info_sizer.Add(self.detail_label, 1, wx.ALIGN_CENTER_VERTICAL)
        
        progress_sizer.Add(progress_info_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        # 进度条
        self.progress_bar = wx.Gauge(parent, range=100, size=(460, 20))
        self.progress_bar.SetValue(0)
        progress_sizer.Add(self.progress_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        
        return progress_sizer

    def _create_button_section(self, parent) -> wx.BoxSizer:
        """创建按钮区域"""
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer()
        
        self.cancel_button = wx.Button(parent, label="取消下载", size=(100, 35))
        self.cancel_button.Bind(wx.EVT_BUTTON, self._on_cancel)
        button_sizer.Add(self.cancel_button, 0, wx.ALL, 5)
        
        return button_sizer

    def _on_show(self, event) -> None:
        """窗口显示时触发布局刷新"""
        if event.IsShown():
            wx.CallLater(100, self._force_layout_refresh)
        event.Skip()

    def _force_layout_refresh(self) -> None:
        """强制刷新布局"""
        self.Layout()
        self.Refresh()
        current_size = self.GetSize()
        self.SetSize((current_size[0] + 1, current_size[1]))
        wx.CallLater(50, lambda: self.SetSize(current_size))

    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.2f} {size_names[i]}"

    def _start_download(self) -> None:
        """开始下载"""
        self.download_object = DownloadObject(self.url, self.file_path, size=str(self.file_size))
        
        # 启动下载线程
        self.download_thread = threading.Thread(target=self._download_file)
        self.download_thread.daemon = True
        self.download_thread.start()

        # 启动定时器更新界面
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._update_ui, self.timer)
        self.timer.Start(300)  # 每300ms更新一次

        self.Centre()

    def _download_file(self) -> None:
        """使用 DownloadObject 进行下载"""
        try:
            self.download_object.download(spawn_thread=False, display_progress=False)
            
            # 等待下载完成或出错
            while self.download_object.is_active() and self.downloading:
                time.sleep(0.3)
            
            if self.downloading:
                if self.download_object.download_complete:
                    self.download_complete = True
                    wx.CallAfter(self._on_download_complete)
                else:
                    wx.CallAfter(self._on_download_error, self.download_object.error_msg)
                    
        except Exception as e:
            if self.downloading:  # 只在未取消的情况下显示错误
                wx.CallAfter(self._on_download_error, str(e))
        
        wx.CallAfter(self.timer.Stop)

    def _update_ui(self, event) -> None:
        """更新界面显示"""
        if not self.download_object or not self.download_object.is_active():
            return
            
        # 获取下载进度信息
        percent = self.download_object.get_percent()
        downloaded_bytes = self.download_object.downloaded_file_size
        total_bytes = self.download_object.total_file_size
        speed = self.download_object.get_speed()
        
        # 更新进度条和百分比
        if percent >= 0:
            progress_value = int(percent)
            self.progress_bar.SetValue(progress_value)
            self.percent_label.SetLabel(f"{progress_value}%  ")
        else:
            # 如果无法获取百分比，使用伪进度
            current_value = self.progress_bar.GetValue()
            if current_value < 90:
                self.progress_bar.SetValue(current_value + 1)
                self.percent_label.SetLabel(f"{current_value + 1}%")
        
        # 格式化显示数据
        downloaded_str = self._format_file_size(downloaded_bytes)
        total_str = self._format_file_size(total_bytes) if total_bytes > 0 else "未知"
        speed_str = self._format_file_size(speed) + "/s"
        
        # 更新详细信息标签
        detail_text = f"速度: {speed_str}  已下载: {downloaded_str} / {total_str}"
        self.detail_label.SetLabel(detail_text)

    def _on_download_complete(self) -> None:
        """下载完成处理"""
        wx.MessageBox(f"下载完成！\n文件保存至: {self.file_path}", "成功", wx.OK | wx.ICON_INFORMATION)
        self.EndModal(wx.ID_OK)

    def _on_download_error(self, error_msg: str) -> None:
        """下载错误处理"""
        wx.MessageBox(f"下载失败: {error_msg}", "错误", wx.OK | wx.ICON_ERROR)
        self.EndModal(wx.ID_CANCEL)

    def _on_cancel(self, event) -> None:
        """取消下载"""
        self.downloading = False
        if self.download_object:
            self.download_object.stop()
        self.EndModal(wx.ID_CANCEL)

    def _on_close(self, event) -> None:
        """窗口关闭处理"""
        self.downloading = False
        if self.timer:
            self.timer.Stop()
        if self.download_object:
            self.download_object.stop()
        if self.download_thread and self.download_thread.is_alive():
            self.download_thread.join(timeout=1.0)
        self.Destroy()


class LoadingFrame(wx.Dialog):
    """加载中对话框"""
    
    def __init__(self, parent, title: str, message: str = "请稍候，正在从服务器加载数据..."):
        style = wx.STAY_ON_TOP
        super().__init__(parent, title=title, size=(350, 120), style=style)
        
        self.timer: Optional[wx.Timer] = None
        self.progress_value: int = 0
        self.message = message
        
        self._init_ui()
        self.Centre()

    def _init_ui(self) -> None:
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
        
        desc_label = wx.StaticText(panel, label=self.message)
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
        self.Bind(wx.EVT_TIMER, self._on_timer, self.timer)
        self.timer.Start(100)

    def _on_timer(self, event) -> None:
        """更新加载动画"""
        self.progress_value = (self.progress_value + 5) % 100
        self.progress_bar.SetValue(self.progress_value)
        
    def update_message(self, message: str) -> None:
        """更新加载消息"""
        # 查找描述标签并更新文本
        for child in self.GetChildren():
            if isinstance(child, wx.Panel):
                for panel_child in child.GetChildren():
                    if isinstance(panel_child, wx.StaticText) and panel_child.GetLabel().startswith("请稍候"):
                        panel_child.SetLabel(message)
                        panel_child.Refresh()
                        break

    def close(self) -> None:
        """关闭对话框"""
        if self.timer:
            self.timer.Stop()
        self.Destroy()


class DownloadListCtrl(wx.ListCtrl):
    """下载列表控件"""
    
    def __init__(self, parent):
        super().__init__(parent, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SUNKEN)
        
        self.data: List[Dict[str, Any]] = []  # 存储每个条目的数据
        
        self._init_columns()

    def _init_columns(self) -> None:
        """初始化列"""
        self.InsertColumn(0, "版本", width=120)
        self.InsertColumn(1, "系统版本", width=150)
        self.InsertColumn(2, "文件大小", width=120)
        self.InsertColumn(3, "发布日期", width=120)
        self.InsertColumn(4, "下载链接", width=280)

    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """格式化文件大小显示"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        size = float(size_bytes)
        
        while size >= 1024 and i < len(size_names) - 1:
            size /= 1024.0
            i += 1
        
        return f"{size:.2f} {size_names[i]}"

    def SetData(self, kdk_data: List[Dict[str, Any]]) -> None:
        """设置列表数据"""
        self.data = []  # 清空旧数据
        self.DeleteAllItems()  # 清空列表显示
        
        for item in kdk_data:
            version = f"{item['build']}"
            system_version = f"macOS {item['version']}"
            file_size = self._format_file_size(item.get('fileSize', 0))
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

    def get_selected_data(self) -> Optional[Dict[str, Any]]:
        """获取选中项的数据"""
        selected_index = self.GetFirstSelected()
        if selected_index != -1:
            return self.data[selected_index]
        return None


class DownloadKDKFrame(wx.Frame):
    """KDK下载管理器主窗口"""
    
    def __init__(self, parent, global_constants: Constants):
        self.constants: constants.Constants = global_constants
        super().__init__(parent, title="KDK 下载管理器", size=(800, 600))
        
        self.loading_dialog: Optional[LoadingFrame] = None
        self.list_ctrl: Optional[DownloadListCtrl] = None
        self.refresh_button: Optional[wx.Button] = None
        self.copy_button: Optional[wx.Button] = None
        self.download_button: Optional[wx.Button] = None
        self.api_source_button: Optional[wx.Button] = None
        
        # API源状态 - 根据constants配置初始化
        self._init_api_sources()
        
        self._init_ui()
        self.Centre()
        self.Show()
        
        # 在后台线程中加载数据
        self._start_loading_data()

    def _init_api_sources(self) -> None:
        """初始化API源"""
        # 确定默认API源
        default_index = 0  # 默认使用OMAPIv2
        
        if self.constants.use_simplehacapi:
            # 使用SimpleHac API
            if self.constants.simplehacapi_url == "OMAPIv1":
                default_index = 0
            else:
                # OMAPIv2或其他
                default_index = 1
        else:
            # 不使用代理，使用原始源
            default_index = 2
        
        self.api_sources = [
            ("OMAPIv1", f"{OMAPIv1}{KDK_INFO_JSON}"),
            ("OMAPIv2", f"{OMAPIv2}{KDK_INFO_JSON}"),
            ("Github - 海外", KDK_API_LINK_ORIGIN)
        ]
        
        self.current_api_index = default_index

    def _on_switch_api_source(self, event) -> None:
        """切换API源"""
        # 创建选择对话框
        choices = []
        for i, (name, url) in enumerate(self.api_sources):
            display_name = name
            if i == self.current_api_index:
                display_name = f"✓ {name}"
            choices.append(display_name)
        
        dlg = wx.SingleChoiceDialog(
            self,
            "请选择数据源：\n\n• OMAPIv1: SimpleHac API 第一代节点\n• OMAPIv2: SimpleHac API 第二代节点\n• Github - 海外: GitHub原始数据源",
            "切换数据源",
            choices
        )
        
        if dlg.ShowModal() == wx.ID_OK:
            new_index = dlg.GetSelection()
            if new_index != self.current_api_index:
                self.current_api_index = new_index
                self._start_loading_data()
        
        dlg.Destroy()

    def _init_ui(self) -> None:
        """初始化用户界面"""
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 标题区域
        header_sizer = self._create_header_section(panel)
        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        # 分隔线
        line = wx.StaticLine(panel, style=wx.LI_HORIZONTAL)
        main_sizer.Add(line, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # 说明文字
        desc_text = wx.StaticText(panel, label="选择要下载的 Kernel Debug Kit (KDK) 版本:")
        main_sizer.Add(desc_text, 0, wx.ALL, 10)
        
        # API源显示
        source_sizer = wx.BoxSizer(wx.HORIZONTAL)
        source_label = wx.StaticText(panel, label="当前数据源:")
        source_sizer.Add(source_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        
        self.source_value = wx.StaticText(panel, label="代理源")
        source_sizer.Add(self.source_value, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 15)
        main_sizer.Add(source_sizer, 0, wx.LEFT | wx.BOTTOM, 10)
        
        # 列表控件
        self.list_ctrl = DownloadListCtrl(panel)
        main_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        
        # 按钮区域
        button_sizer = self._create_action_buttons(panel)
        main_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(main_sizer)

    def _create_header_section(self, parent) -> wx.BoxSizer:
        """创建标题区域"""
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 标题文字
        title_text = wx.StaticText(parent, label="KDK 下载管理器")
        title_font = wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        title_text.SetFont(title_font)
        header_sizer.Add(title_text, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 10)
        
        # API源切换按钮
        self.api_source_button = wx.Button(parent, label="切换数据源")
        self.api_source_button.Bind(wx.EVT_BUTTON, self._on_switch_api_source)
        header_sizer.Add(self.api_source_button, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        
        # 刷新按钮
        self.refresh_button = wx.Button(parent, label="刷新列表")
        self.refresh_button.Bind(wx.EVT_BUTTON, self._on_refresh)
        header_sizer.Add(self.refresh_button, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        
        return header_sizer

    def _create_action_buttons(self, parent) -> wx.BoxSizer:
        """创建操作按钮区域"""
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer()
        
        self.copy_button = wx.Button(parent, label="复制链接")
        self.copy_button.Bind(wx.EVT_BUTTON, self._on_copy)
        button_sizer.Add(self.copy_button, 0, wx.ALL, 5)
        
        self.download_button = wx.Button(parent, label="下载选中")
        self.download_button.Bind(wx.EVT_BUTTON, self._on_download)
        button_sizer.Add(self.download_button, 0, wx.ALL, 5)
        
        return button_sizer

    def _start_loading_data(self) -> None:
        """开始加载数据"""
        source_name = self.api_sources[self.current_api_index][0]
        message = f"请稍候，正在从{source_name}加载数据..."
        self.loading_dialog = LoadingFrame(self, "加载中", message)
        self.loading_dialog.Show()
        
        # 更新界面显示当前数据源
        self.source_value.SetLabel(source_name)
        
        threading.Thread(target=self._fetch_kdk_data_with_fallback, daemon=True).start()

    def _fetch_kdk_data_with_fallback(self) -> None:
        """获取KDK数据，支持失败后自动切换API源"""
        time.sleep(1)  # 让加载界面显示一会儿
        
        first_try_index = self.current_api_index
        second_try_index = 1 if self.current_api_index == 0 else 0
        
        # 尝试第一个API源
        first_success = self._try_fetch_api(first_try_index)
        
        if not first_success:
            # 第一个API失败，尝试第二个API源
            wx.CallAfter(self._update_loading_message, "第一个API源失败，尝试切换数据源...")
            time.sleep(1)
            
            second_success = self._try_fetch_api(second_try_index)
            
            if not second_success:
                # 两个API源都失败
                wx.CallAfter(self._show_api_error_dialog)
            else:
                # 第二个API成功，更新当前源
                self.current_api_index = second_try_index
                wx.CallAfter(self.source_value.SetLabel, self.api_sources[second_try_index][0])
        else:
            # 第一个API成功
            wx.CallAfter(self.source_value.SetLabel, self.api_sources[first_try_index][0])
        
        wx.CallAfter(self._close_loading_dialog)

    def _try_fetch_api(self, api_index: int) -> bool:
        """尝试获取指定API的数据，返回是否成功"""
        api_name, api_url = self.api_sources[api_index]
        
        try:
            wx.CallAfter(self._update_loading_message, f"正在连接{api_name}...")
            network_utils = network_handler.NetworkUtilities()
            response = network_utils.get(api_url)
            response.raise_for_status()
            kdk_data = response.json()
            
            # 验证数据格式
            if isinstance(kdk_data, list) and len(kdk_data) > 0 and 'build' in kdk_data[0]:
                wx.CallAfter(self.list_ctrl.SetData, kdk_data)
                return True
            else:
                wx.CallAfter(self._update_loading_message, f"{api_name}返回数据格式错误...")
                return False
                
        except Exception as e:
            error_msg = f"{api_name}请求失败: {e}"
            wx.CallAfter(self._update_loading_message, error_msg)
            return False

    def _update_loading_message(self, message: str) -> None:
        """更新加载对话框的消息"""
        if self.loading_dialog:
            self.loading_dialog.update_message(message)

    def _show_api_error_dialog(self) -> None:
        """显示API错误对话框"""
        dlg = wx.MessageDialog(
            self,
            "无法从任何数据源获取KDK信息。\n\n可能的原因：\n1. 网络连接问题\n2. 代理服务器故障\n3. 数据源服务不可用\n\n请检查网络连接后重试，或手动切换数据源。",
            "数据获取失败",
            wx.OK | wx.ICON_ERROR
        )
        dlg.ShowModal()
        dlg.Destroy()

    def _close_loading_dialog(self) -> None:
        """关闭加载对话框"""
        if self.loading_dialog:
            self.loading_dialog.close()
            self.loading_dialog = None

    def _on_refresh(self, event) -> None:
        """刷新列表"""
        self._start_loading_data()

    def _on_copy(self, event) -> None:
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

    def _on_download(self, event) -> None:
        """下载选中项"""
        selected_data = self.list_ctrl.get_selected_data()
        if not selected_data:
            wx.MessageBox("请选择一个 KDK 版本进行下载", "提示", wx.OK | wx.ICON_INFORMATION)
            return
            
        default_file = f"Kernel_Debug_Kit_{selected_data['version']}.dmg"
        with wx.FileDialog(self, "保存文件", defaultFile=default_file, 
                         wildcard="DMG Files (*.dmg)|*.dmg", 
                         style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                file_path = dlg.GetPath()
                url = selected_data['url']
                file_size = selected_data.get('fileSize', 0)
                
                # 显示下载进度对话框
                download_dialog = DownloadProgressFrame(self, "下载进度", url, file_path, file_size)
                download_dialog.Show()