"""
gui_sys_patch_start.py: 正在安装驱动补丁 窗口
"""

import wx
import sys
import time
import logging
import plistlib
import traceback
import threading
import subprocess

from pathlib import Path

from .. import constants

from ..datasets import os_data

from ..support import (
    kdk_handler,
    metallib_handler
)
from ..sys_patch import (
    sys_patch,
)
from ..wx_gui import (
    gui_main_menu,
    gui_support,
    gui_download,
)

from ..sys_patch.patchsets import HardwarePatchsetDetection, HardwarePatchsetSettings



class SysPatchStartFrame(wx.Frame):
    """
    Create a frame for 正在安装驱动补丁
    Uses a Modal Dialog for smoother transition from other frames
    """
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None, patches: dict = {}):
        logging.info("初始化 安装驱动补丁 窗口")

        self.title = title
        self.constants: constants.Constants = global_constants
        self.frame_modal: wx.Dialog = None
        self.return_button: wx.Button = None
        self.available_patches: bool = False
        self.patches: dict = patches

        super(SysPatchStartFrame, self).__init__(parent, title=title, size=(350, 200), style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))
        gui_support.GenerateMenubar(self, self.constants).generate()
        self.Centre()

        if self.patches == {}:
            self.patches = HardwarePatchsetDetection(constants=self.constants).device_properties


    def _kdk_download(self, frame: wx.Frame = None) -> bool:
        frame = self if not frame else frame

        logging.info("KDK missing, generating KDK download frame")

        header = wx.StaticText(frame, label="正在下载KDK", pos=(-1,5))
        header.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        header.Centre(wx.HORIZONTAL)

        subheader = wx.StaticText(frame, label="取回KDK数据库...", pos=(-1, header.GetPosition()[1] + header.GetSize()[1] + 5))
        subheader.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        subheader.Centre(wx.HORIZONTAL)

        progress_bar = wx.Gauge(frame, range=100, pos=(-1, subheader.GetPosition()[1] + subheader.GetSize()[1] + 5), size=(250, 20))
        progress_bar.Centre(wx.HORIZONTAL)

        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # Set size of frame
        frame.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 35))
        frame.Show()

        # Generate KDK object
        self.kdk_obj: kdk_handler.KernelDebugKitObject = None
        def _kdk_thread_spawn():
            self.kdk_obj = kdk_handler.KernelDebugKitObject(self.constants, self.constants.detected_os_build, self.constants.detected_os_version)

        kdk_thread = threading.Thread(target=_kdk_thread_spawn)
        kdk_thread.start()

        gui_support.wait_for_thread(kdk_thread)

        if self.kdk_obj.success is False:
            progress_bar_animation.stop_pulse()
            progress_bar.SetValue(0)
            wx.MessageBox(f"KDK 下载失败: {self.kdk_obj.error_msg}", "Error", wx.OK | wx.ICON_ERROR)
            return False

        kdk_download_obj = self.kdk_obj.retrieve_download()
        if not kdk_download_obj:
            # KDK is already downloaded
            return True

        gui_download.DownloadFrame(
            self,
            title=self.title,
            global_constants=self.constants,
            download_obj=kdk_download_obj,
            item_name=f"KDK Build {self.kdk_obj.kdk_url_build}"
        )
        if kdk_download_obj.download_complete is False:
            return False

        logging.info("KDK download complete, validating with hdiutil")
        header.SetLabel(f"Validating KDK: {self.kdk_obj.kdk_url_build}")
        header.Centre(wx.HORIZONTAL)

        subheader.SetLabel("Checking if checksum is valid...")
        subheader.Centre(wx.HORIZONTAL)
        wx.Yield()

        progress_bar_animation.stop_pulse()

        if self.kdk_obj.validate_kdk_checksum() is False:
            progress_bar.SetValue(0)
            logging.error("KDK checksum validation failed")
            logging.error(self.kdk_obj.error_msg)
            msg = wx.MessageDialog(frame, f"KDK MD5不匹配: {self.kdk_obj.error_msg}", "Error", wx.OK | wx.ICON_ERROR)
            msg.ShowModal()
            return False

        progress_bar.SetValue(100)

        logging.info("KDK download complete")

        for child in frame.GetChildren():
            child.Destroy()

        return True


    def _metallib_download(self, frame: wx.Frame = None) -> bool:
        frame = self if not frame else frame

        logging.info("MetallibSupportPkg missing, generating Metallib download frame")

        header = wx.StaticText(frame, label="正在下载 Metal Libraries", pos=(-1,5))
        header.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        header.Centre(wx.HORIZONTAL)

        subheader = wx.StaticText(frame, label="取回 MetallibSupportPkg 数据库...", pos=(-1, header.GetPosition()[1] + header.GetSize()[1] + 5))
        subheader.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        subheader.Centre(wx.HORIZONTAL)

        progress_bar = wx.Gauge(frame, range=100, pos=(-1, subheader.GetPosition()[1] + subheader.GetSize()[1] + 5), size=(250, 20))
        progress_bar.Centre(wx.HORIZONTAL)

        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # Set size of frame
        frame.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 35))
        frame.Show()

        self.metallib_obj: metallib_handler.MetalLibraryObject = None
        def _metallib_thread_spawn():
            self.metallib_obj = metallib_handler.MetalLibraryObject(self.constants, self.constants.detected_os_build, self.constants.detected_os_version)

        metallib_thread = threading.Thread(target=_metallib_thread_spawn)
        metallib_thread.start()

        gui_support.wait_for_thread(metallib_thread)

        if self.metallib_obj.success is False:
            progress_bar_animation.stop_pulse()
            progress_bar.SetValue(0)
            wx.MessageBox(f"Metallib 下载失败: {self.metallib_obj.error_msg}", "Error", wx.OK | wx.ICON_ERROR)
            return False

        self.metallib_download_obj = self.metallib_obj.retrieve_download()
        if not self.metallib_download_obj:
            # Metallib is already downloaded
            return True

        gui_download.DownloadFrame(
            self,
            title=self.title,
            global_constants=self.constants,
            download_obj=self.metallib_download_obj,
            item_name=f"Metallib Build {self.metallib_obj.metallib_url_build}"
        )
        if self.metallib_download_obj.download_complete is False:
            return False

        logging.info("Metallib download complete, installing Metallib PKG")

        header.SetLabel(f"正在安装Metallib: {self.metallib_obj.metallib_url_build}")
        header.Centre(wx.HORIZONTAL)

        subheader.SetLabel("正在安装Metallib...")
        subheader.Centre(wx.HORIZONTAL)

        self.result = False
        def _install_metallib():
            self.result = self.metallib_obj.install_metallib()

        install_thread = threading.Thread(target=_install_metallib)
        install_thread.start()

        gui_support.wait_for_thread(install_thread)

        if self.result is False:
            progress_bar_animation.stop_pulse()
            progress_bar.SetValue(0)
            wx.MessageBox(f"Metallib 安装失败: {self.metallib_obj.error_msg}", "Error", wx.OK | wx.ICON_ERROR)
            return False

        progress_bar_animation.stop_pulse()
        progress_bar.SetValue(100)

        logging.info("Metallib installation complete")

        for child in frame.GetChildren():
            child.Destroy()

        return True


    def _generate_modal(self, patches: dict = {}, variant: str = "正在安装驱动补丁"):
        """
        Create UI for 正在安装驱动补丁/unpatching
        """
        supported_variants = ["正在安装驱动补丁", "正在卸载驱动补丁"]
        if variant not in supported_variants:
            logging.error(f"Unsupported variant: {variant}")
            return

        self.frame_modal.Close() if self.frame_modal else None

        dialog = wx.Dialog(self, title=self.title, size=(400, 200))

        # Title
        title = wx.StaticText(dialog, label=variant, pos=(-1, 10))
        title.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title.Centre(wx.HORIZONTAL)

        if variant == "正在安装驱动补丁":
            # Label
            label = wx.StaticText(dialog, label="将会安装以下补丁:", pos=(-1, title.GetPosition()[1] + 30))
            label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            label.Centre(wx.HORIZONTAL)


            # Get longest patch label, then create anchor for patch labels
            longest_patch = ""
            for patch in patches:
                if (not patch.startswith("设置") and not patch.startswith("验证") and patches[patch] is True):
                    if len(patch) > len(longest_patch):
                        longest_patch = patch

            anchor = wx.StaticText(dialog, label=longest_patch, pos=(label.GetPosition()[0], label.GetPosition()[1] + 20))
            anchor.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            anchor.Centre(wx.HORIZONTAL)
            anchor.Hide()

            # Labels
            i = 0
            logging.info("Available patches:")
            for patch in patches:
                if (not patch.startswith("设置") and not patch.startswith("验证") and patches[patch] is True):
                    logging.info(f"- {patch}")
                    patch_label = wx.StaticText(dialog, label=f"- {patch}", pos=(anchor.GetPosition()[0], label.GetPosition()[1] + 20 + i))
                    patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                    i = i + 20

            if i == 20:
                patch_label.SetLabel(patch_label.GetLabel().replace("-", ""))
                patch_label.Centre(wx.HORIZONTAL)

            elif i == 0:
                patch_label = wx.StaticText(dialog, label="未能应用任何补丁", pos=(label.GetPosition()[0], label.GetPosition()[1] + 20))
                patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                patch_label.Centre(wx.HORIZONTAL)
        else:
            patch_label = wx.StaticText(dialog, label="恢复到最近快照", pos=(-1, title.GetPosition()[1] + 30))
            patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            patch_label.Centre(wx.HORIZONTAL)


        # Text box
        text_box = wx.TextCtrl(dialog, pos=(10, patch_label.GetPosition()[1] + 30), size=(380, 400), style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_RICH2)
        text_box.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        text_box.Centre(wx.HORIZONTAL)
        self.text_box = text_box

        # Button: Return to Main Menu
        return_button = wx.Button(dialog, label="返回", pos=(10, text_box.GetPosition()[1] + text_box.GetSize()[1] + 5), size=(150, 30))
        return_button.Bind(wx.EVT_BUTTON, self.on_return_to_main_menu)
        return_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        return_button.Centre(wx.HORIZONTAL)
        self.return_button = return_button

        # Set frame size
        dialog.SetSize((-1, return_button.GetPosition().y + return_button.GetSize().height + 33))
        self.frame_modal = dialog
        dialog.ShowWindowModal()


    def start_root_patching(self):
        logging.info("Starting 正在安装驱动补丁")

        while gui_support.PayloadMount(self.constants, self).is_unpack_finished() is False:
            wx.Yield()
            time.sleep(self.constants.thread_sleep_interval)

        if self.patches[HardwarePatchsetSettings.KERNEL_DEBUG_KIT_REQUIRED] is True:
            if self._kdk_download(self) is False:
                sys.exit(1)

        if self.patches[HardwarePatchsetSettings.METALLIB_SUPPORT_PKG_REQUIRED] is True:
            if self._metallib_download(self) is False:
                sys.exit(1)

        self._generate_modal(self.patches, "正在安装驱动补丁")
        self.return_button.Disable()

        thread = threading.Thread(target=self._start_root_patching, args=(self.patches,))
        thread.start()

        gui_support.wait_for_thread(thread)

        self._post_patch()
        self.return_button.Enable()


    def _start_root_patching(self, patches: dict):
        logger = logging.getLogger()
        logger.addHandler(gui_support.ThreadHandler(self.text_box))
        try:
            sys_patch.PatchSysVolume(self.constants.computer.real_model, self.constants, patches).start_patch()
        except:
            logging.error("An internal error occurred while running the Root Patcher:\n")
            logging.error(traceback.format_exc())
        logger.removeHandler(logger.handlers[2])


    def revert_root_patching(self):
        logging.info("Reverting root patches")

        self._generate_modal(self.patches, "正在卸载驱动补丁")
        self.return_button.Disable()

        thread = threading.Thread(target=self._revert_root_patching, args=(self.patches,))
        thread.start()

        while thread.is_alive():
            wx.Yield()

        self._post_patch()
        self.return_button.Enable()


    def _revert_root_patching(self, patches: dict):
        logger = logging.getLogger()
        logger.addHandler(gui_support.ThreadHandler(self.text_box))
        try:
            sys_patch.PatchSysVolume(self.constants.computer.real_model, self.constants, patches).start_unpatch()
        except:
            logging.error("An internal error occurred while running the Root Patcher:\n")
            logging.error(traceback.format_exc())
        logger.removeHandler(logger.handlers[2])


    def on_return_to_main_menu(self, event: wx.Event = None):
        # Get frame from event
        frame_modal: wx.Dialog = event.GetEventObject().GetParent()
        frame: wx.Frame = frame_modal.Parent
        frame_modal.Hide()
        frame.Hide()

        main_menu_frame = gui_main_menu.MainFrame(
            None,
            title=self.title,
            global_constants=self.constants,
        )
        main_menu_frame.Show()
        frame.Destroy()


    def on_return_dismiss(self, event: wx.Event = None):
        self.frame_modal.Hide()
        self.frame_modal.Destroy()


    def _post_patch(self):
        if self.constants.root_patcher_succeeded is False:
            return

        if self.constants.needs_to_open_preferences is False:
            gui_support.RestartHost(self.frame_modal).restart(message="驱动补丁操作成功!\n\n现在重启吗?")
            return

        if self.constants.detected_os >= os_data.os_data.ventura:
            gui_support.RestartHost(self.frame_modal).restart(message="驱动补丁操作成功!\n如果系统提示您打开“系统设置”以授权新的 Kext，可以忽略此项。重新启动后，您的系统已准备就绪.\n\n现在重启吗?")
            return

        # Create dialog box to open System Preferences -> Security and Privacy
        self.popup = wx.MessageDialog(
            self.frame_modal,
            "我们刚刚完成了到根卷的补丁安装！\n\n但是，Apple 要求用户手动批准已安装的内核扩展，然后才能在下次重新启动之前使用它们。\n\n您要打开系统偏好设置吗？",
            "Open System Preferences?",
            wx.YES_NO | wx.ICON_INFORMATION
        )
        self.popup.SetYesNoLabels("打开系统设置", "忽略")
        answer = self.popup.ShowModal()
        if answer == wx.ID_YES:
            output =subprocess.run(
                [
                    "/usr/bin/osascript", "-e",
                    'tell app "System Preferences" to activate',
                    "-e", 'tell app "System Preferences" to reveal anchor "General" of pane id "com.apple.preference.security"',
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            if output.returncode != 0:
                # Some form of fallback if unaccelerated state errors out
                subprocess.run(["/usr/bin/open", "-a", "System Preferences"])
            time.sleep(5)
            sys.exit(0)


    def _check_if_new_patches_needed(self, patches: dict) -> bool:
        """
        Checks if any new patches are needed for the user to install
        Newer users will assume the root patch menu will present missing patches.
        Thus we'll need to see if the exact same OCLP build was used already
        """

        logging.info("Checking if new patches are needed")

        if self.constants.commit_info[0] in ["Running from source", "Built from source"]:
            return True

        if self.constants.computer.oclp_sys_url != self.constants.commit_info[2]:
            # If commits are different, assume patches are as well
            return True

        oclp_plist = "/System/Library/CoreServices/oclp-mod.plist"
        if not Path(oclp_plist).exists():
            # If it doesn't exist, no patches were ever installed
            # ie. all patches applicable
            return True

        oclp_plist_data = plistlib.load(open(oclp_plist, "rb"))
        for patch in patches:
            if (not patch.startswith("设置") and not patch.startswith("验证") and patches[patch] is True):
                # Patches should share the same name as the plist key
                # See sys_patch/patchsets/base.py for more info
                if patch.split(": ")[1] not in oclp_plist_data:
                    logging.info(f"- Patch {patch} not installed")
                    return True

        logging.info("No new patches detected for system")
        return False
