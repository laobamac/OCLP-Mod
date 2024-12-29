"""
gui_macos_installer_flash.py: macOS Installer Flash Frame
"""

import wx
import time
import logging
import plistlib
import tempfile
import threading
import subprocess
import re
import os

from pathlib import Path

from .. import constants

from ..datasets import os_data
from ..volume   import generate_copy_arguments

from ..wx_gui import (
    gui_main_menu,
    gui_build,
    gui_support
)
from ..support import (
    macos_installer_handler,
    utilities,
    network_handler,
    kdk_handler,
    metallib_handler,
    subprocess_wrapper
)


class DMGFlashFrame(wx.Frame):

    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None):
        logging.info("Initializing macOS Installer Flash Frame")
        super(DMGFlashFrame, self).__init__(parent, title=title, size=(350, 200), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, global_constants).generate()

        self.constants: constants.Constants = global_constants
        self.title: str = title

        self.available_installers_local: dict = {}
        self.available_disks: dict = {}
        self.prepare_result: bool = False

        self.progress_bar_animation: gui_support.GaugePulseCallback = None

        self.frame_modal: wx.Dialog = None

        #self._generate_elements()
        #self.Centre()
        #self.Show()
        #self._choose_dmg_file()



    def _generate_elements(self) -> None:
        title_label = wx.StaticText(self, label="选择本地的DMG镜像", pos=(-1,1))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)
        


    def _choose_dmg_file(self) -> None:
        wildcard = "DMG 文件 (*.dmg)|*.dmg"
        dialog = wx.FileDialog(
        None, message="选择一个DMG镜像", wildcard=wildcard, style=wx.FD_OPEN
    )

        if dialog.ShowModal() == wx.ID_OK: 
            file_path = dialog.GetPath() 
            logging.info(f"选择的DMG文件路径: {file_path}")
            self.on_select(file_path)
            return file_path
        else:
            logging.info("未选择文件")
            self.on_return_to_main_menu()
        dialog.Destroy()
        


    def on_select(self, path) -> None:
       
        # Fetching information on local disks
        title_label = wx.StaticText(self, label="取回本地硬盘信息", pos=(-1,1))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Progress bar
        progress_bar = wx.Gauge(self, range=100, pos=(-1, 30), size=(200, 30))
        progress_bar.Centre(wx.HORIZONTAL)

        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # Set size of frame
        self.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))

        # Fetch local disks
        def _fetch_disks():
            self.available_disks = macos_installer_handler.InstallerCreation().list_disk_to_format()

            # Need to clean up output on pre-Sierra
            # Disk images are mixed in with regular disks (ex. payloads.dmg)
            ignore = ["disk image", "read-only", "virtual"]
            for disk in self.available_disks.copy():
                if any(string in self.available_disks[disk]['name'].lower() for string in ignore):
                    del self.available_disks[disk]


        thread = threading.Thread(target=_fetch_disks)
        thread.start()

        while thread.is_alive():
            wx.Yield()

        self.frame_modal = wx.Dialog(self, title=self.title, size=(350, 200))

        # Title: Select local disk
        title_label = wx.StaticText(self.frame_modal, label="选择本地硬盘", pos=(-1,5))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Label: Selected USB will be erased, please backup any data
        warning_label = wx.StaticText(self.frame_modal, label="选择的U盘会格式化！", pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5))
        warning_label.SetFont(gui_support.font_factory(11, wx.FONTWEIGHT_NORMAL))
        warning_label.Centre(wx.HORIZONTAL)

        # List of disks
        if self.available_disks:
            spacer = 5
            entries = len(self.available_disks)
            logging.info("可用硬盘:")
            for disk in self.available_disks:
                logging.info(f" - {disk}: {self.available_disks[disk]['name']} - {utilities.human_fmt(self.available_disks[disk]['size'])}")
                disk_button = wx.Button(self.frame_modal, label=f"{disk}: {self.available_disks[disk]['name']} - {utilities.human_fmt(self.available_disks[disk]['size'])}", pos=(-1, warning_label.GetPosition()[1] + warning_label.GetSize()[1] + spacer), size=(300, 30))
                disk_button.Bind(wx.EVT_BUTTON, lambda event, temp=disk: self.on_select_disk(self.available_disks[temp], path))
                disk_button.Centre(wx.HORIZONTAL)
                if entries == 1:
                    disk_button.SetDefault()
                spacer += 25
        else:
            disk_button = wx.StaticText(self.frame_modal, label="未找到可用硬盘", pos=(-1, warning_label.GetPosition()[1] + warning_label.GetSize()[1] + 5))
            disk_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
            disk_button.Centre(wx.HORIZONTAL)

        # Search for disks again
        search_button = wx.Button(self.frame_modal, label="再次扫描", pos=(-1, disk_button.GetPosition()[1] + disk_button.GetSize()[1]), size=(150, 30))
        search_button.Bind(wx.EVT_BUTTON, lambda event, temp=path: self.on_select(temp))
        search_button.Centre(wx.HORIZONTAL)

        # Button: Return to Main Menu
        cancel_button = wx.Button(self.frame_modal, label="返回", pos=(-1, search_button.GetPosition()[1] + search_button.GetSize()[1] - 10), size=(150, 30))
        cancel_button.Bind(wx.EVT_BUTTON, self.on_return_to_main_menu)
        cancel_button.Centre(wx.HORIZONTAL)

        # Set size of frame
        self.frame_modal.SetSize((-1, cancel_button.GetPosition()[1] + cancel_button.GetSize()[1] + 40))

        progress_bar_animation.stop_pulse()

        self.frame_modal.ShowWindowModal()


    def on_select_disk(self, disk: dict, path) -> None:
        answer = wx.MessageBox(f"确定抹掉 '{disk['name']}'?\n会格式化,无法回退.", "继续", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        if answer != wx.YES:
            return

        logging.info(f"你选择了: {disk['name']}")

        self.frame_modal.Destroy()

        for child in self.GetChildren():
            child.Destroy()

        self.SetSize((450, -1))

        file_name = os.path.basename(path)
        print(f"文件名: {file_name}")

        match = re.search(r'macOS\s+([\w\s]+)\+([\d.]+)', file_name)
 
        if match:
           os_name = match.group(1)
           os_version = match.group(2) 
           result = f"macOS {os_name} {os_version}"
           logging.info(f"提取的版本信息: {result}")
           return result
        else:
           logging.info("未找到匹配的版本信息")

        # Title: Creating Installer: {installer_name}
        title_label = wx.StaticText(self, label=f"正在创建: {match}", pos=(-1,1))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Label: Creating macOS installers can take 30min+ on slower USB drives.
        warning_label = wx.StaticText(self, label="根据设备速度，可能需要30min甚至更久.", pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 5))
        warning_label.SetFont(gui_support.font_factory(11, wx.FONTWEIGHT_NORMAL))
        warning_label.Centre(wx.HORIZONTAL)

        # Label: We will notify you when the installer is ready.
        warning_label = wx.StaticText(self, label="可以去做其他事情，比如看看SimpleHac资源社，完成会提示你.", pos=(-1, warning_label.GetPosition()[1] + warning_label.GetSize()[1] + 5))
        warning_label.SetFont(gui_support.font_factory(11, wx.FONTWEIGHT_NORMAL))
        warning_label.Centre(wx.HORIZONTAL)

        # Label: Bytes Written: 0 MB
        bytes_written_label = wx.StaticText(self, label="已写入: 0.00 MB", pos=(-1, warning_label.GetPosition()[1] + warning_label.GetSize()[1] + 5))
        bytes_written_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        bytes_written_label.Centre(wx.HORIZONTAL)

        # Progress bar
        progress_bar = wx.Gauge(self, range=100, pos=(-1, bytes_written_label.GetPosition()[1] + bytes_written_label.GetSize()[1] + 5), size=(300, 30))
        progress_bar.Centre(wx.HORIZONTAL)

        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # Set size of frame
        self.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))
        self.Show()

        progress_bar_animation.stop_pulse()

        # /dev/diskX -> diskX
        root_disk = disk['identifier'][5:]
        initial_bytes_written = float(utilities.monitor_disk_output(root_disk))
        self.result = False
        def _flash():
            logging.info(f"Flashing {path} to {root_disk}")
            self.result = self._flash_installer(root_disk)

        thread = threading.Thread(target=_flash)
        thread.start()

        # Wait for installer to be created
        while thread.is_alive():
            try:
                total_bytes_written = float(utilities.monitor_disk_output(root_disk))
            except:
                total_bytes_written = initial_bytes_written
            bytes_written = total_bytes_written - initial_bytes_written
            wx.CallAfter(bytes_written_label.SetLabel, f"已写入: {bytes_written:.2f} MB")
            try:
                bytes_written = int(bytes_written)
            except:
                bytes_written = 0
            wx.CallAfter(progress_bar.SetValue, bytes_written)
            wx.Yield()

        if self.result is False:
            logging.error("Failed to flash installer, cannot continue.")
            self.on_return_to_main_menu()
            return

        # Next verify the installer
        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        bytes_written_label.SetLabel("验证安装器...")
        error_message = self._validate_installer_pkg(disk['identifier'])

        progress_bar_animation.stop_pulse()

        if error_message != "":
            progress_bar.SetValue(0)
            wx.MessageBox(f"Failed to validate installer, cannot continue.\n This can generally happen due to a faulty USB drive, as flashing is an intensive process that can trigger hardware faults not normally seen. \n\n{error_message}", "Corrupted Installer!", wx.OK | wx.ICON_ERROR)
            self.on_return_to_main_menu()
            return

        progress_bar.SetValue(estimated_size)

        if gui_support.CheckProperties(self.constants).host_can_build() is False:
            wx.MessageBox("安装程序创建成功！如果要将 OpenCore 安装到此 USB，则需要在设置中更改目标机型", "已成功创建 macOS 安装器！", wx.OK | wx.ICON_INFORMATION)
            self.on_return_to_main_menu()
            return

        answer = wx.MessageBox("安装程序创建成功，是否要继续并将 OpenCore 安装到此磁盘？", "已成功创建 macOS 安装器！", wx.YES_NO | wx.ICON_QUESTION)
        if answer != wx.YES:
            self.on_return_to_main_menu()
            return

        # Install OpenCore
        self.Hide()
        gui_build.BuildFrame(
            parent=None,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetPosition()
        )
        self.Destroy()

    def _flash_installer(self, disk) -> bool:
        return()


    def on_return_to_main_menu(self, event: wx.Event = None):
        if self.frame_modal:
            self.frame_modal.Hide()
        if self:
            if isinstance(self, wx.Frame):
                self.Hide()
        main_menu_frame = gui_main_menu.MainFrame(
            None,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.GetScreenPosition()
        )
        main_menu_frame.Show()
        if self.frame_modal:
            self.frame_modal.Destroy()
        if self:
            if isinstance(self, wx.Frame):
                self.Destroy()
