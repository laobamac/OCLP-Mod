"""
gui_download.py: Generate UI for downloading files
"""

import wx
import logging, time

from .. import constants

from ..wx_gui import gui_support
from .. import constants
from ..languages.language_handler import LanguageHandler

from ..support import (
    network_handler,
    utilities
)


class DownloadFrame(wx.Frame):
    """
    Update provided frame with download stats
    """
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, download_obj: network_handler.DownloadObject, item_name: str, download_icon = None) -> None:
        logging.info("Initializing Download Frame")
        self.constants: constants.Constants = global_constants
        self.language_handler = LanguageHandler(self.constants)
        self.title: str = title
        self.parent: wx.Frame = parent
        self.download_obj: network_handler.DownloadObject = download_obj
        self.item_name: str = item_name
        if download_icon:
            self.download_icon: str = download_icon
        else:
            self.download_icon: str = "/System/Library/CoreServices/Installer.app/Contents/Resources/package.icns"

        self.user_cancelled: bool = False

        self.frame_modal = wx.Dialog(parent, title=title, size=(400, 200))

        self._generate_elements(self.frame_modal)


    def _generate_elements(self, frame: wx.Dialog = None) -> None:
        """
        Generate elements for download frame
        """

        frame = self if not frame else frame
        icon = self.download_icon
        icon = wx.StaticBitmap(frame, bitmap=wx.Bitmap(icon, wx.BITMAP_TYPE_ICON), pos=(-1, 20))
        icon.SetSize((100, 100))
        icon.Centre(wx.HORIZONTAL)

        title_label = wx.StaticText(frame, label=f"{self.language_handler.get_translation('Downloading:')} {self.item_name}", pos=(-1,icon.GetPosition()[1] + icon.GetSize()[1] + 20))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        progress_bar = wx.Gauge(frame, range=100, pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5), size=(300, 20), style=wx.GA_SMOOTH|wx.GA_PROGRESS)
        progress_bar.Centre(wx.HORIZONTAL)

        label_amount = wx.StaticText(frame, label=self.language_handler.get_translation("Ready_to_download"), pos=(-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1]))
        label_amount.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        label_amount.Centre(wx.HORIZONTAL)

        return_button = wx.Button(frame, label=self.language_handler.get_translation("back"), pos=(-1, label_amount.GetPosition()[1] + label_amount.GetSize()[1] + 10))
        return_button.Bind(wx.EVT_BUTTON, lambda event: self.terminate_download())
        return_button.Centre(wx.HORIZONTAL)

        # Set size of frame
        frame.SetSize((-1, return_button.GetPosition()[1] + return_button.GetSize()[1] + 40))
        frame.ShowWindowModal()

        self.download_obj.download()
        while self.download_obj.is_active():

            percentage: int = round(self.download_obj.get_percent())
            if percentage == 0:
                percentage = 1

            if percentage == -1:
                amount_str = f"{utilities.human_fmt(self.download_obj.downloaded_file_size)} {self.language_handler.get_translation("Downloaded")}， ({utilities.human_fmt(self.download_obj.get_speed())}/s)"
                progress_bar.Pulse()
            else:
                amount_str = f"{self.language_handler.get_translation("There_is_still")} {utilities.seconds_to_readable_time(self.download_obj.get_time_remaining())} - {utilities.human_fmt(self.download_obj.downloaded_file_size)} {self.language_handler.get_translation("at")} {utilities.human_fmt(self.download_obj.total_file_size)}{self.language_handler.get_translation("center")}， {self.language_handler.get_translation("speed")} ({utilities.human_fmt(self.download_obj.get_speed())}/s)"
                progress_bar.SetValue(int(percentage))

            label_amount.SetLabel(amount_str)
            label_amount.Centre(wx.HORIZONTAL)

            wx.Yield()
            time.sleep(self.constants.thread_sleep_interval)

        if self.download_obj.download_complete is False and self.user_cancelled is False:
            wx.MessageBox(f"{self.language_handler.get_translation("Download_failed")}: \n{self.download_obj.error_msg}", self.language_handler.get_translation("Error"), wx.OK | wx.ICON_ERROR)

        progress_bar.Destroy()
        frame.Destroy()


    def terminate_download(self) -> None:
        """
        Terminate download
        """
        if wx.MessageBox(self.language_handler.get_translation("The_download_will_be_canceled,are_you_sure?"), self.language_handler.get_translation("Cancel_download"), wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT) == wx.YES:
            logging.info("你取消了下载任务")
            self.user_cancelled = True
            self.download_obj.stop()


