"""
gui_sys_patch_display.py: Display root patching menu
"""

import wx
import logging
import plistlib
import threading

from pathlib import Path

from .. import constants

from ..sys_patch.patchsets import HardwarePatchsetDetection, HardwarePatchsetValidation

from ..wx_gui import (
    gui_main_menu,
    gui_support,
    gui_sys_patch_start,
)


class SysPatchDisplayFrame(wx.Frame):
    """
    Create a modal frame for displaying root patches
    """
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None):
        logging.info("Initializing Root Patch Display Frame")

        if parent:
            self.frame = parent
        else:
            super().__init__(parent, title=title, size=(360, 200), style=wx.DEFAULT_FRAME_STYLE ^ wx.RESIZE_BORDER ^ wx.MAXIMIZE_BOX)
            self.frame = self
            self.frame.Centre()

        self.title = title
        self.constants: constants.Constants = global_constants
        self.frame_modal: wx.Dialog = None
        self.return_button: wx.Button = None
        self.available_patches: bool = False
        self.init_with_parent = True if parent else False

        self.frame_modal = wx.Dialog(self.frame, title=title, size=(360, 200))

        self._generate_elements_display_patches(self.frame_modal)

        if self.constants.update_stage != gui_support.AutoUpdateStages.INACTIVE:
            if self.available_patches is False:
                gui_support.RestartHost(self.frame).restart(message="不需要任何补丁!\n\n你想现在重启来安装OpenCore吗？")


    def _generate_elements_display_patches(self, frame: wx.Frame = None) -> None:
        """
        Generate UI elements for root patch frame

        Format:
            - Title label:        Post-Install Menu
            - Label:              Available patches:
            - Labels:             {patch name}
            - Button:             Start Root Patching
            - Button:             Revert Root Patches
            - Button:             Return to Main Menu
        """
        frame = self if not frame else frame

        title_label = wx.StaticText(frame, label="安装驱动补丁", pos=(-1, 10))
        title_label.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))
        title_label.Centre(wx.HORIZONTAL)

        # Label: Fetching patches...
        available_label = wx.StaticText(frame, label="正在匹配可供安装的补丁", pos=(-1, title_label.GetPosition()[1] + title_label.GetSize()[1] + 10))
        available_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
        available_label.Centre(wx.HORIZONTAL)

        # Progress bar
        progress_bar = wx.Gauge(frame, range=100, pos=(-1, available_label.GetPosition()[1] + available_label.GetSize()[1] + 10), size=(250, 20))
        progress_bar.Centre(wx.HORIZONTAL)
        progress_bar_animation = gui_support.GaugePulseCallback(self.constants, progress_bar)
        progress_bar_animation.start_pulse()

        # Set window height
        frame.SetSize((-1, progress_bar.GetPosition()[1] + progress_bar.GetSize()[1] + 40))

        # Labels: {patch name}
        patches: dict = {}
        def _fetch_patches(self) -> None:
            nonlocal patches
            patches = HardwarePatchsetDetection(constants=self.constants).device_properties

        thread = threading.Thread(target=_fetch_patches, args=(self,))
        thread.start()

        frame.ShowWindowModal()

        gui_support.wait_for_thread(thread)

        frame.Close()

        progress_bar.Hide()
        progress_bar_animation.stop_pulse()

        available_label.SetLabel("可以安装的补丁:")
        available_label.Centre(wx.HORIZONTAL)


        # can_unpatch: bool = not patches[HardwarePatchsetValidation.UNPATCHING_NOT_POSSIBLE]
        can_unpatch: bool = not patches.get(HardwarePatchsetValidation.UNPATCHING_NOT_POSSIBLE, False)

        # 检查网络连接状态和无线网卡补丁
        network_unavailable = patches.get(HardwarePatchsetValidation.MISSING_NETWORK_CONNECTION, False)
        has_wireless_patches = any("无线网卡" in patch for patch in patches.keys())
        
        # 保存原始补丁列表用于后续判断
        original_patches = patches.copy()
        
        # 如果网络未连接且存在无线网卡补丁，询问用户是否只安装无线网卡补丁
        user_choice_wireless_only = False
        if network_unavailable and has_wireless_patches:
            # 询问用户是否只安装无线网卡补丁
            dialog = wx.MessageDialog(
                frame,
                "网络未连接。检测到无线网卡相关补丁可用。\n\n"
                "由于网络未连接，其他补丁可能需要网络下载组件，可能无法正常安装。\n"
                "是否只安装无线网卡相关补丁？\n\n"
                "选择『是』: 只显示无线网卡补丁\n"
                "选择『否』: 显示所有可用补丁（安装其他补丁可能需要网络）",
                "网络未连接 - 安装选项",
                wx.YES_NO | wx.YES_DEFAULT | wx.ICON_QUESTION
            )
            
            result = dialog.ShowModal()
            dialog.Destroy()
            
            if result == wx.ID_YES:
                # 用户选择只安装无线网卡补丁
                user_choice_wireless_only = True
                
                # 过滤补丁，只保留无线网卡相关的
                filtered_patches = {}
                for patch_key, patch_value in patches.items():
                    if "无线网卡" in patch_key:
                        filtered_patches[patch_key] = patch_value
                    elif patch_key.startswith("设置") or patch_key.startswith("验证"):
                        # 保留设置和验证信息
                        filtered_patches[patch_key] = patch_value
                
                # 更新补丁列表
                patches = filtered_patches
                
                # 弹窗提示用户
                wx.MessageBox(
                    "已选择只安装无线网卡相关补丁。\n\n"
                    "安装完成后，连接网络再回来安装其他补丁。",
                    "无线网卡补丁选择",
                    wx.OK | wx.ICON_INFORMATION,
                    frame
                )
                
                logging.info("用户选择只安装无线网卡相关补丁")
            else:
                # 用户选择显示所有补丁，显示警告
                wx.MessageBox(
                    "已选择显示所有可用补丁。\n\n"
                    "请注意：由于网络未连接，某些补丁可能需要网络下载组件，可能无法正常安装。\n"
                    "建议先安装无线网卡补丁，连接网络后再安装其他补丁。",
                    "网络未连接警告",
                    wx.OK | wx.ICON_WARNING,
                    frame
                )
                
                logging.info("用户选择显示所有可用补丁（网络未连接）")

        if not any(not patch.startswith("设置") and not patch.startswith("验证") and patches[patch] is True for patch in patches):
            logging.info("No applicable patches available")
            patches = {}

        # Check if OCLP has already applied the same patches
        # 对于过滤后的补丁列表，需要基于原始补丁列表来判断是否有新补丁
        if network_unavailable and has_wireless_patches and user_choice_wireless_only:
            # 如果用户选择了只安装无线网卡补丁，使用过滤后的补丁列表来判断新补丁
            no_new_patches = not self._check_if_new_patches_needed(patches) if patches else False
        else:
            # 其他情况使用原始补丁列表
            no_new_patches = not self._check_if_new_patches_needed(original_patches) if original_patches else False

        if not patches:
            # Prompt user with no patches found
            patch_label = wx.StaticText(frame, label="不需要补丁", pos=(-1, available_label.GetPosition()[1] + 20))
            patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            patch_label.Centre(wx.HORIZONTAL)

        else:
            # Add Label for each patch
            i = 0
            if no_new_patches is True:
                patch_label = wx.StaticText(frame, label="所有补丁已安装", pos=(-1, available_label.GetPosition()[1] + 20))
                patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                patch_label.Centre(wx.HORIZONTAL)
                i = i + 20
            else:
                longest_patch = ""
                for patch in patches:
                    if (not patch.startswith("设置") and not patch.startswith("验证") and patches[patch] is True):
                        if len(patch) > len(longest_patch):
                            longest_patch = patch
                if longest_patch:
                    anchor = wx.StaticText(frame, label=longest_patch, pos=(-1, available_label.GetPosition()[1] + 20))
                    anchor.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                    anchor.Centre(wx.HORIZONTAL)
                    anchor.Hide()

                logging.info("Available patches:")
                for patch in patches:
                    if (not patch.startswith("设置") and not patch.startswith("验证") and patches[patch] is True):
                        i = i + 20
                        logging.info(f"- {patch}")
                        if longest_patch:
                            patch_label = wx.StaticText(frame, label=f"- {patch}", pos=(anchor.GetPosition()[0], available_label.GetPosition()[1] + i))
                        else:
                            patch_label = wx.StaticText(frame, label=f"- {patch}", pos=(-1, available_label.GetPosition()[1] + i))
                            patch_label.Centre(wx.HORIZONTAL)
                        patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))

                if i == 20 and longest_patch:
                    patch_label.SetLabel(patch_label.GetLabel().replace("-", ""))
                    patch_label.Centre(wx.HORIZONTAL)

            if patches[HardwarePatchsetValidation.PATCHING_NOT_POSSIBLE] is True:
                # Cannot patch due to the following reasons:
                # 使用补丁列表的最后一个标签作为基准
                last_patch_y = patch_label.GetPosition()[1]
                patch_label = wx.StaticText(frame, label="无法安装补丁，原因:", pos=(-1, last_patch_y + 25))
                patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                patch_label.Centre(wx.HORIZONTAL)

                longest_patch = ""
                for patch in patches:
                    if not patch.startswith("验证"):
                        continue
                    if patches[patch] is False:
                        continue
                    if patch in [HardwarePatchsetValidation.PATCHING_NOT_POSSIBLE, HardwarePatchsetValidation.UNPATCHING_NOT_POSSIBLE]:
                        continue

                    if len(patch) > len(longest_patch):
                        longest_patch = patch
                
                if longest_patch:
                    anchor = wx.StaticText(frame, label=longest_patch.split('验证: ')[1], pos=(-1, patch_label.GetPosition()[1] + 20))
                    anchor.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                    anchor.Centre(wx.HORIZONTAL)
                    anchor.Hide()

                i = 0
                for patch in patches:
                    if not patch.startswith("验证"):
                        continue
                    if patches[patch] is False:
                        continue
                    if patch in [HardwarePatchsetValidation.PATCHING_NOT_POSSIBLE, HardwarePatchsetValidation.UNPATCHING_NOT_POSSIBLE]:
                        continue

                    if longest_patch:
                        patch_label = wx.StaticText(frame, label=f"- {patch.split('验证: ')[1]}", pos=(anchor.GetPosition()[0], anchor.GetPosition()[1] + i))
                    else:
                        patch_label = wx.StaticText(frame, label=f"- {patch.split('验证: ')[1]}", pos=(-1, patch_label.GetPosition()[1] + 20))
                        patch_label.Centre(wx.HORIZONTAL)
                    patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                    i = i + 20

                if i == 20 and longest_patch:
                    patch_label.SetLabel(patch_label.GetLabel().replace("-", ""))
                    patch_label.Centre(wx.HORIZONTAL)
                elif i == 20 and not longest_patch:
                    patch_label.SetLabel(patch_label.GetLabel().replace("-", ""))
                    patch_label.Centre(wx.HORIZONTAL)

            else:
                if self.constants.computer.oclp_sys_version and self.constants.computer.oclp_sys_date:
                    date = self.constants.computer.oclp_sys_date.split(" @")
                    date = date[0] if len(date) == 2 else ""

                    patch_text = f"{self.constants.computer.oclp_sys_version}, {date}"

                    # 获取当前最后一个标签的位置
                    last_label_y = patch_label.GetPosition()[1]
                    patch_label = wx.StaticText(frame, label="上一次补丁安装时间:", pos=(-1, last_label_y + 25))
                    patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                    patch_label.Centre(wx.HORIZONTAL)

                    patch_label = wx.StaticText(frame, label=patch_text, pos=(available_label.GetPosition()[0] - 10, patch_label.GetPosition()[1] + 20))
                    patch_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                    patch_label.Centre(wx.HORIZONTAL)

        # Button: Start Root Patching
        start_button = wx.Button(frame, label="开始安装驱动补丁", pos=(10, patch_label.GetPosition().y + 25), size=(170, 30))
        start_button.Bind(wx.EVT_BUTTON, lambda event: self.on_start_root_patching(patches))
        start_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        start_button.Centre(wx.HORIZONTAL)

        # Button: Revert Root Patches
        revert_button = wx.Button(frame, label="删除已安装的补丁", pos=(10, start_button.GetPosition().y + start_button.GetSize().height - 5), size=(170, 30))
        revert_button.Bind(wx.EVT_BUTTON, lambda event: self.on_revert_root_patching(patches))
        revert_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        revert_button.Centre(wx.HORIZONTAL)

        # Button: Return to Main Menu
        return_button = wx.Button(frame, label="返回", pos=(10, revert_button.GetPosition().y + revert_button.GetSize().height), size=(150, 30))
        return_button.Bind(wx.EVT_BUTTON, self.on_return_dismiss if self.init_with_parent else self.on_return_to_main_menu)
        return_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        return_button.Centre(wx.HORIZONTAL)
        self.return_button = return_button

        # Disable buttons if unsupported
        if not patches:
            start_button.Disable()
        else:
            self.available_patches = True
            if patches.get(HardwarePatchsetValidation.PATCHING_NOT_POSSIBLE, False) is True or no_new_patches is True:
                start_button.Disable()
            elif no_new_patches is False:
                start_button.SetDefault()
            else:
                self.available_patches = False
        if can_unpatch is False:
            revert_button.Disable()

        # Set frame size
        frame.SetSize((-1, return_button.GetPosition().y + return_button.GetSize().height + 15))
        frame.ShowWindowModal()


    def on_start_root_patching(self, patches: dict):
        frame = gui_sys_patch_start.SysPatchStartFrame(
            parent=None,
            title=self.title,
            global_constants=self.constants,
            patches=patches,
        )
        self.frame_modal.Hide()
        self.frame_modal.Destroy()
        self.frame.Hide()
        self.frame.Destroy()
        frame.start_root_patching()


    def on_revert_root_patching(self, patches: dict):
        frame = gui_sys_patch_start.SysPatchStartFrame(
            parent=None,
            title=self.title,
            global_constants=self.constants,
            patches=patches,
        )
        self.frame_modal.Hide()
        self.frame_modal.Destroy()
        self.frame.Hide()
        self.frame.Destroy()
        frame.revert_root_patching()


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


    def _check_if_new_patches_needed(self, patches: dict) -> bool:
        """
        Checks if any new patches are needed for the user to install
        Newer users will assume the root patch menu will present missing patches.
        Thus we'll need to see if the exact same OCLP build was used already
        """

        logging.info("检查是否需要新的补丁")


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
                    logging.info(f"- 补丁 {patch} 没有安装")
                    return True

        logging.info("没有检测到新的补丁需要安装")
        return False