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
from ..languages.language_handler import LanguageHandler

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
        self.language_handler = LanguageHandler(self.constants)
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

        model_label = wx.StaticText(frame, label=self.language_handler.get_translation("Target_model"), pos=(-1, -1))
        model_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
        sizer.Add(model_label, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        model_choice = wx.Choice(frame, choices=model_array.SupportedSMBIOS + [self.language_handler.get_translation("Host_model")], pos=(-1, -1), size=(150, -1))
        model_choice.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        model_choice.Bind(wx.EVT_CHOICE, lambda event: self.on_model_choice(event, model_choice))
        selection = self.constants.custom_model if self.constants.custom_model else self.language_handler.get_translation("Host_model")
        model_choice.SetSelection(model_choice.FindString(selection))
        sizer.Add(model_choice, 0, wx.ALIGN_CENTER | wx.ALL, 5)

        model_description = wx.StaticText(frame, label=self.language_handler.get_translation("Themodelthatthepatcherisgoingtoimitate."), pos=(-1, -1))
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
        return_button = wx.Button(frame, label=self.language_handler.get_translation("back", "kembali"), pos=(-1, -1), size=(100, 30))
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
            self.language_handler.get_translation("membuat"): {
                self.language_handler.get_translation("ringkasan"): {
                    "type": "title",
                },
                self.language_handler.get_translation("Booting_firmware"): {
                    "type": "checkbox",
                    "value": self.constants.firewire_boot,
                    "variable": "firewire_boot",
                    "description": [
                        self.language_handler.get_translation("enable_fireware_driver"),
                        self.language_handler.get_translation("start_macos"),
                    ],
                    "condition": not (generate_smbios.check_firewire(self.constants.custom_model or self.constants.computer.real_model) is False)
                },
                self.language_handler.get_translation("start_XHCI"): {
                    "type": "checkbox",
                    "value": self.constants.xhci_boot,
                    "variable": "xhci_boot",
                    "description": [
                        self.language_handler.get_translation("In_a_system_without_native_support_activate"),
                        self.language_handler.get_translation("usb_expansion"),
                    ],
                    "condition": not gui_support.CheckProperties(self.constants).host_has_cpu_gen(cpu_data.CPUGen.ivy_bridge) # Sandy Bridge and older do not natively support XHCI booting
                },
                self.language_handler.get_translation("booting_nvme"): {
                    "type": "checkbox",
                    "value": self.constants.nvme_boot,
                    "variable": "nvme_boot",
                    "description": [
                        self.language_handler.get_translation("start_macos"),
                        self.language_handler.get_translation("Non-original_NVMe_drive"),
                        self.language_handler.get_translation("support"),
                        self.language_handler.get_translation("Note:_Your_machine_must_support_NVMe."),
                        self.language_handler.get_translation("OC_can_be_booted_from_the_NVMe_drive."),
                    ],
                    "condition": not gui_support.CheckProperties(self.constants).host_has_cpu_gen(cpu_data.CPUGen.ivy_bridge) # Sandy Bridge and older do not natively support NVMe booting
                },
                "wrap_around 2": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Protection_of_OpenCore_Digital_Signature"): {
                    "type": "checkbox",
                    "value": self.constants.vault,
                    "variable": "vault",
                    "description": [
                        self.language_handler.get_translation("description_digitaly_signin"),
                    ],
                },

                self.language_handler.get_translation("Displaying_the_OpenCore_boot_interface"): {
                    "type": "checkbox",
                    "value": self.constants.showpicker,
                    "variable": "showpicker",
                    "description": [
                        self.language_handler.get_translation("when_deactive"),
                    ],
                },
                self.language_handler.get_translation("Boot_interface_wait_time"): {
                    "type": "spinctrl",
                    "value": self.constants.oc_timeout,
                    "variable": "oc_timeout",
                    "description": [
                        self.language_handler.get_translation("On_the_boot_selector,_choose_default."),
                        self.language_handler.get_translation("Time_runs_out_a_second_before_entering."),
                        self.language_handler.get_translation("Setting_this_to_0_means_there_is_no_deadline."),
                    ],

                    "min": 0,
                    "max": 60,
                },
                self.language_handler.get_translation("MacPro3.1/Xserve2.1Solutions"): {
                    "type": "checkbox",
                    "value": self.constants.force_quad_thread,
                    "variable": "force_quad_thread",
                    "description": [
                        self.language_handler.get_translation("Limitthemaximumnumberofthreadsonthisunitto4."),
                        self.language_handler.get_translation("RequiredformacOSSequoiaandnewerversions."),
                    ],
                    "condition": (self.constants.custom_model and self.constants.custom_model in ["MacPro3,1", "Xserve2,1"]) or self.constants.computer.real_model in ["MacPro3,1", "Xserve2,1"]
                },
                self.language_handler.get_translation("Debugging"): {
                    "type": "title",
                },

#                "Mode Verbose": {
#                    "type": "checkbox",
#                    "value": self.constants.verbose_debug,
#                    "variable": "verbose_debug",
#                    "description": [
#                       self.language_handler.get_translation("Outputverboseinformationupon_startup"),
#                    ],
#                },

                self.language_handler.get_translation("verbose_debug"): {
                    "type": "checkbox",
                    "value": self.constants.verbose_debug,
                    "variable": "verbose_debug",
                    "description": [
                        self.language_handler.get_translation("Outputverboseinformationupon_startup"),
                    ],
                },            
            
                self.language_handler.get_translation("debug_version_driver"): {
                    "type": "checkbox",
                    "value": self.constants.kext_debug,
                    "variable": "kext_debug",
                    "description": [
                        self.language_handler.get_translation("use_debug"),
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("debugging_OpenCore_version"): {
                    "type": "checkbox",
                    "value": self.constants.opencore_debug,
                    "variable": "opencore_debug",
                    "description": [
                        self.language_handler.get_translation("Use_the_DEBUG_version")
                    ],
                },
            },
            self.language_handler.get_translation("Additional"): {
                self.language_handler.get_translation("Universal(effectivesustainability)"): {
                    "type": "title",
                },
                "WOL": {
                    "type": "checkbox",
                    "value": self.constants.enable_wake_on_wlan,
                    "variable": "enable_wake_on_wlan",
                    "description": [
                        self.language_handler.get_translation("Disabled_by_default"),
                        self.language_handler.get_translation("Causes_performance_degradation"),
                        self.language_handler.get_translation("Applicable_only_to_BCM943224,_331,"),
                        self.language_handler.get_translation("360and3602chipsets."),
                    ],
                },
                self.language_handler.get_translation("Disable_Thunder"): {
                    "type": "checkbox",
                    "value": self.constants.disable_tb,
                    "variable": "disable_tb",
                    "description": [
                        self.language_handler.get_translation("Regarding_the_malfunction"),
                        self.language_handler.get_translation("PCHmayoccasionallycrashonMacBookPro11,x."),
                    ],
                    "condition": (self.constants.custom_model and self.constants.custom_model in ["MacBookPro11,1", "MacBookPro11,2", "MacBookPro11,3"]) or self.constants.computer.real_model in ["MacBookPro11,1", "MacBookPro11,2", "MacBookPro11,3"]
                },
                "Windows GMUX": {
                    "type": "checkbox",
                    "value": self.constants.dGPU_switch,
                    "variable": "dGPU_switch",
                    "description": [
                        self.language_handler.get_translation("Allow_exposing_iGPU_in_Windows"),
                        self.language_handler.get_translation("UsedfordGPU-basedMacBooks"),
                    ],
                },
                self.language_handler.get_translation("Disable_CPUFriend"): {
                    "type": "checkbox",
                    "value": self.constants.disallow_cpufriend,
                    "variable": "disallow_cpufriend",
                    "description": [
                    self.language_handler.get_translation("DisableCPUFriendforunsupportedmodels.")
                    ],
                },
                self.language_handler.get_translation("Disablethemediaanalysisdservice"): {
                    "type": "checkbox",
                    "value": self.constants.disable_mediaanalysisd,
                    "variable": "disable_mediaanalysisd",
                    "description": [
                        self.language_handler.get_translation("RegardingiCloudusing3802-BasedGPUs"),
                        self.language_handler.get_translation("Photos,this_may_delay."),
                        self.language_handler.get_translation("CPU_usage"),
                    ],
                    "condition": gui_support.CheckProperties(self.constants).host_has_3802_gpu()
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Allow_the_use_of_AppleALC_audio"): {
                    "type": "checkbox",
                    "value": self.constants.set_alc_usage,
                    "variable": "set_alc_usage",
                    "description": [
                        self.language_handler.get_translation("AllowAppleALCtomanageaudioifapplicable."),
                        self.language_handler.get_translation("DisabledonlywhenthehostlackstheGOPROM."),
                    ],
                },
                self.language_handler.get_translation("WritetoNVRAM"): {
                    "type": "checkbox",
                    "value": self.constants.nvram_write,
                    "variable": "nvram_write",
                    "description": [
                        self.language_handler.get_translation("AllowOpenCoretowritetoNVRAM."),
                        self.language_handler.get_translation("Incaseoramalfunctionor"),
                        self.language_handler.get_translation("DisabledondowngradedNVRAMsystem."),
                    ],
                },

                self.language_handler.get_translation("Third-partyNVMepowermanagement"): {
                    "type": "checkbox",
                    "value": self.constants.allow_nvme_fixing,
                    "variable": "allow_nvme_fixing",
                    "description": [
                        self.language_handler.get_translation("EnableunprovidedfeaturesinmacOS"),
                        self.language_handler.get_translation("NVMepowermanagement"),
                    ],
                },
                self.language_handler.get_translation("Third-partySATApowermanagement"): {
                    "type": "checkbox",
                    "value": self.constants.allow_3rd_party_drives,
                    "variable": "allow_3rd_party_drives",
                    "description": [
                        self.language_handler.get_translation("EnableunprovidedfeaturesinmacOS"),
                        self.language_handler.get_translation("SATA_power_management"),
                    ],
                    "condition": not bool(self.constants.computer.third_party_sata_ssd is False and not self.constants.custom_model)
                },
                self.language_handler.get_translation("Trim_related"): {
                    "type": "checkbox",
                    "value": self.constants.apfs_trim_timeout,
                    "variable": "apfs_trim_timeout",
                    "description": [
                        self.language_handler.get_translation("Itisrecommendedthatallusersuseit,evenifthereareissues."),
                        self.language_handler.get_translation("SSDsmayalsobenefitfromdisablingthisfeature."),
                    ],
                },
            },
            self.language_handler.get_translation("advanced"): {
                self.language_handler.get_translation("Various_kinds"): {
                    "type": "title",
                },
                self.language_handler.get_translation("Disable_Firmware_Throttling"): {
                    "type": "checkbox",
                    "value": self.constants.disable_fw_throttle,
                    "variable": "disable_fw_throttle",
                    "description": [
                        self.language_handler.get_translation("Disable_firmware-based_restrictions"),
                        self.language_handler.get_translation("Caused_by_lack_of_hardware"),
                        self.language_handler.get_translation("Forexample,missingmonitors,batteries,etc."),
                    ],
                },
                self.language_handler.get_translation("Software_DeMUX"): {
                    "type": "checkbox",
                    "value": self.constants.software_demux,
                    "variable": "software_demux",
                    "description": [
                        self.language_handler.get_translation("Enable_software-based_DeMUX"),
                        self.language_handler.get_translation("Applicable_to_MacBookPro8,2_and_MacBookPro8,3."),
                        self.language_handler.get_translation("Prevent_the_faulty_dGPU_from_being_enabled."),
                        self.language_handler.get_translation("Note:Relevant_NVRAM_parameters_are_required:"),
                        "'gpu-power-prefs'.",
                    ],
                    "warning": "This settings requires 'gpu-power-prefs' NVRAM argument to be set to '1'.\n\nIf missing and this option is toggled, the system will not boot\n\nFull command:\nnvram FA4CE28D-B62F-4C99-9CC3-6815686E30F9:gpu-power-prefs=%01%00%00%00",
                    "condition": not bool((not self.constants.custom_model and self.constants.computer.real_model not in ["MacBookPro8,2", "MacBookPro8,3"]) or (self.constants.custom_model and self.constants.custom_model not in ["MacBookPro8,2", "MacBookPro8,3"]))
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Enable_unsupported_features"): {
                    "type": "choice",
                    "choices": [
                        "Enabled",
                        "Partial",
                        "Disabled",
                    ],
                    "value": "Enabled",
                    "variable": "",
                    "description": [
                        self.language_handler.get_translation("Configure_FeatureUnlock_level."),
                        self.language_handler.get_translation("If_your_system_prompts_to_suggest_lowering"),
                        self.language_handler.get_translation("Due_to_encountering_unstable_memory."),
                    ],
                },
                "Populate FeatureUnlock Override": {
                    "type": "populate",
                    "function": self._populate_fu_override,
                    "args": wx.Frame,
                },
                self.language_handler.get_translation("Sleep_Plan"): {
                    "type": "checkbox",
                    "value": self.constants.disable_connectdrivers,
                    "variable": "disable_connectdrivers",
                    "description": [
                        self.language_handler.get_translation("Load_only_the_minimum_EFI_drivers"),
                        self.language_handler.get_translation("Prevent_sleep_issues"),
                        self.language_handler.get_translation("Note:This_may_interrupt_from"),
                        self.language_handler.get_translation("Booting_from_an_external_hard_drive"),
                    ],
                },
                self.language_handler.get_translation("Graphics_card"): {
                    "type": "title",
                },
                self.language_handler.get_translation("AMD_GOP_injection"): {
                    "type": "checkbox",
                    "value": self.constants.amd_gop_injection,
                    "variable": "amd_gop_injection",
                    "description": [
                        self.language_handler.get_translation("Inject_AMD_GOP_to_display"),
                        self.language_handler.get_translation("Start_screen"),
                    ],
                    "condition": not bool((not self.constants.custom_model and self.constants.computer.real_model not in socketed_gpu_models) or (self.constants.custom_model and self.constants.custom_model not in socketed_gpu_models))
                },
                self.language_handler.get_translation("Nvidia_GOP_injection"): {
                    "type": "checkbox",
                    "value": self.constants.nvidia_kepler_gop_injection,
                    "variable": "nvidia_kepler_gop_injection",
                    "description": [
                        self.language_handler.get_translation("Inject_Nvidia_Kepler_GOP_for_sisplay"),
                        self.language_handler.get_translation("Start_screen"),
                    ],
                    "condition": not bool((not self.constants.custom_model and self.constants.computer.real_model not in socketed_gpu_models) or (self.constants.custom_model and self.constants.custom_model not in socketed_gpu_models))
                },
                "wrap_around 2": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Graphics_card_overwrite"): {
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
                        self.language_handler.get_translation("Cover_detected/hypothetical_MXM_graphics_card"),
                        self.language_handler.get_translation("Applicable_to_MXM-based_iMacs."),
                    ],
                    "condition": bool((not self.constants.custom_model and self.constants.computer.real_model in socketed_imac_models) or (self.constants.custom_model and self.constants.custom_model in socketed_imac_models))
                },
                "Populate Graphics Override": {
                    "type": "populate",
                    "function": self._populate_graphics_override,
                    "args": wx.Frame,
                },

            },
            self.language_handler.get_translation("Security"): {
                self.language_handler.get_translation("Kernel_Security"): {
                    "type": "title",
                },
                self.language_handler.get_translation("Disable_resource_library_validation"): {
                    "type": "checkbox",
                    "value": self.constants.disable_cs_lv,
                    "variable": "disable_cs_lv",
                    "description": [
                        self.language_handler.get_translation("After_injecting_modifications_while_patching"),
                        self.language_handler.get_translation("When_the_system_files_are_needed"),
                    ],
                },
                self.language_handler.get_translation("Disable_AMFI"): {
                    "type": "checkbox",
                    "value": self.constants.disable_amfi,
                    "variable": "disable_amfi",
                    "description": [
                        self.language_handler.get_translation("After_injecting_modifications_while_patching"),
                        self.language_handler.get_translation("When_the_system_files_are_needed"),
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Safe_boot_model"): {
                    "type": "checkbox",
                    "value": self.constants.secure_status,
                    "variable": "secure_status",
                    "description": [
                        self.language_handler.get_translation("Set_Apple_Secure_Boot_Model_Identifier"),
                        self.language_handler.get_translation("If_it_has_been_counterfeited,then_match_the_T2_model."),
                        self.language_handler.get_translation("Note:Incompatible_with_driver_patches"),
                    ],
                },
                self.language_handler.get_translation("System_Integrity_Protection_(SIP)"): {
                    "type": "title",
                },
                "Populate SIP": {
                    "type": "populate",
                    "function": self._populate_sip_settings,
                    "args": wx.Frame,
                },
            },
            "SMBIOS": {
                self.language_handler.get_translation("Model_Replacement"): {
                    "type": "title",
                },
                self.language_handler.get_translation("SMBIOS_Replacement_Level"): {
                    "type": "choice",
                    "choices": [
                        self.language_handler.get_translation("None"),
                        self.language_handler.get_translation("Minimal"),
                        self.language_handler.get_translation("Moderate"),
                        self.language_handler.get_translation("advanced"),
                    ],
                    "value": self.constants.serial_settings,
                    "variable": "serial_settings",
                    "description": [
                        self.language_handler.get_translation("Supported_levels:"),
                        self.language_handler.get_translation("- None:_None"),
                        self.language_handler.get_translation("- Small:_Board_ID."),
                        self.language_handler.get_translation("- Inside:_Change_Model."),
                        self.language_handler.get_translation("- Height:_Change_model_and_serial.")
                    ],
                },

                self.language_handler.get_translation("SMBIOS_Model_Replacement"): {
                    "type": "choice",
                    "choices": models + [self.language_handler.get_translation("Default")],
                    "value": self.constants.override_smbios,
                    "variable": "override_smbios",
                    "description": [
                        self.language_handler.get_translation("Prepare_a_fake_model"),
                    ],

                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Enables_replacement_of_natively_supported_Macs"): {
                    "type": "checkbox",
                    "value": self.constants.allow_native_spoofs,
                    "variable": "allow_native_spoofs",
                    "description": [
                        "",
                        self.language_handler.get_translation("Allow_OpenCore_to_mimic_native"),
                        self.language_handler.get_translation("Supported_Mac."),
                        self.language_handler.get_translation("Mainly_used_to_activate"),
                        self.language_handler.get_translation("Universal_Control_on_unsupported_Mac"),
                    ],
                },
                self.language_handler.get_translation("Serial_number_overwrite"): {
                    "type": "title",
                },
                "Populate 序列号覆写": {
                    "type": "populate",
                    "function": self._populate_serial_spoofing_settings,
                    "args": wx.Frame,
                },
            },
            self.language_handler.get_translation("Patching"): {
                self.language_handler.get_translation("Patch_root_directory"): {
                    "type": "title",
                },
                self.language_handler.get_translation("TeraScale_2_Acceleration"): {
                    "type": "checkbox",
                    "value": global_settings.GlobalEnviromentSettings().read_property("MacBookPro_TeraScale_2_Accel") or self.constants.allow_ts2_accel,
                    "variable": "MacBookPro_TeraScale_2_Accel",
                    "constants_variable": "allow_ts2_accel",
                    "description": [
                        self.language_handler.get_translation("Activating_AMD_TeraScale_2_GPU"),
                        self.language_handler.get_translation("On_the_MacBookPro8,2_and"),
                        self.language_handler.get_translation("Acceleration_on_MacBookPro8,3."),
                        self.language_handler.get_translation("This_is_disabled_by_default_because"),
                        self.language_handler.get_translation("This_GPU_model_has_common_failures.")
                    ],
                    "override_function": self._update_global_settings,
                    "condition": not bool(self.constants.computer.real_model not in ["MacBookPro8,2", "MacBookPro8,3"])
                },
                self.language_handler.get_translation("Allow_the_installation_of_the_old_HDA_environment_extension_patch"): {
                    "type": "checkbox",
                    "value": self.constants.allow_hda_patch,
                    "variable": "allow_hda_patch",
                    "description": [
                        "",
                        self.language_handler.get_translation("Allowed_on_Tahoe_system_and_above"),
                        self.language_handler.get_translation("Activate_the_AppleHDA_driver_for_the_sound_card"),
                        self.language_handler.get_translation("With_AppleALC.kext")
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Allow_the_installation_of_the_old_USB_environment_extension_patch"): {
                    "type": "checkbox",
                    "value": self.constants.allow_usb_patch,
                    "variable": "allow_usb_patch",
                    "description": [
                        "",
                        self.language_handler.get_translation("Allowed_on_Tahoe_system_and_above"),
                        self.language_handler.get_translation("Installing_USB_Legacy_Environment_Extension")
                    ],
                },
                "wrap_around 1": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Non-Metal_Configuration"): {
                    "type": "title",
                },
                self.language_handler.get_translation("Logout_is_required_to_apply_changes_to_SkyLight"): {
                    "type": "sub_title",
                },
                self.language_handler.get_translation("Dark_Mode_Menu"): {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_DarkMenuBar"),
                    "variable": "Moraea_DarkMenuBar",
                    "description": [
                        self.language_handler.get_translation("If_the_Beta_menu_bar_is_activated,the_menu_bar_color_will_be_dynamic_as_needed"),
                        # self.language_handler.get_translation("change")
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                self.language_handler.get_translation("beta_blur"): {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_BlurBeta"),
                    "variable": "Moraea_BlurBeta",
                    "description": [
                        self.language_handler.get_translation("Control_window_blur_behaviour."),
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)

                },
                self.language_handler.get_translation("Solution_to_load_the_cursor_(rainbow_circle)"): {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea.EnableSpinHack"),
                    "variable": "Moraea.EnableSpinHack",
                    "description": [
                        self.language_handler.get_translation("Note:May_use_more_CPU_resources."),
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                "wrap_around 2": {
                    "type": "wrap_around",
                },
                self.language_handler.get_translation("Beta_Menu_Bar"): {
                    "type": "checkbox",
                    "value": self._get_system_settings("Amy.MenuBar2Beta"),
                    "variable": "Amy.MenuBar2Beta",
                    "description": [
                        self.language_handler.get_translation("support_for_dynamic_color")
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                self.language_handler.get_translation("Disable_Beta_Rim"): {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_RimBetaDisabled"),
                    "variable": "Moraea_RimBetaDisabled",
                    "description": [
                        self.language_handler.get_translation("Control_the_window_edge_rendering_effect"),
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
                self.language_handler.get_translation("Control_the_application_of_widget_colors_on_the_desktop"): {
                    "type": "checkbox",
                    "value": self._get_system_settings("Moraea_ColorWidgetDisabled"),
                    "variable": "Moraea_ColorWidgetDisabled",
                    "description": [
                        self.language_handler.get_translation("Control_the_application_of_widget_colors_on_the_desktop"),
                    ],
                    "override_function": self._update_system_defaults,
                    "condition": gui_support.CheckProperties(self.constants).host_is_non_metal(general_check=True)
                },
            },
            self.language_handler.get_translation("App"): {
                self.language_handler.get_translation("General"): {
                    "type": "title",
                },
                self.language_handler.get_translation("Allow_native_models"): {
                    "type": "checkbox",
                    "value": self.constants.allow_oc_everywhere,
                    "variable": "allow_oc_everywhere",
                    "description": [
                        self.language_handler.get_translation("Allows_the_installation_of_OpenCore")
                    ],
                    "注意": self.language_handler.get_translation("attention_this_option_should"),
                },
                self.language_handler.get_translation("Ignore_app_updates"): {
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
                self.language_handler.get_translation("Disabled_Report"): {
                    "type": "checkbox",
                    "value": global_settings.GlobalEnviromentSettings().read_property("DisableCrashAndAnalyticsReporting"),
                    "variable": "DisableCrashAndAnalyticsReporting",
                    "description": [
                        self.language_handler.get_translation("When_enabled,_the_patch_will_not_report_any_information_to_laobamac.")
                    ],
                    "override_function": self._update_global_settings,
                },
                self.language_handler.get_translation("Remove_unused_KDK"): {
                    "type": "checkbox",
                    "value": global_settings.GlobalEnviromentSettings().read_property("ShouldNukeKDKs") or self.constants.should_nuke_kdks,
                    "variable": "ShouldNukeKDKs",
                    "constants_variable": "should_nuke_kdks",
                    "description": [
                        self.language_handler.get_translation("WhenenabledtheapplicationwillremoveunusedKDKsfromthesystemduringrootdirectorypatching"),
                    ],
                    "override_function": self._update_global_settings,
                },
                self.language_handler.get_translation("Statistics"): {
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
            if child.GetLabel() == self.language_handler.get_translation("System_Integrity_Protection_(SIP)"):
                sip_title = child
                break

        # Calculate center position based on title
        title_pos = sip_title.GetPosition()
        title_width = sip_title.GetSize().width
        center_x = title_pos.x + (title_width // 2)

        # Label: Flip individual bits corresponding to XNU's csr.h
        # If you're unfamiliar with how SIP works, do not touch this menu
        sip_label = wx.StaticText(panel, label=self.language_handler.get_translation("Reverse_corresponds_to"))
        sip_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))

        # Calculate label position to be centered
        label_width = sip_label.GetSize().width
        sip_label.SetPosition((center_x - (label_width // 2), title_pos.y + 30))

        # Hyperlink: csr.h
        spacer = 1 if self.constants.detected_os >= os_data.os_data.big_sur else 3
        sip_csr_h = wx.adv.HyperlinkCtrl(panel, id=wx.ID_ANY, label="XNU's csr.h",
                                         url="https://github.com/apple-oss-distributions/xnu/blob/xnu-8020.101.4/bsd/sys/csr.h")
        sip_csr_h.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        sip_csr_h.SetHoverColour(self.hyperlink_colour)
        sip_csr_h.SetNormalColour(self.hyperlink_colour)
        sip_csr_h.SetVisitedColour(self.hyperlink_colour)

        # Position hyperlink next to label
        hyperlink_x = sip_label.GetPosition().x + sip_label.GetSize().width + 4
        sip_csr_h.SetPosition((hyperlink_x, sip_label.GetPosition().y + spacer))

        # Label: SIP Status
        if self.constants.custom_sip_value is not None:
            self.sip_value = int(self.constants.custom_sip_value, 16)
        elif self.constants.sip_status is True:
            self.sip_value = 0x00
        else:
            self.sip_value = 0x803

        sip_configured_label = wx.StaticText(panel,
                                             label=f"{self.language_handler.get_translation('Current_set_SIP:')} {hex(self.sip_value)}")
        sip_configured_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))
        # Center this label
        configured_width = sip_configured_label.GetSize().width
        sip_configured_label.SetPosition((center_x - (configured_width // 2), sip_label.GetPosition().y + 20))
        self.sip_configured_label = sip_configured_label

        # Label: SIP Status
        sip_booted_label = wx.StaticText(panel,
                                         label=f"{self.language_handler.get_translation('Currently_started_SIP:')} {hex(py_sip_xnu.SipXnu().get_sip_status().value)}")
        sip_booted_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        # Center this label
        booted_width = sip_booted_label.GetSize().width
        sip_booted_label.SetPosition((center_x - (booted_width // 2), sip_configured_label.GetPosition().y + 20))

        # SIP toggles
        entries_per_row = len(sip_data.system_integrity_protection.csr_values) // 2
        horizontal_spacer = 15
        vertical_spacer = 25
        index = 1
        for sip_bit in sip_data.system_integrity_protection.csr_values_extended:
            self.sip_checkbox = wx.CheckBox(panel, label=
            sip_data.system_integrity_protection.csr_values_extended[sip_bit]["name"].split("CSR_")[1])
            self.sip_checkbox.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
            self.sip_checkbox.SetToolTip(
                f'Description: {sip_data.system_integrity_protection.csr_values_extended[sip_bit]["description"]}\nValue: {hex(sip_data.system_integrity_protection.csr_values_extended[sip_bit]["value"])}\nIntroduced in: macOS {sip_data.system_integrity_protection.csr_values_extended[sip_bit]["introduced_friendly"]}')

            if self.sip_value & sip_data.system_integrity_protection.csr_values_extended[sip_bit]["value"] == \
                    sip_data.system_integrity_protection.csr_values_extended[sip_bit]["value"]:
                self.sip_checkbox.SetValue(True)

            # Position checkbox
            self.sip_checkbox.SetPosition((vertical_spacer, sip_booted_label.GetPosition().y + 20 + horizontal_spacer))

            horizontal_spacer += 20
            if index == entries_per_row:
                horizontal_spacer = 15
                vertical_spacer += 250

            index += 1
            self.sip_checkbox.Bind(wx.EVT_CHECKBOX, self.on_sip_value)

    def _populate_serial_spoofing_settings(self, panel: wx.Frame) -> None:
        title: wx.StaticText = None
        for child in panel.GetChildren():
            if child.GetLabel() == self.language_handler.get_translation("Serial_number_overwrite"):
                title = child
                break

        # Calculate positions based on title position
        title_pos = title.GetPosition()

        # Field dimensions
        field_width = 200
        spacing = 20

        # Calculate center position relative to title
        # We'll use the title's x position as our reference point
        center_x = title_pos.x + (title.GetSize().width // 2)

        # Position for left field (Custom Serial Number)
        left_x = center_x - field_width - spacing // 2

        # Position for right field (Custom Board Serial Number)
        right_x = center_x + spacing // 2

        # Vertical positions
        label_y = title_pos.y + 30
        textbox_y = label_y + 20
        button_y = textbox_y + 40

        # Label: Custom Serial Number
        custom_serial_number_label = wx.StaticText(
            panel,
            label=self.language_handler.get_translation("custom_serial"),
            pos=(left_x, label_y)
        )
        custom_serial_number_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))

        # Textbox: Custom Serial Number
        custom_serial_number_textbox = wx.TextCtrl(
            panel,
            pos=(left_x, textbox_y),
            size=(field_width, 25)
        )
        custom_serial_number_textbox.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        custom_serial_number_textbox.SetToolTip("Enter a custom serial number here...")
        custom_serial_number_textbox.Bind(wx.EVT_TEXT, self.on_custom_serial_number_textbox)
        custom_serial_number_textbox.SetValue(self.constants.custom_serial_number)
        self.custom_serial_number_textbox = custom_serial_number_textbox

        # Label: Custom Board Serial Number
        custom_board_serial_number_label = wx.StaticText(
            panel,
            label=self.language_handler.get_translation("custom_board_serial"),
            pos=(right_x, label_y)
        )
        custom_board_serial_number_label.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_BOLD))

        # Textbox: Custom Board Serial Number
        custom_board_serial_number_textbox = wx.TextCtrl(
            panel,
            pos=(right_x, textbox_y),
            size=(field_width, 25)
        )
        custom_board_serial_number_textbox.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        custom_board_serial_number_textbox.SetToolTip("Enter a custom board serial number here...")
        custom_board_serial_number_textbox.Bind(wx.EVT_TEXT, self.on_custom_board_serial_number_textbox)
        custom_board_serial_number_textbox.SetValue(self.constants.custom_board_serial_number)
        self.custom_board_serial_number_textbox = custom_board_serial_number_textbox

        # Button: Generate Serial Number (centered below both fields)
        generate_serial_number_button = wx.Button(
            panel,
            label=f"{self.language_handler.get_translation('generate_serial')} {self.constants.custom_model or self.constants.computer.real_model}",
            pos=(center_x - 100, button_y),
            size=(200, 25)
        )
        generate_serial_number_button.SetFont(gui_support.font_factory(13, wx.FONTWEIGHT_NORMAL))
        generate_serial_number_button.Bind(wx.EVT_BUTTON, self.on_generate_serial_number)


    def _populate_app_stats(self, panel: wx.Frame) -> None:
        title: wx.StaticText = None
        for child in panel.GetChildren():
            if child.GetLabel() == self.language_handler.get_translation("Statistics"):
                title = child
                break

        lines = f"""{self.language_handler.get_translation('Software_Information')}:
    {self.language_handler.get_translation("Software_version")}: {self.constants.patcher_version}
    {self.language_handler.get_translation("Patch_support_package_version")}: {self.constants.patcher_support_pkg_version}
    {self.language_handler.get_translation("Software_Path")}: {self.constants.launcher_binary}
    {self.language_handler.get_translation("Software_loading")}: {self.constants.payload_path}

Commit Information:
    Branch: {self.constants.commit_info[0]}
    Date: {self.constants.commit_info[1]}
    URL: {self.constants.commit_info[2] if self.constants.commit_info[2] != "" else "N/A"}

{self.language_handler.get_translation("Startup_information")}:
    Booted OS: XNU {self.constants.detected_os} ({self.constants.detected_os_version})
    Booted Patcher Version: {self.constants.computer.oclp_version}
    Booted OpenCore Version: {self.constants.computer.opencore_version}
    Booted OpenCore Disk: {self.constants.booted_oc_disk}

{self.language_handler.get_translation("Hardware_Information")}:
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
