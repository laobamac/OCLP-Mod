"""
gui_settings.py: Settings Frame for the GUI
"""

import wx
import wx.adv
import pprint
import logging
import py_sip_xnu
import subprocess

from pathlib import Path

from .. import constants

from ..sys_patch import sys_patch

from ..wx_gui import (
    gui_support,
    gui_update
)
from ..support import (
    global_settings,
    defaults,
    generate_smbios,
    network_handler,
    subprocess_wrapper
)
from ..datasets import (
    model_array,
    sip_data,
    smbios_data,
    os_data,
    cpu_data
)


class SettingsFrame(wx.Frame):
    """
    Modal-based Settings Frame
    """
    def __init__(self, parent: wx.Frame, title: str, global_constants: constants.Constants, screen_location: tuple = None):
        logging.info("Initializing Settings Frame")
        self.constants: constants.Constants = global_constants
        self.title: str = title
        self.parent: wx.Frame = parent

        self.hyperlink_colour = (25, 179, 231)

        self.settings = self._settings()

        self.frame_modal = wx.Dialog(parent, title=title, size=(600, 685))

        self._generate_elements(self.frame_modal)
        self.frame_modal.ShowWindowModal()

    def _generate_elements(self, frame: wx.Frame = None) -> None:
        """
        Generates elements for the Settings Frame
        Uses wx.Notebook to implement a tabbed interface
        and relies on 'self._settings()' for populating
        """

        notebook = wx.Notebook(frame)
        notebook.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(10)

        model_label = wx.StaticText(frame, label="目标机型", pos=(-1, -1))
        model_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
        sizer.Add(model_label, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        model_choice = wx.Choice(frame, choices=model_array.SupportedSMBIOS + ["主机机型"], pos=(-1, -1), size=(150, -1))
        model_choice.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        model_choice.Bind(wx.EVT_CHOICE, lambda event: self.on_model_choice(event, model_choice))
        selection = self.constants.custom_model if self.constants.custom_model else "主机机型"
        model_choice.SetSelection(model_choice.FindString(selection))
        sizer.Add(model_choice, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        model_description = wx.StaticText(frame, label="覆写Patcher将要仿冒的机型", pos=(-1, -1))
        model_description.SetFont(gui_support.font_factory(11, wx.FONTWEIGHT_NORMAL))
        sizer.Add(model_description, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        tabs = list(self.settings.keys())
        if not Path("~/.laobamac_developer").expanduser().exists():
            tabs.remove("开发者")
        for tab in tabs:
            panel = wx.Panel(notebook)
            notebook.AddPage(panel, tab)

        sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 10)

        # Add return button
        return_button = wx.Button(frame, label="返回", pos=(-1, -1), size=(100, 30))
        return_button.Bind(wx.EVT_BUTTON, self.on_return)
        return_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        sizer.Add(return_button, 0, wx.ALIGN_CENTER | wx.ALL, 10)

        frame.SetSizer(sizer)

        horizontal_center = frame.GetSize()[0] / 2
        for tab in tabs:
            if tab not in self.settings:
                continue

            stock_height = 0
            stock_width = 20

            height = stock_height
            width = stock_width

            lowest_height_reached = height
            highest_height_reached = height

            panel = notebook.GetPage(tabs.index(tab))

            for setting, setting_info in self.settings[tab].items():
                if setting_info["type"] == "populate":
                    # execute populate function
                    if setting_info["args"] == wx.Frame:
                        setting_info["function"](panel)
                    else:
                        raise Exception("Invalid populate function")
                    continue

                if setting_info["type"] == "title":
                    stock_height = lowest_height_reached
                    height = stock_height
                    width = stock_width

                    height += 10

                    # Add title
                    title = wx.StaticText(panel, label=setting, pos=(-1, -1))
                    title.SetFont(gui_support.font_factory(19, wx.FONTWEIGHT_BOLD))

                    title.SetPosition((int(horizontal_center) - int(title.GetSize()[0] / 2) - 15, height))
                    highest_height_reached = height + title.GetSize()[1] + 10
                    height += title.GetSize()[1] + 10
                    continue

                if setting_info["type"] == "sub_title":
                    # Add sub-title
                    sub_title = wx.StaticText(panel, label=setting, pos=(-1, -1))
                    sub_title.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))

                    sub_title.SetPosition((int(horizontal_center) - int(sub_title.GetSize()[0] / 2) - 15, height))
                    highest_height_reached = height + sub_title.GetSize()[1] + 10
                    height += sub_title.GetSize()[1] + 10
                    continue

                if setting_info["type"] == "wrap_around":
                    height = highest_height_reached
                    width = 300 if width is stock_width else stock_width
                    continue

                if setting_info["type"] == "checkbox":
                    # Add checkbox, and description underneath
                    checkbox = wx.CheckBox(panel, label=setting, pos=(10 + width, 10 + height), size = (300,-1))
                    checkbox.SetValue(setting_info["value"] if setting_info["value"] else False)
                    checkbox.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                    event = lambda event, warning=setting_info["warning"] if "warning" in setting_info else "", override=bool(setting_info["override_function"]) if "override_function" in setting_info else False: self.on_checkbox(event, warning, override)
                    checkbox.Bind(wx.EVT_CHECKBOX, event)
                    if "condition" in setting_info:
                        checkbox.Enable(setting_info["condition"])
                        if setting_info["condition"] is False:
                            checkbox.SetValue(False)

                elif setting_info["type"] == "spinctrl":
                    # Add spinctrl, and description underneath
                    spinctrl = wx.SpinCtrl(panel, value=str(setting_info["value"]), pos=(width - 20, 10 + height), min=setting_info["min"], max=setting_info["max"], size = (45,-1))
                    spinctrl.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                    spinctrl.Bind(wx.EVT_TEXT, lambda event, variable=setting: self.on_spinctrl(event, variable))
                    # Add label next to spinctrl
                    label = wx.StaticText(panel, label=setting, pos=(spinctrl.GetSize()[0] + width - 16, spinctrl.GetPosition()[1]))
                    label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                elif setting_info["type"] == "choice":
                    # Title
                    title = wx.StaticText(panel, label=setting, pos=(width + 30, 10 + height))
                    title.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
                    height += title.GetSize()[1] + 10

                    # Add combobox, and description underneath
                    choice = wx.Choice(panel, pos=(width + 25, 10 + height), choices=setting_info["choices"], size = (150,-1))
                    choice.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                    choice.SetSelection(choice.FindString(setting_info["value"]))
                    if "override_function" in setting_info:
                        choice.Bind(wx.EVT_CHOICE, lambda event, variable=setting: self.settings[tab][variable]["override_function"](event))
                    else:
                        choice.Bind(wx.EVT_CHOICE, lambda event, variable=setting: self.on_choice(event, variable))
                    height += 10
                elif setting_info["type"] == "button":
                    button = wx.Button(panel, label=setting, pos=(width + 25, 10 + height), size = (200,-1))
                    button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
                    button.Bind(wx.EVT_BUTTON, lambda event, variable=setting: self.settings[tab][variable]["function"](event))
                    height += 10

                else:
                    raise Exception("Invalid setting type")

                lines = '\n'.join(setting_info["description"])
                description = wx.StaticText(panel, label=lines, pos=(30 + width, 10 + height + 20))
                description.SetFont(gui_support.font_factory(11, wx.FONTWEIGHT_NORMAL))
                height += 40
                if "condition" in setting_info:
                    if setting_info["condition"] is False:
                        description.SetForegroundColour((128, 128, 128))

                # Check number of lines in description, and adjust spacer accordingly
                for i, line in enumerate(lines.split('\n')):
                    if line == "":
                        continue
                    if i == 0:
                        height += 11
                    else:
                        height += 13

                if height > lowest_height_reached:
                    lowest_height_reached = height


    def _settings(self) -> dict:
        """
        Generates a dictionary of settings to be used in the GUI
        General format:
        {
            "Tab Name": {
                "type": "title" | "checkbox" | "spinctrl" | "populate" | "wrap_around",
                "value": bool | int | str,
                "variable": str,  (Variable name)
                "constants_variable": str, (Constants variable name, if different from "variable")
                "description": [str, str, str], (List of strings)
                "warning": str, (Optional) (Warning message to be displayed when checkbox is checked)
                "override_function": function, (Optional) (Function to be executed when checkbox is checked)
            }
        }
        """

        models = [model for model in smbios_data.smbios_dictionary if "_" not in model and " " not in model and smbios_data.smbios_dictionary[model]["Board ID"] is not None]
        socketed_imac_models = ["iMac9,1", "iMac10,1", "iMac11,1", "iMac11,2", "iMac11,3", "iMac12,1", "iMac12,2"]
        socketed_gpu_models = socketed_imac_models + ["MacPro3,1", "MacPro4,1", "MacPro5,1", "Xserve2,1", "Xserve3,1"]

        settings = {
            "创建": {
                "概览": {
                    "type": "title",
                },
                "固件启动": {
                    "type": "checkbox",
                    "value": self.constants.firewire_boot,
                    "variable": "firewire_boot",
                    "description": [
                        "启用从火线驱动器",
                        "启动macOS",
                    ],
                    "condition": not (generate_smbios.check_firewire(self.constants.custom_model or self.constants.computer.real_model) is False)
                },
                "XHCI启动": {
                    "type": "checkbox",
                    "value": self.constants.xhci_boot,
                    "variable": "xhci_boot",
                    "description": [
                        "在没有原生支持的系统上，启用从",
                        "USB 3.0扩展卡启动macOS。",
                    ],
                    "condition": not gui_support.CheckProperties(self.constants).host_has_cpu_gen(cpu_data.CPUGen.ivy_bridge) # Sandy Bridge and older do not natively support XHCI booting
                },
                "NVMe启动": {
                    "type": "checkbox",
                    "value": self.constants.nvme_boot,
                    "variable": "nvme_boot",
                    "description": [
                        "启用macOS中对",
                        "NVMe驱动器的非原生",
                        "支持",
                        "注意：需要你的机器支持NVMe",
                        "OC才可以从NVMe驱动器启动。",
                    ],
                    "condition": not gui_support.CheckProperties(self.constants).host_has_cpu_gen(cpu_data.CPUGen.ivy_bridge) # Sandy Bridge and older do not natively support NVMe booting
                },
                "wrap_around 2": {
                    "type": "wrap_around",
                },
                "OpenCore签名保护": {
                    "type": "checkbox",
                    "value": self.constants.vault,
                    "variable": "vault",
                    "description": [
                        "对OpenCore进行数字签名，以防止",
                        "篡改&破坏"
                    ],
                },

                "显示OpenCore引导界面": {
                    "type": "checkbox",
                    "value": self.constants.showpicker,
                    "variable": "showpicker",
                    "description": [
                        "禁用时，用户可以按住ESC键",
                        "在固件中显示选择器",
                    ],
                },
                "引导界面等待时间": {
                    "type": "spinctrl",
                    "value": self.constants.oc_timeout,
                    "variable": "oc_timeout",
                    "description": [
                        "在引导选择器选择默认",
                        "条目之前的超时时间（秒）。",
                        "设置为0表示无超时。",
                    ],

                    "min": 0,
                    "max": 60,
                },
                "MacPro3,1/Xserve2,1 解决方案": {
                    "type": "checkbox",
                    "value": self.constants.force_quad_thread,
                    "variable": "force_quad_thread",
                    "description": [
                        "在这些单元上限制最大线程数为4。",
                        "macOS Sequoia及更高版本需要。",
                    ],
                    "condition": (self.constants.custom_model and self.constants.custom_model in ["MacPro3,1", "Xserve2,1"]) or self.constants.computer.real_model in ["MacPro3,1", "Xserve2,1"]
                },
                "调试": {
                    "type": "title",
                },

                "啰嗦模式": {
                    "type": "checkbox",
                    "value": self.constants.verbose_debug,
                    "variable": "verbose_debug",
                    "description": [
                        "启动时输出详细信息",
                    ],

                },
                "调试版本驱动": {
                    "type": "checkbox",
                    "value": self.constants.kext_debug,
                    "variable": "kext_debug",
                    "description": [
                        "使用kext的DEBUG版本，并",
                        "启用额外的内核日志记录。",
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "调试版本OpenCore": {
                    "type": "checkbox",
                    "value": self.constants.opencore_debug,
                    "variable": "opencore_debug",
                    "description": [
                        "使用OpenCore的DEBUG版本，并",
                        "启用额外的内核日志记录。",
                    ],
                },
            },
            "额外": {
                "通用（可持续生效）": {
                    "type": "title",
                },
                "WOL": {
                    "type": "checkbox",
                    "value": self.constants.enable_wake_on_wlan,
                    "variable": "enable_wake_on_wlan",
                    "description": [
                        "默认情况下禁用，因为在某些系统上从唤醒状态可能会",
                        "导致性能下降",
                        "仅适用于BCM943224、331、",
                        "360和3602芯片组。",
                    ],
                },
                "禁用雷电⚡️": {
                    "type": "checkbox",
                    "value": self.constants.disable_tb,
                    "variable": "disable_tb",
                    "description": [
                        "针对有故障",
                        "导致PCH可能会偶尔崩溃的MacBookPro11,x。",
                    ],
                    "condition": (self.constants.custom_model and self.constants.custom_model in ["MacBookPro11,1", "MacBookPro11,2", "MacBookPro11,3"]) or self.constants.computer.real_model in ["MacBookPro11,1", "MacBookPro11,2", "MacBookPro11,3"]
                },
                "Windows GMUX": {
                    "type": "checkbox",
                    "value": self.constants.dGPU_switch,
                    "variable": "dGPU_switch",
                    "description": [
                        "允许在Windows中暴露iGPU",
                        "用于基于dGPU的MacBooks。",
                    ],
                },
                "禁用CPUFriend": {
                    "type": "checkbox",
                    "value": self.constants.disallow_cpufriend,
                    "variable": "disallow_cpufriend",
                    "description": [
                    "禁用不支持型号的",
                    "CPUFriend",
                    ],
                },
                "禁用mediaanalysisd服务": {
                    "type": "checkbox",
                    "value": self.constants.disable_mediaanalysisd,
                    "variable": "disable_mediaanalysisd",
                    "description": [
                        "对于使用3802-Based GPU的iCloud",
                        "Photos，这可能会延缓",
                        "CPU占用",
                    ],
                    "condition": gui_support.CheckProperties(self.constants).host_has_3802_gpu()
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "允许使用AppleALC音频": {
                    "type": "checkbox",
                    "value": self.constants.set_alc_usage,
                    "variable": "set_alc_usage",
                    "description": [
                        "如果适用，允许AppleALC管理音频",
                        "仅在主机缺少GOP ROM时禁用。",
                    ],
                },
                "写入NVRAM": {
                    "type": "checkbox",
                    "value": self.constants.nvram_write,
                    "variable": "nvram_write",
                    "description": [
                        "允许OpenCore写入NVRAM。",
                        "在有故障或",
                        "降级的NVRAM系统上禁用。",
                    ],
                },

                "第三方NVMe电源管理": {
                    "type": "checkbox",
                    "value": self.constants.allow_nvme_fixing,
                    "variable": "allow_nvme_fixing",
                    "description": [
                        "在 macOS 中启用未被提供的",
                        "NVMe 电源管理",
                    ],
                },
                "第三方SATA电源管理": {
                    "type": "checkbox",
                    "value": self.constants.allow_3rd_party_drives,
                    "variable": "allow_3rd_party_drives",
                    "description": [
                        "在 macOS 中启用未被提供的",
                        "SATA 电源管理",
                    ],
                    "condition": not bool(self.constants.computer.third_party_sata_ssd is False and not self.constants.custom_model)
                },
                "Trim相关": {
                    "type": "checkbox",
                    "value": self.constants.apfs_trim_timeout,
                    "variable": "apfs_trim_timeout",
                    "description": [
                        "建议所有用户使用，即使有故障",
                        "SSDs 可能也会从禁用此功能中受益。",
                    ],
                },
            },
            "高级": {
                "杂项": {
                    "type": "title",
                },
                "Disable Firmware Throttling": {
                    "type": "checkbox",
                    "value": self.constants.disable_fw_throttle,
                    "variable": "disable_fw_throttle",
                    "description": [
                        "禁用基于固件的限制",
                        "由缺少硬件引起",
                        "例如缺少显示器、电池等",
                    ],
                },
                "Software DeMUX": {
                    "type": "checkbox",
                    "value": self.constants.software_demux,
                    "variable": "software_demux",
                    "description": [
                        "启用基于软件的 DeMUX",
                        "适用于 MacBookPro8,2 和 MacBookPro8,3.",
                        "防止有故障的 dGPU 启用",
                        "注意：需要相关的 NVRAM 参数：",
                        "'gpu-power-prefs'.",
                    ],
                    "warning": "This settings requires 'gpu-power-prefs' NVRAM argument to be set to '1'.\n\nIf missing and this option is toggled, the system will not boot\n\nFull command:\nnvram FA4CE28D-B62F-4C99-9CC3-6815686E30F9:gpu-power-prefs=%01%00%00%00",
                    "condition": not bool((not self.constants.custom_model and self.constants.computer.real_model not in ["MacBookPro8,2", "MacBookPro8,3"]) or (self.constants.custom_model and self.constants.custom_model not in ["MacBookPro8,2", "MacBookPro8,3"]))
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "启用不支持的功能": {
                    "type": "choice",
                    "choices": [
                        "Enabled",
                        "Partial",
                        "Disabled",
                    ],
                    "value": "Enabled",
                    "variable": "",
                    "description": [
                        "配置 FeatureUnlock 等级.",
                        "如果您的系统提示建议降低",
                        "由于遇到内存不稳定",
                    ],
                },
                "Populate FeatureUnlock Override": {
                    "type": "populate",
                    "function": self._populate_fu_override,
                    "args": wx.Frame,
                },
                "休眠方案": {
                    "type": "checkbox",
                    "value": self.constants.disable_connectdrivers,
                    "variable": "disable_connectdrivers",
                    "description": [
                        "仅加载最低 EFI 驱动程序",
                        "防止休眠问题",
                        "注意：这可能会中断从",
                        "外置硬盘的启动",
                    ],
                },
                "显卡": {
                    "type": "title",
                },
                "AMD GOP 注入": {
                    "type": "checkbox",
                    "value": self.constants.amd_gop_injection,
                    "variable": "amd_gop_injection",
                    "description": [
                        "注入AMD GOP来显示",
                        "启动界面",
                    ],
                    "condition": not bool((not self.constants.custom_model and self.constants.computer.real_model not in socketed_gpu_models) or (self.constants.custom_model and self.constants.custom_model not in socketed_gpu_models))
                },
                "Nvidia GOP 注入": {
                    "type": "checkbox",
                    "value": self.constants.nvidia_kepler_gop_injection,
                    "variable": "nvidia_kepler_gop_injection",
                    "description": [
                        "注入Nvidia Kepler GOP来显示",
                        "启动界面",
                    ],
                    "condition": not bool((not self.constants.custom_model and self.constants.computer.real_model not in socketed_gpu_models) or (self.constants.custom_model and self.constants.custom_model not in socketed_gpu_models))
                },
                "wrap_around 2": {
                    "type": "wrap_around",
                },
                "显卡覆写": {
                    "type": "choice",
                    "choices": [
                        "None",
                        "Nvidia Kepler",
                        "AMD GCN",
                        "AMD Polaris",
                        "AMD Lexa",
                        "AMD Navi",
                    ],
                    "value": "None",
                    "variable": "",
                    "description": [
                        "覆盖检测到的/假设的 MXM显卡",
                        "适用于MXM-based iMacs.",
                    ],
                    "condition": bool((not self.constants.custom_model and self.constants.computer.real_model in socketed_imac_models) or (self.constants.custom_model and self.constants.custom_model in socketed_imac_models))
                },
                "Populate Graphics Override": {
                    "type": "populate",
                    "function": self._populate_graphics_override,
                    "args": wx.Frame,
                },

            },
            "安全": {
                "内核安全": {
                    "type": "title",
                },
                "禁用资源库验证": {
                    "type": "checkbox",
                    "value": self.constants.disable_cs_lv,
                    "variable": "disable_cs_lv",
                    "description": [
                        "在打补丁时注入修改后",
                        "的系统文件时需要",
                    ],
                },
                "禁用 AMFI": {
                    "type": "checkbox",
                    "value": self.constants.disable_amfi,
                    "variable": "disable_amfi",
                    "description": [
                        "在打补丁时注入修改后",
                        "的系统文件时需要",
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "安全启动机型": {
                    "type": "checkbox",
                    "value": self.constants.secure_status,
                    "variable": "secure_status",
                    "description": [
                        "设置 Apple 安全启动模型标识符",
                        "如果已经仿冒，则匹配 T2 模型",
                        "注意：与驱动补丁不兼容",
                    ],
                },
                "系统完整性保护（SIP）": {
                    "type": "title",
                },
                "Populate SIP": {
                    "type": "populate",
                    "function": self._populate_sip_settings,
                    "args": wx.Frame,
                },
            },
            "SMBIOS": {
                "机型覆写": {
                    "type": "title",
                },
                "SMBIOS 覆写等级": {
                    "type": "choice",
                    "choices": [
                        "None",
                        "Minimal",
                        "Moderate",
                        "Advanced",
                    ],
                    "value": self.constants.serial_settings,
                    "variable": "serial_settings",
                    "description": [
                        "支持的级别：",
                        "    - 无：无",
                        "   - 小: 覆写 Board ID.",
                        "   - 中: 覆写 Model.",
                        "   - 高: 覆写 Model 和 serial.",
                    ],
                },

                "SMBIOS 机型覆写": {
                    "type": "choice",
                    "choices": models + ["Default"],
                    "value": self.constants.override_smbios,
                    "variable": "override_smbios",
                    "description": [
                        "设置仿冒的机型",
                    ],

                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "允许覆写原生支持的Mac": {
                    "type": "checkbox",
                    "value": self.constants.allow_native_spoofs,
                    "variable": "allow_native_spoofs",
                    "description": [
                        "允许 OpenCore 仿冒原生",
                        "受支持的Mac.",
                        "主要用于启用",
                        "不受支持的 Mac 上的 Universal Control",
                    ],
                },
                "序列号覆写": {
                    "type": "title",
                },
                "Populate 序列号覆写": {
                    "type": "populate",
                    "function": self._populate_serial_spoofing_settings,
                    "args": wx.Frame,
                },
            },
            "补丁": {
                "根目录补丁": {
                    "type": "title",
                },
                "TeraScale 2 Acceleration": {
                    "type": "checkbox",
                    "value": global_settings.GlobalEnviromentSettings().read_property("MacBookPro_TeraScale_2_Accel") or self.constants.allow_ts2_accel,
                    "variable": "MacBookPro_TeraScale_2_Accel",
                    "constants_variable": "allow_ts2_accel",
                    "description": [
                        "启用 AMD TeraScale 2 GPU",
                        "在 MacBookPro8,2 和",
                        "MacBookPro8,3 上的加速。",
                        "默认情况下这是禁用的，因为",
                        "这些型号的 GPU 常见故障。"
                    ],
                    "override_function": self._update_global_settings,
                    "condition": not bool(self.constants.computer.real_model not in ["MacBookPro8,2", "MacBookPro8,3"])
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "允许安装旧版USB环境扩展补丁": {
                    "type": "checkbox",
                    "value": self.constants.allow_usb_patch,
                    "variable": "allow_usb_patch",
                    "description": [
                        "允许在Tahoe及以上系统",
                        "安装旧版USB环境扩展"
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "Non-Metal配置": {
                    "type": "title",
                },
                "Log out required to apply changes to SkyLight": {
                    "type": "sub_title",
                },
                "暗黑模式菜单": {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_DarkMenuBar"),
                    "variable": "Moraea_DarkMenuBar",
                    "description": [
                        "如果启用了 Beta 菜单栏，"
                        "菜单栏颜色将根据需要动态"
                        "变化。"
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                "Beta Blur": {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_BlurBeta"),
                    "variable": "Moraea_BlurBeta",
                    "description": [
                        "Control window blur behaviour.",
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)

                },
                "加载光标（彩虹圈圈）解决方案": {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea.EnableSpinHack"),
                    "variable": "Moraea.EnableSpinHack",
                    "description": [
                        "注意：可能会占用更多 CPU 资源。",
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                "wrap_around 2": {
                    "type": "wrap_around",
                },
                "Beta Menu Bar": {
                    "type": "checkbox",
                    "value": self._get_system_settings("Amy.MenuBar2Beta"),
                    "variable": "Amy.MenuBar2Beta",
                    "description": [
                        "支持动态颜色变化。"
                        "注意：此设置仍在试验阶段。"
                        "如果遇到问题，请"
                        "禁用此设置。"
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                "禁用 Beta Rim": {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_RimBetaDisabled"),
                    "variable": "Moraea_RimBetaDisabled",
                    "description": [
                        "控制窗口边缘的渲染效果",
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                "控制桌面小部件颜色强制执行": {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_ColorWidgetDisabled"),
                    "variable": "Moraea_ColorWidgetDisabled",
                    "description": [
                        "控制桌面小部件颜色强制执行",
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
            },
            "App": {
                "通用": {
                    "type": "title",
                },
                "Allow native models": {
                    "type": "checkbox",
                    "value": self.constants.allow_oc_everywhere,
                    "variable": "allow_oc_everywhere",
                    "description": [
                        "允许在原生支持的Mac上安装OpenCore。",
                        "注意这不会允许不支持的",
                        "macOS版本安装在",
                        "你的系统上。"
                    ],
                    "注意": "这个选项仅应在您的Mac原生支持您想要运行的操作系统时使用。\n\n如果您当前正在运行一个不支持的操作系统，这个选项将会导致启动失败。\n\n仅在原生Mac上切换以启用操作系统特性。\n\n您确定要继续吗？",
                },
                "忽略App更新": {
                    "type": "checkbox",
                    "value": global_settings.GlobalEnviromentSettings().read_property("IgnoreAppUpdates") or self.constants.ignore_updates,
                    "variable": "IgnoreAppUpdates",
                    "constants_variable": "ignore_updates",
                    "description": [
                        # "Ignore app updates",
                    ],
                    "override_function": self._update_global_settings,
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "禁用报告": {
                    "type": "checkbox",
                    "value": global_settings.GlobalEnviromentSettings().read_property("DisableCrashAndAnalyticsReporting"),
                    "variable": "DisableCrashAndAnalyticsReporting",
                    "description": [
                        "当启用时，修补程序将不会",
                        "向laobamac报告任何信息。",
                    ],
                    "override_function": self._update_global_settings,
                },
                "移除未使用的KDK": {
                    "type": "checkbox",
                    "value": global_settings.GlobalEnviromentSettings().read_property("ShouldNukeKDKs") or self.constants.should_nuke_kdks,
                    "variable": "ShouldNukeKDKs",
                    "constants_variable": "should_nuke_kdks",
                    "description": [
                        "当启用时，应用程序将从系统中移除",
                        "未使用的KDK",
                        "在根目录修补期间。",
                    ],
                    "override_function": self._update_global_settings,
                },
                "统计": {
                    "type": "title",
                },
                "Populate Stats": {
                    "type": "populate",
                    "function": self._populate_app_stats,
                    "args": wx.Frame,
                },
            },
            "开发者": {
                "验证": {
                    "type": "title",
                },
                "安装最新日构建版本 🧪": {
                    "type": "button",
                    "function": self.on_nightly,
                    "description": [
                        "如果你已经在这里，我假设你已经准备好了",
                        "冒着系统变砖的风险 🧱。",
                        "在盲目更新前请检查更新日志。",
                    ],
                },
                "Trigger Exception": {
                    "type": "button",
                    "function": self.on_test_exception,
                    "description": [
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                "Export constants": {
                    "type": "button",
                    "function": self.on_export_constants,
                    "description": [
                        "Export constants.py values to a txt file.",
                    ],
                },

                "开发者补丁选项": {
                    "type": "title",
                },
                "挂载根目录": {
                    "type": "button",
                    "function": self.on_mount_root_vol,
                    "description": [
                        "Life's too short to type 'sudo mount -o",
                        "nobrowse -t apfs /dev/diskXsY",
                        "/System/Volumes/Update/mnt1' every time.",
                    ],
                },
                "wrap_around 2": {
                    "type": "wrap_around",
                },
                "保存根目录": {
                    "type": "button",
                    "function": self.on_bless_root_vol,
                    "description": [
                        "重建内核缓存并祈祷快照别寄（bushi 🙏",
                    ],
                },
            },
        }

        return settings


    def on_model_choice(self, event: wx.Event, model_choice: wx.Choice) -> None:
        """
        Sets model to use for patching.
        """

        selection = model_choice.GetStringSelection()
        if selection == "主机机型":
            selection = self.constants.computer.real_model
            self.constants.custom_model = None
            logging.info(f"Using Real Model: {self.constants.computer.real_model}")
            defaults.GenerateDefaults(self.constants.computer.real_model, True, self.constants)
        else:
            logging.info(f"Using Custom Model: {selection}")
            self.constants.custom_model = selection
            defaults.GenerateDefaults(self.constants.custom_model, False, self.constants)
            self.parent.build_button.Enable()



        self.parent.model_label.SetLabel(f"机型: {selection}")
        self.parent.model_label.Centre(wx.HORIZONTAL)

        self.frame_modal.Destroy()
        SettingsFrame(
            parent=self.parent,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.parent.GetPosition()
        )


    def _populate_sip_settings(self, panel: wx.Frame) -> None:

        horizontal_spacer = 250

        # Look for title on frame
        sip_title: wx.StaticText = None
        for child in panel.GetChildren():
            if child.GetLabel() == "系统完整性保护（SIP）":
                sip_title = child
                break


        # Label: Flip individual bits corresponding to XNU's csr.h
        # If you're unfamiliar with how SIP works, do not touch this menu
        sip_label = wx.StaticText(panel, label="反转对应于", pos=(sip_title.GetPosition()[0] - 20, sip_title.GetPosition()[1] + 30))
        sip_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))

        # Hyperlink: csr.h
        spacer = 1 if self.constants.detected_os >= os_data.os_data.big_sur else 3
        sip_csr_h = wx.adv.HyperlinkCtrl(panel, id=wx.ID_ANY, label="XNU's csr.h", url="https://github.com/apple-oss-distributions/xnu/blob/xnu-8020.101.4/bsd/sys/csr.h", pos=(sip_label.GetPosition()[0] + sip_label.GetSize()[0] + 4, sip_label.GetPosition()[1] + spacer))
        sip_csr_h.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        sip_csr_h.SetHoverColour(self.hyperlink_colour)
        sip_csr_h.SetNormalColour(self.hyperlink_colour)
        sip_csr_h.SetVisitedColour(self.hyperlink_colour)

        # Label: SIP Status
        if self.constants.custom_sip_value is not None:
            self.sip_value = int(self.constants.custom_sip_value, 16)
        elif self.constants.sip_status is True:
            self.sip_value = 0x00
        else:
            self.sip_value = 0x803
        sip_configured_label = wx.StaticText(panel, label=f"当前设置的SIP: {hex(self.sip_value)}", pos=(sip_label.GetPosition()[0] + 35, sip_label.GetPosition()[1] + 20))
        sip_configured_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
        self.sip_configured_label = sip_configured_label

        # Label: SIP Status
        sip_booted_label = wx.StaticText(panel, label=f"当前启动的SIP: {hex(py_sip_xnu.SipXnu().get_sip_status().value)}", pos=(sip_configured_label.GetPosition()[0], sip_configured_label.GetPosition()[1] + 20))
        sip_booted_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))


        # SIP toggles
        entries_per_row = len(sip_data.system_integrity_protection.csr_values) // 2
        horizontal_spacer = 15
        vertical_spacer = 25
        index = 1
        for sip_bit in sip_data.system_integrity_protection.csr_values_extended:
            self.sip_checkbox = wx.CheckBox(panel, label=sip_data.system_integrity_protection.csr_values_extended[sip_bit]["name"].split("CSR_")[1], pos = (vertical_spacer, sip_booted_label.GetPosition()[1] + 20 + horizontal_spacer))
            self.sip_checkbox.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            self.sip_checkbox.SetToolTip(f'Description: {sip_data.system_integrity_protection.csr_values_extended[sip_bit]["description"]}\nValue: {hex(sip_data.system_integrity_protection.csr_values_extended[sip_bit]["value"])}\nIntroduced in: macOS {sip_data.system_integrity_protection.csr_values_extended[sip_bit]["introduced_friendly"]}')

            if self.sip_value & sip_data.system_integrity_protection.csr_values_extended[sip_bit]["value"] == sip_data.system_integrity_protection.csr_values_extended[sip_bit]["value"]:
                self.sip_checkbox.SetValue(True)

            horizontal_spacer += 20
            if index == entries_per_row:
                horizontal_spacer = 15
                vertical_spacer += 250

            index += 1
            self.sip_checkbox.Bind(wx.EVT_CHECKBOX, self.on_sip_value)


    def _populate_serial_spoofing_settings(self, panel: wx.Frame) -> None:
        title: wx.StaticText = None
        for child in panel.GetChildren():
            if child.GetLabel() == "序列号覆写":
                title = child
                break

        # Label: Custom Serial Number
        custom_serial_number_label = wx.StaticText(panel, label="自定义序列号", pos=(title.GetPosition()[0] - 150, title.GetPosition()[1] + 30))
        custom_serial_number_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))

        # Textbox: Custom Serial Number
        custom_serial_number_textbox = wx.TextCtrl(panel, pos=(custom_serial_number_label.GetPosition()[0] - 27, custom_serial_number_label.GetPosition()[1] + 20), size=(200, 25))
        custom_serial_number_textbox.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        custom_serial_number_textbox.SetToolTip("Enter a custom serial number here. This will be used for the SMBIOS and iMessage.\n\nNote: This will not be used if the \"Use Custom Serial Number\" checkbox is not checked.")
        custom_serial_number_textbox.Bind(wx.EVT_TEXT, self.on_custom_serial_number_textbox)
        custom_serial_number_textbox.SetValue(self.constants.custom_serial_number)
        self.custom_serial_number_textbox = custom_serial_number_textbox

        # Label: Custom Board Serial Number
        custom_board_serial_number_label = wx.StaticText(panel, label="自定义主板序列号", pos=(title.GetPosition()[0] + 120, custom_serial_number_label.GetPosition()[1]))
        custom_board_serial_number_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))

        # Textbox: Custom Board Serial Number
        custom_board_serial_number_textbox = wx.TextCtrl(panel, pos=(custom_board_serial_number_label.GetPosition()[0] - 5, custom_serial_number_textbox.GetPosition()[1]), size=(200, 25))
        custom_board_serial_number_textbox.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        custom_board_serial_number_textbox.SetToolTip("Enter a custom board serial number here. This will be used for the SMBIOS and iMessage.\n\nNote: This will not be used if the \"Use Custom Board Serial Number\" checkbox is not checked.")
        custom_board_serial_number_textbox.Bind(wx.EVT_TEXT, self.on_custom_board_serial_number_textbox)
        custom_board_serial_number_textbox.SetValue(self.constants.custom_board_serial_number)
        self.custom_board_serial_number_textbox = custom_board_serial_number_textbox

        # Button: Generate Serial Number (below)
        generate_serial_number_button = wx.Button(panel, label=f"生成 S/N: {self.constants.custom_model or self.constants.computer.real_model}", pos=(title.GetPosition()[0] - 30, custom_board_serial_number_label.GetPosition()[1] + 60), size=(200, 25))
        generate_serial_number_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        generate_serial_number_button.Bind(wx.EVT_BUTTON, self.on_generate_serial_number)


    def _populate_app_stats(self, panel: wx.Frame) -> None:
        title: wx.StaticText = None
        for child in panel.GetChildren():
            if child.GetLabel() == "统计":
                title = child
                break

        lines = f"""软件信息:
    软件版本: {self.constants.patcher_version}
    补丁支持包版本: {self.constants.patcher_support_pkg_version}
    软件路径: {self.constants.launcher_binary}
    软件加载: {self.constants.payload_path}

Commit Information:
    Branch: {self.constants.commit_info[0]}
    Date: {self.constants.commit_info[1]}
    URL: {self.constants.commit_info[2] if self.constants.commit_info[2] != "" else "N/A"}

启动信息:
    Booted OS: XNU {self.constants.detected_os} ({self.constants.detected_os_version})
    Booted Patcher Version: {self.constants.computer.oclp_version}
    Booted OpenCore Version: {self.constants.computer.opencore_version}
    Booted OpenCore Disk: {self.constants.booted_oc_disk}

硬件信息:
    {pprint.pformat(self.constants.computer, indent=4)}
"""
        # TextCtrl: properties
        self.app_stats = wx.TextCtrl(panel, value=lines, pos=(-1, title.GetPosition()[1] + 30), size=(600, 240), style=wx.TE_READONLY | wx.TE_MULTILINE | wx.TE_RICH2)
        self.app_stats.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))


    def on_checkbox(self, event: wx.Event, warning_pop: str = "", override_function: bool = False) -> None:
        """
        """
        label = event.GetEventObject().GetLabel()
        value = event.GetEventObject().GetValue()
        if warning_pop != "" and value is True:
            warning = wx.MessageDialog(self.frame_modal, warning_pop, f"Warning: {label}", wx.YES_NO | wx.ICON_WARNING | wx.NO_DEFAULT)
            if warning.ShowModal() == wx.ID_NO:
                event.GetEventObject().SetValue(not event.GetEventObject().GetValue())
                return
            if label == "Allow native models":
                if self.constants.computer.real_model in smbios_data.smbios_dictionary:
                    if self.constants.detected_os > smbios_data.smbios_dictionary[self.constants.computer.real_model]["Max OS Supported"]:
                        chassis_type = "aluminum"
                        if self.constants.computer.real_model in ["MacBook5,2", "MacBook6,1", "MacBook7,1"]:
                            chassis_type = "plastic"
                        dlg = wx.MessageDialog(self.frame_modal, f"This model, {self.constants.computer.real_model}, does not natively support macOS {os_data.os_conversion.kernel_to_os(self.constants.detected_os)}, {os_data.os_conversion.convert_kernel_to_marketing_name(self.constants.detected_os)}. The last native OS was macOS {os_data.os_conversion.kernel_to_os(smbios_data.smbios_dictionary[self.constants.computer.real_model]['Max OS Supported'])}, {os_data.os_conversion.convert_kernel_to_marketing_name(smbios_data.smbios_dictionary[self.constants.computer.real_model]['Max OS Supported'])}\n\nToggling this option will break booting on this OS. Are you absolutely certain this is desired?\n\nYou may end up with a nice {chassis_type} brick 🧱", "Are you certain?", wx.YES_NO | wx.ICON_WARNING | wx.NO_DEFAULT)
                        if dlg.ShowModal() == wx.ID_NO:
                            event.GetEventObject().SetValue(not event.GetEventObject().GetValue())
                            return
        if override_function is True:
            self.settings[self._find_parent_for_key(label)][label]["override_function"](self.settings[self._find_parent_for_key(label)][label]["variable"], value, self.settings[self._find_parent_for_key(label)][label]["constants_variable"] if "constants_variable" in self.settings[self._find_parent_for_key(label)][label] else None)
            return

        self._update_setting(self.settings[self._find_parent_for_key(label)][label]["variable"], value)
        if label == "Allow native models":
            if gui_support.CheckProperties(self.constants).host_can_build() is True:
                self.parent.build_button.Enable()
            else:
                self.parent.build_button.Disable()


    def on_spinctrl(self, event: wx.Event, label: str) -> None:
        """
        """
        value = event.GetEventObject().GetValue()
        self._update_setting(self.settings[self._find_parent_for_key(label)][label]["variable"], value)


    def _update_setting(self, variable, value):
        logging.info(f"Updating Local Setting: {variable} = {value}")
        setattr(self.constants, variable, value)
        tmp_value = value
        if tmp_value is None:
            tmp_value = "PYTHON_NONE_VALUE"
        global_settings.GlobalEnviromentSettings().write_property(f"GUI:{variable}", tmp_value)


    def _update_global_settings(self, variable, value, global_setting = None):
        logging.info(f"Updating Global Setting: {variable} = {value}")
        tmp_value = value
        if tmp_value is None:
            tmp_value = "PYTHON_NONE_VALUE"
        global_settings.GlobalEnviromentSettings().write_property(variable, tmp_value)
        if global_setting is not None:
            self._update_setting(global_setting, value)


    def _update_system_defaults(self, variable, value, global_setting = None):
        value_type = type(value)
        if value_type is str:
            value_type = "-string"
        elif value_type is int:
            value_type = "-int"
        elif value_type is bool:
            value_type = "-bool"

        logging.info(f"Updating System Defaults: {variable} = {value} ({value_type})")
        subprocess.run(["/usr/bin/defaults", "write", "-globalDomain", variable, value_type, str(value)])


    def _update_system_defaults_root(self, variable, value, global_setting = None):
        value_type = type(value)
        if value_type is str:
            value_type = "-string"
        elif value_type is int:
            value_type = "-int"
        elif value_type is bool:
            value_type = "-bool"

        logging.info(f"Updating System Defaults (root): {variable} = {value} ({value_type})")
        subprocess_wrapper.run_as_root(["/usr/bin/defaults", "write", "/Library/Preferences/.GlobalPreferences.plist", variable, value_type, str(value)])


    def _find_parent_for_key(self, key: str) -> str:
        for parent in self.settings:
            if key in self.settings[parent]:
                return parent


    def on_sip_value(self, event: wx.Event) -> None:
        """
        """
        dict = sip_data.system_integrity_protection.csr_values_extended[f"CSR_{event.GetEventObject().GetLabel()}"]

        if event.GetEventObject().GetValue() is True:
            self.sip_value = self.sip_value + dict["value"]
        else:
            self.sip_value = self.sip_value - dict["value"]

        if hex(self.sip_value) == "0x0":
            self.constants.custom_sip_value = None
            self.constants.sip_status = True
        elif hex(self.sip_value) == "0x803":
            self.constants.custom_sip_value = None
            self.constants.sip_status = False
        else:
            self.constants.custom_sip_value = hex(self.sip_value)

        self.sip_configured_label.SetLabel(f"当前配置的SIP: {hex(self.sip_value)}")

    def on_choice(self, event: wx.Event, label: str) -> None:
        """
        """
        value = event.GetString()
        self._update_setting(self.settings[self._find_parent_for_key(label)][label]["variable"], value)


    def on_generate_serial_number(self, event: wx.Event) -> None:
        dlg = wx.MessageDialog(self.frame_modal, "使用序列号覆写时请小心，这只能在合法获得并需要重新覆写序列号的机器上使用。\n\n注意：新的序列号仅通过 OpenCore 覆盖，不会永久安装到 ROM 中。\n\n如果系统不需要仿冒，滥用此设置可能会破坏电源管理和操作系统。\n\nlaobamac 不容忍在被盗设备上使用OCLP-Mod！如经发现，OCLP-Mod将根据法律与MIT License追究责任。\n\n您确定要继续吗？", "警告", wx.YES_NO | wx.ICON_WARNING | wx.NO_DEFAULT)
        if dlg.ShowModal() != wx.ID_YES:
            return

        macserial_output = subprocess.run([self.constants.macserial_path, "--generate", "--model", self.constants.custom_model or self.constants.computer.real_model, "--num", "1"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        macserial_output = macserial_output.stdout.decode().strip().split(" | ")
        if len(macserial_output) == 2:
            self.custom_serial_number_textbox.SetValue(macserial_output[0])
            self.custom_board_serial_number_textbox.SetValue(macserial_output[1])
        else:
            wx.MessageBox(f"生成序列号失败:\n\n{macserial_output}", "错误", wx.OK | wx.ICON_ERROR)


    def on_custom_serial_number_textbox(self, event: wx.Event) -> None:
        self.constants.custom_serial_number = event.GetEventObject().GetValue()


    def on_custom_board_serial_number_textbox(self, event: wx.Event) -> None:
        self.constants.custom_board_serial_number = event.GetEventObject().GetValue()


    def _populate_fu_override(self, panel: wx.Panel) -> None:
        gpu_combo_box: wx.Choice = None
        for child in panel.GetChildren():
            if isinstance(child, wx.Choice):
                gpu_combo_box = child
                break

        gpu_combo_box.Bind(wx.EVT_CHOICE, self.fu_selection_click)
        if self.constants.fu_status is False:
            gpu_combo_box.SetStringSelection("Disabled")
        elif self.constants.fu_arguments is None:
            gpu_combo_box.SetStringSelection("Enabled")
        else:
            gpu_combo_box.SetStringSelection("Partial")


    def fu_selection_click(self, event: wx.Event) -> None:
        value = event.GetEventObject().GetStringSelection()
        if value == "Enabled":
            logging.info("Updating FU Status: Enabled")
            self.constants.fu_status = True
            self.constants.fu_arguments = None
            return

        if value == "Partial":
            logging.info("Updating FU Status: Partial")
            self.constants.fu_status = True
            self.constants.fu_arguments = " -disable_sidecar_mac"
            return

        logging.info("Updating FU Status: Disabled")
        self.constants.fu_status = False
        self.constants.fu_arguments = None


    def _populate_graphics_override(self, panel: wx.Panel) -> None:
        gpu_combo_box: wx.Choice = None
        index = 0
        for child in panel.GetChildren():
            if isinstance(child, wx.Choice):
                if index == 0:
                    index = index + 1
                    continue
                gpu_combo_box = child
                break

        gpu_combo_box.Bind(wx.EVT_CHOICE, self.gpu_selection_click)
        gpu_combo_box.SetStringSelection(f"{self.constants.imac_vendor} {self.constants.imac_model}")

        socketed_gpu_models = ["iMac9,1", "iMac10,1", "iMac11,1", "iMac11,2", "iMac11,3", "iMac12,1", "iMac12,2"]
        if ((not self.constants.custom_model and self.constants.computer.real_model not in socketed_gpu_models) or (self.constants.custom_model and self.constants.custom_model not in socketed_gpu_models)):
            gpu_combo_box.Disable()
            return


    def gpu_selection_click(self, event: wx.Event) -> None:
        gpu_choice = event.GetEventObject().GetStringSelection()

        logging.info(f"Updating GPU Selection: {gpu_choice}")
        if "AMD" in gpu_choice:
            self.constants.imac_vendor = "AMD"
            self.constants.metal_build = True
            if "Polaris" in gpu_choice:
                self.constants.imac_model = "Polaris"
            elif "GCN" in gpu_choice:
                self.constants.imac_model = "GCN"
            elif "Lexa" in gpu_choice:
                self.constants.imac_model = "Lexa"
            elif "Navi" in gpu_choice:
                self.constants.imac_model = "Navi"
            else:
                raise Exception("Unknown GPU Model")
        elif "Nvidia" in gpu_choice:
            self.constants.imac_vendor = "Nvidia"
            self.constants.metal_build = True
            if "Kepler" in gpu_choice:
                self.constants.imac_model = "Kepler"
            elif "GT" in gpu_choice:
                self.constants.imac_model = "GT"
            else:
                raise Exception("Unknown GPU Model")
        else:
            self.constants.imac_vendor = "None"
            self.constants.metal_build = False


    def _get_system_settings(self, variable) -> bool:
        result = subprocess.run(["/usr/bin/defaults", "read", "-globalDomain", variable], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode == 0:
            try:
                return bool(int(result.stdout.decode().strip()))
            except:
                return False
        return False


    def on_return(self, event):
        self.frame_modal.Destroy()


    def on_nightly(self, event: wx.Event) -> None:
        # Ask prompt for which branch
        branches = ["main"]
        if self.constants.commit_info[0] not in ["Running from source", "Built from source"]:
            branches = [self.constants.commit_info[0].split("/")[-1]]
        result = network_handler.NetworkUtilities().get("https://api.github.com/repos/laobamac/oclp-mod/branches")
        if result is not None:
            result = result.json()
            for branch in result:
                if branch["name"] == "gh-pages":
                    continue
                if branch["name"] not in branches:
                    branches.append(branch["name"])

            with wx.SingleChoiceDialog(self.parent, "Which branch would you like to download?", "Branch Selection", branches) as dialog:
                if dialog.ShowModal() == wx.ID_CANCEL:
                    return

                branch = dialog.GetStringSelection()
        else:
            branch = "main"

        gui_update.UpdateFrame(
            parent=self.parent,
            title=self.title,
            global_constants=self.constants,
            screen_location=self.parent.GetPosition(),
            url=f"https://nightly.link/laobamac/oclp-mod/workflows/build-app-wxpython/{branch}/OCLP-Mod.pkg.zip",
            version_label="(Nightly)"
        )


    def on_export_constants(self, event: wx.Event) -> None:
        # Throw pop up to get save location
        with wx.FileDialog(self.parent, "Save Constants File", wildcard="JSON files (*.txt)|*.txt", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT, defaultFile=f"constants-{self.constants.patcher_version}.txt") as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return

            # Save the current contents in the file
            pathname = fileDialog.GetPath()
            logging.info(f"Saving constants to {pathname}")
            with open(pathname, 'w') as file:
                file.write(pprint.pformat(vars(self.constants), indent=4))


    def on_test_exception(self, event: wx.Event) -> None:
        raise Exception("Test Exception")

    def on_mount_root_vol(self, event: wx.Event) -> None:
        #Don't need to pass model as we're bypassing all logic
        if sys_patch.PatchSysVolume("",self.constants)._mount_root_vol() == True:
            wx.MessageDialog(self.parent, "Root Volume Mounted, remember to fix permissions before saving the Root Volume", "Success", wx.OK | wx.ICON_INFORMATION).ShowModal()
        else:
            wx.MessageDialog(self.parent, "Root Volume Mount Failed, check terminal output", "Error", wx.OK | wx.ICON_ERROR).ShowModal()

    def on_bless_root_vol(self, event: wx.Event) -> None:
        #Don't need to pass model as we're bypassing all logic
        if sys_patch.PatchSysVolume("",self.constants)._rebuild_root_volume() == True:
            wx.MessageDialog(self.parent, "Root Volume saved, please reboot to apply changes", "Success", wx.OK | wx.ICON_INFORMATION).ShowModal()
        else:
            wx.MessageDialog(self.parent, "Root Volume update Failed, check terminal output", "Error", wx.OK | wx.ICON_ERROR).ShowModal()