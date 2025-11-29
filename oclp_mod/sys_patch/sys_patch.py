"""
sys_patch.py: Framework for mounting and patching macOS root volume
"""

"""
System based off of Apple's Kernel Debug Kit (KDK)
- https://developer.apple.com/download/all/

The system relies on mounting the APFS volume as a live read/write volume
We perform our required edits, then create a new snapshot for the system boot

The manual process is as follows:
 1. Find the Root Volume
    'diskutil info / | grep "Device Node:"'
 2. Convert Snapshot Device Node to Root Volume Device Node
    /dev/disk3s1s1 -> /dev/disk3s1 (strip last 's1')
 3. Mount the APFS volume as a read/write volume
    'sudo mount -o nobrowse -t apfs  /dev/disk5s5 /System/Volumes/Update/mnt1'
 4. Perform edits to the system (ie. create new KernelCollection)
    'sudo kmutil install --volume-root /System/Volumes/Update/mnt1/ --update-all'
 5. Create a new snapshot for the system boot
    'sudo bless --folder /System/Volumes/Update/mnt1/System/Library/CoreServices --bootefi --create-snapshot'

Additionally Apple's APFS snapshot system supports system rollbacks:
  'sudo bless --mount /System/Volumes/Update/mnt1 --bootefi --last-sealed-snapshot'
Note: root volume rollbacks are unstable in Big Sur due to quickly discarding the original snapshot
- Generally within 2~ boots, the original snapshot is discarded
- Monterey always preserves the original snapshot allowing for reliable rollbacks

Alternative to mounting via 'mount', Apple's update system uses 'mount_apfs' directly
  '/sbin/mount_apfs -R /dev/disk5s5 /System/Volumes/Update/mnt1'

With macOS Ventura, you will also need to install the KDK onto root if you plan to use kmutil
This is because Apple removed on-disk binaries (ref: https://github.com/laobamac/oclp-mod/issues/998)
  'sudo ditto /Library/Developer/KDKs/<KDK Version>/System /System/Volumes/Update/mnt1/System'
"""

import logging
import plistlib
import subprocess
import os

from pathlib   import Path
from functools import cache

from .mount import (
    RootVolumeMount,
    APFSSnapshot
)
from .utilities import (
    install_new_file,
    remove_file,
    PatcherSupportPkgMount,
    KernelDebugKitMerge
)

from .. import constants
from ..datasets.os_data import os_data

from ..volume   import generate_copy_arguments

from ..datasets import (
    os_data
)
from ..support import (
    utilities,
    subprocess_wrapper,
    metallib_handler
)
from .patchsets import (
    HardwarePatchsetDetection,
    HardwarePatchsetSettings,
    PatchType,
    DynamicPatchset
)
from . import (
    sys_patch_helpers,
    kernelcache
)
from .auto_patcher import InstallAutomaticPatchingServices


class PatchSysVolume:
    def __init__(self, model: str, global_constants: constants.Constants, hardware_details: list = None) -> None:
        self.model = model
        self.constants: constants.Constants = global_constants
        self.computer = self.constants.computer
        self.root_supports_snapshot = utilities.check_if_root_is_apfs_snapshot()
        self.constants.root_patcher_succeeded = False # Reset Variable each time we start
        self.constants.needs_to_open_preferences = False
        self.patch_set_dictionary = {}
        self.needs_kmutil_exemptions = False # For '/Library/Extensions' rebuilds
        self.kdk_path = None
        self.metallib_path = None

        # GUI will detect hardware patches before starting PatchSysVolume()
        # However the TUI will not, so allow for data to be passed in manually avoiding multiple calls
        if hardware_details is None:
            hardware_details = HardwarePatchsetDetection(self.constants).device_properties
        self.hardware_details = hardware_details
        self._init_pathing()

        self.skip_root_kmutil_requirement = not self.hardware_details[HardwarePatchsetSettings.KERNEL_DEBUG_KIT_REQUIRED] if self.constants.detected_os >= os_data.os_data.ventura else False
        
        self.requires_kdk_caching      = self.hardware_details[HardwarePatchsetSettings.KERNEL_DEBUG_KIT_REQUIRED] and self.constants.detected_os >= os_data.os_data.ventura
        self.requires_metallib_caching = self.hardware_details[HardwarePatchsetSettings.METALLIB_SUPPORT_PKG_REQUIRED] and self.constants.detected_os >= os_data.os_data.sequoia

        self.mount_obj = RootVolumeMount(self.constants.detected_os)


    def _init_pathing(self) -> None:
        """
        Initializes the pathing for root volume patching
        """
        self.mount_location_data = ""
        if self.root_supports_snapshot is True:
            self.mount_location = "/System/Volumes/Update/mnt1"
        else:
            self.mount_location = ""

        self.mount_extensions = f"{self.mount_location}/System/Library/Extensions"
        self.mount_application_support = f"{self.mount_location_data}/Library/Application Support"


    def _mount_root_vol(self) -> bool:
        """
        Mount root volume
        """
        if self.mount_obj.mount():
            return True

        return False

    def _unmount_root_vol(self) -> None:
        """
        Unmount root volume
        """
        logging.info("- 卸载根卷")
        self.mount_obj.unmount(ignore_errors=True)


    def _run_sanity_checks(self) -> bool:
        """
        Run sanity check before continuing patching
        """
        logging.info("- 在继续打补丁之前运行完整性检查")

        mounted_system_version = Path(self.mount_location) / "System/Library/CoreServices/SystemVersion.plist"

        if not mounted_system_version.exists():
            logging.error("- 在已挂载的根卷上未找到 SystemVersion.plist")
            return False

        try:
            mounted_data = plistlib.load(open(mounted_system_version, "rb"))
            if mounted_data["ProductBuildVersion"] != self.constants.detected_os_build:
                logging.error(
                    f"- SystemVersion.plist 构建版本不匹配：发现 {mounted_data['ProductVersion']} ({mounted_data['ProductBuildVersion']}), 预期 {self.constants.detected_os_version} ({self.constants.detected_os_build})"
                    )
                logging.error("您的机器上正在进行更新，打补丁无法继续，直到取消或完成更新")
                return False
        except:
            logging.error("- 解析 SystemVersion.plist 失败")
            return False

        return True


    def _merge_kdk_with_root(self, save_hid_cs: bool = False) -> None:
        """
        Merge Kernel Debug Kit (KDK) with the root volume
        If no KDK is present, will call kdk_handler to download and install it

        Parameters:
            save_hid_cs (bool): If True, will save the HID CS file before merging KDK
                                Required for USB 1.1 downgrades on Ventura and newer
        """
        self.kdk_path = KernelDebugKitMerge(
            self.constants,
            self.mount_location,
            self.skip_root_kmutil_requirement
        ).merge(save_hid_cs)


    def _unpatch_root_vol(self):
        """
        Reverts APFS snapshot and cleans up any changes made to the root and data volume
        """

        if APFSSnapshot(self.constants.detected_os, self.mount_location).revert_snapshot() is False:
            return

        self._clean_skylight_plugins()
        self._delete_nonmetal_enforcement()

        kernelcache.KernelCacheSupport(
            mount_location_data=self.mount_location_data,
            detected_os=self.constants.detected_os,
            skip_root_kmutil_requirement=self.skip_root_kmutil_requirement
        ).clean_auxiliary_kc()

        self.constants.root_patcher_succeeded = True

        if (self.constants.detected_os >= os_data.os_data.tahoe):
            if os.path.exists("/Library/Preferences/FeatureFlags/Domain/"):
                logging.info("- 重置为新版聚焦")
                subprocess_wrapper.run_as_root_and_verify(["/usr/bin/defaults", "write", "/Library/Preferences/FeatureFlags/Domain/SpotlightUI.plist", "SpotlightPlus", "-dict", "Enabled", "-bool", "true"])

        logging.info("- 卸载补丁完成")
        logging.info("\n请重启系统使补丁生效")


    def _rebuild_root_volume(self) -> bool:
        """
        Rebuilds the Root Volume:
        - Rebuilds the Kernel Collection
        - Updates the Preboot Kernel Cache
        - Rebuilds the dyld Shared Cache
        - Creates a new APFS Snapshot

        Returns:
            bool: True if successful, False if not
        """
        if self._rebuild_kernel_cache() is False:
            return False

        self._update_preboot_kernel_cache()
        self._rebuild_dyld_shared_cache()

        if self._create_new_apfs_snapshot() is False:
            return False

        self._unmount_root_vol()

        logging.info("- 补丁完成")
        logging.info("\n请重启系统使补丁生效")

        if self.needs_kmutil_exemptions is True:
            logging.info("注意：Apple 将要求您打开“系统偏好设置”->“安全性”，以允许加载新的内核扩展")

        self.constants.root_patcher_succeeded = True

        return True


    def _rebuild_kernel_cache(self) -> bool:
        """
        Rebuilds the Kernel Cache
        """

        result =  kernelcache.RebuildKernelCache(
            os_version=self.constants.detected_os,
            mount_location=self.mount_location,
            auxiliary_cache=self.needs_kmutil_exemptions,
            auxiliary_cache_only=self.skip_root_kmutil_requirement
        ).rebuild()

        if result is False:
            return False

        if self.skip_root_kmutil_requirement is False:
            sys_patch_helpers.SysPatchHelpers(self.constants).install_rsr_repair_binary()

        return True


    def _create_new_apfs_snapshot(self) -> bool:
        """
        Creates a new APFS snapshot of the root volume

        Returns:
            bool: True if snapshot was created, False if not
        """
        return APFSSnapshot(self.constants.detected_os, self.mount_location).create_snapshot()


    def _rebuild_dyld_shared_cache(self) -> None:
        """
        Rebuild the dyld shared cache
        Only required on Mojave and older
        """

        if self.constants.detected_os > os_data.os_data.catalina:
            return
        logging.info("- 重建 dyld 共享缓存")
        subprocess_wrapper.run_as_root_and_verify(["/usr/bin/update_dyld_shared_cache", "-root", f"{self.mount_location}/"])


    def _update_preboot_kernel_cache(self) -> None:
        """
        Update the preboot kernel cache
        Only required on Catalina
        """

        if self.constants.detected_os == os_data.os_data.catalina:
            logging.info("- 重建预启动内核缓存")
            subprocess_wrapper.run_as_root_and_verify(["/usr/sbin/kcditto"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


    def _clean_skylight_plugins(self) -> None:
        """
        Clean non-Metal's SkylightPlugins folder
        """

        if (Path(self.mount_application_support) / Path("SkyLightPlugins/")).exists():
            logging.info("- 找到 SkylightPlugins 文件夹，正在删除旧插件")
            subprocess_wrapper.run_as_root_and_verify(["/bin/rm", "-Rf", f"{self.mount_application_support}/SkyLightPlugins"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            subprocess_wrapper.run_as_root_and_verify(["/bin/mkdir", f"{self.mount_application_support}/SkyLightPlugins"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        else:
            logging.info("- 创建 SkylightPlugins 文件夹")
            subprocess_wrapper.run_as_root_and_verify(["/bin/mkdir", "-p", f"{self.mount_application_support}/SkyLightPlugins/"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


    def _delete_nonmetal_enforcement(self) -> None:
        """
        Remove defaults related to forced OpenGL rendering
        Primarily for development purposes
        """

        for arg in ["useMetal", "useIOP"]:
            result = subprocess.run(["/usr/bin/defaults", "read", "/Library/Preferences/com.apple.CoreDisplay", arg], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout.decode("utf-8").strip()
            if result in ["0", "false", "1", "true"]:
                logging.info(f"- 删除非 Metal 强制渲染首选项: {arg}")
                subprocess_wrapper.run_as_root(["/usr/bin/defaults", "delete", "/Library/Preferences/com.apple.CoreDisplay", arg])


    def _write_patchset(self, patchset: dict) -> None:
        """
        Write patchset information to Root Volume

        Parameters:
            patchset (dict): Patchset information (generated by HardwarePatchsetDetection)
        """

        destination_path = f"{self.mount_location}/System/Library/CoreServices"
        file_name = "oclp-mod.plist"
        destination_path_file = f"{destination_path}/{file_name}"
        if sys_patch_helpers.SysPatchHelpers(self.constants).generate_patchset_plist(patchset, file_name, self.kdk_path, self.metallib_path):
            logging.info("- 将补丁集信息写入根卷")
            if Path(destination_path_file).exists():
                subprocess_wrapper.run_as_root_and_verify(["/bin/rm", destination_path_file], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            subprocess_wrapper.run_as_root_and_verify(generate_copy_arguments(f"{self.constants.payload_path}/{file_name}", destination_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        if self.constants.detected_os >= os_data.os_data.tahoe and os.path.exists(destination_path_file):
            with open(destination_path_file, 'r', encoding='utf-8') as f:
                if '旧版启动台' in f.read():
                    if not os.path.exists("/Library/Preferences/FeatureFlags/Domain/"):
                        logging.info("- 创建 FeatureFlags 目录")
                        subprocess_wrapper.run_as_root(["/bin/mkdir", "-p", "/Library/Preferences/FeatureFlags/Domain"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    logging.info("- 启用旧版启动台")
                    subprocess_wrapper.run_as_root_and_verify(["/usr/bin/defaults", "write", "/Library/Preferences/FeatureFlags/Domain/SpotlightUI.plist", "SpotlightPlus", "-dict", "Enabled", "-bool", "false"])


    def _patch_root_vol(self):
        """
        Patch root volume
        """

        logging.info(f"- 为 {self.model} 运行补丁")
        if self.patch_set_dictionary != {}:
            self._execute_patchset(self.patch_set_dictionary)
        else:
            self._execute_patchset(HardwarePatchsetDetection(self.constants).patches)

        if self.constants.wxpython_variant is True and self.constants.detected_os >= os_data.os_data.big_sur:
            needs_daemon = False
            if self.requires_kdk_caching is True or self.requires_metallib_caching is True:
                needs_daemon = True
            InstallAutomaticPatchingServices(self.constants).install_auto_patcher_launch_agent(kdk_caching_needed=needs_daemon)

        self._rebuild_root_volume()


    def _execute_patchset(self, required_patches: dict):
        """
        Executes provided patchset

        Parameters:
            required_patches (dict): Patchset to execute (generated by HardwarePatchsetDetection)
        """

        kc_support_obj = kernelcache.KernelCacheSupport(
            mount_location_data=self.mount_location_data,
            detected_os=self.constants.detected_os,
            skip_root_kmutil_requirement=self.skip_root_kmutil_requirement
        )

        source_files_path = str(self.constants.payload_local_binaries_root_path)
        required_patches = self._preflight_checks(required_patches, source_files_path)
        for patch in required_patches:
            logging.info("- 安装补丁集: " + patch)
            for method_remove in [PatchType.REMOVE_SYSTEM_VOLUME, PatchType.REMOVE_DATA_VOLUME]:
                if method_remove in required_patches[patch]:
                    for remove_patch_directory in required_patches[patch][method_remove]:
                        logging.info("- 删除文件路径: " + remove_patch_directory)
                        for remove_patch_file in required_patches[patch][method_remove][remove_patch_directory]:
                            if method_remove == PatchType.REMOVE_SYSTEM_VOLUME:
                                destination_folder_path = str(self.mount_location) + remove_patch_directory
                            else:
                                destination_folder_path = str(self.mount_location_data) + remove_patch_directory
                            remove_file(destination_folder_path, remove_patch_file)


            for method_install in [PatchType.OVERWRITE_SYSTEM_VOLUME, PatchType.OVERWRITE_DATA_VOLUME, PatchType.MERGE_SYSTEM_VOLUME, PatchType.MERGE_DATA_VOLUME]:
                if method_install not in required_patches[patch]:
                    continue

                for install_patch_directory in list(required_patches[patch][method_install]):
                    logging.info(f"- 处理安装路径: {install_patch_directory}")
                    for install_file in list(required_patches[patch][method_install][install_patch_directory]):
                        source_folder_path = required_patches[patch][method_install][install_patch_directory][install_file] + install_patch_directory
                        # 检查是否从根目录源
                        if not required_patches[patch][method_install][install_patch_directory][install_file].startswith("/"):
                            source_folder_path = source_files_path + "/" + source_folder_path

                        if method_install in [PatchType.OVERWRITE_SYSTEM_VOLUME, PatchType.MERGE_SYSTEM_VOLUME]:
                            destination_folder_path = str(self.mount_location) + install_patch_directory
                        else:
                            if install_patch_directory == "/Library/Extensions":
                                self.needs_kmutil_exemptions = True
                                if kc_support_obj.check_kexts_needs_authentication(install_file) is True:
                                    self.constants.needs_to_open_preferences = True

                            destination_folder_path = str(self.mount_location_data) + install_patch_directory

                        updated_destination_folder_path = kc_support_obj.add_auxkc_support(install_file, source_folder_path, install_patch_directory, destination_folder_path)
                        if updated_destination_folder_path != destination_folder_path:
                            if kc_support_obj.check_kexts_needs_authentication(install_file) is True:
                                self.constants.needs_to_open_preferences = True

                        if destination_folder_path != updated_destination_folder_path:
                            # 更新 required_patches 以反映新的目标文件夹路径
                            if updated_destination_folder_path not in required_patches[patch][method_install]:
                                required_patches[patch][method_install].update({updated_destination_folder_path: {}})
                            required_patches[patch][method_install][updated_destination_folder_path].update({install_file: required_patches[patch][method_install][install_patch_directory][install_file]})
                            required_patches[patch][method_install][install_patch_directory].pop(install_file)

                            destination_folder_path = updated_destination_folder_path

                        install_new_file(source_folder_path, destination_folder_path, install_file, method_install)

            if PatchType.EXECUTE in required_patches[patch]:
                for process in required_patches[patch][PatchType.EXECUTE]:
                    # 有些进程需要 sudo，然而我们不能直接在某些场景中调用 sudo
                    # 相反，如果字符串的布尔值为 True，则调用提升权限函数
                    if required_patches[patch][PatchType.EXECUTE][process] is True:
                        logging.info(f"- 以 root 运行进程:\n{process}")
                        subprocess_wrapper.run_as_root_and_verify(process.split(" "), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    else:
                        logging.info(f"- 运行进程:\n{process}")
                        subprocess_wrapper.run_and_verify(process, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

        if any(x in required_patches for x in ["AMD Legacy GCN", "AMD Legacy Polaris", "AMD Legacy Vega"]):
            sys_patch_helpers.SysPatchHelpers(self.constants).disable_window_server_caching()
        if "Metal 3802 Common Extended" in required_patches:
            sys_patch_helpers.SysPatchHelpers(self.constants).patch_gpu_compiler_libraries(mount_point=self.mount_location)

        self._write_patchset(required_patches)


    def _resolve_metallib_support_pkg(self) -> str:
        """
        Resolves MetalLibSupportPkg
        """
        metallib_obj = metallib_handler.MetalLibraryObject(self.constants, self.constants.detected_os_build, self.constants.detected_os_version)
        if metallib_obj.success is False:
            logging.error(f"无法找到 MetalLibSupportPkg: {metallib_obj.error_msg}")
            raise Exception(f"无法找到 MetalLibSupportPkg: {metallib_obj.error_msg}")

        metallib_download_obj = metallib_obj.retrieve_download()
        if not metallib_download_obj:
            # 已经下载，返回路径
            logging.info(f"使用 MetalLibSupportPkg: {metallib_obj.metallib_installed_path}")
            self.metallib_path = metallib_obj.metallib_installed_path
            return str(metallib_obj.metallib_installed_path)

        metallib_download_obj.download(spawn_thread=False)
        if metallib_download_obj.download_complete is False:
            error_msg = metallib_download_obj.error_msg
            logging.error(f"无法下载 MetalLibSupportPkg: {error_msg}")
            raise Exception(f"无法下载 MetalLibSupportPkg: {error_msg}")

        if metallib_obj.install_metallib() is False:
            logging.error("无法安装 MetalLibSupportPkg")
            raise Exception("无法安装 MetalLibSupportPkg")

        # 安装后，检查是否存在
        return self._resolve_metallib_support_pkg()


    @cache
    def _resolve_dynamic_patchset(self, variant: DynamicPatchset) -> str:
        """
        Resolves dynamic patchset to a path
        """
        if variant == DynamicPatchset.MetallibSupportPkg:
            return self._resolve_metallib_support_pkg()

        raise Exception(f"未知动态补丁集: {variant}")


    def _preflight_checks(self, required_patches: dict, source_files_path: Path) -> dict:
        """
        Runs preflight checks before patching

        Parameters:
            required_patches (dict): Patchset dictionary (from HardwarePatchsetDetection)
            source_files_path (Path): Path to the source files (PatcherSupportPkg)

        Returns:
            dict: Updated patchset dictionary
        """

        logging.info("- 在打补丁前运行预检")

        for patch in required_patches:
            # 检查所有文件是否存在
            for method_type in [PatchType.OVERWRITE_SYSTEM_VOLUME, PatchType.OVERWRITE_DATA_VOLUME, PatchType.MERGE_SYSTEM_VOLUME, PatchType.MERGE_DATA_VOLUME]:
                if method_type not in required_patches[patch]:
                    continue
                for install_patch_directory in required_patches[patch][method_type]:
                    for install_file in required_patches[patch][method_type][install_patch_directory]:
                        try:
                            if required_patches[patch][method_type][install_patch_directory][install_file] in DynamicPatchset:
                                required_patches[patch][method_type][install_patch_directory][install_file] = self._resolve_dynamic_patchset(required_patches[patch][method_type][install_patch_directory][install_file])
                        except TypeError:
                            pass

                        source_file = required_patches[patch][method_type][install_patch_directory][install_file] + install_patch_directory + "/" + install_file

                        # 检查是否从根目录源
                        if not required_patches[patch][method_type][install_patch_directory][install_file].startswith("/"):
                            source_file = source_files_path + "/" + source_file
                        if not Path(source_file).exists():
                            raise Exception(f"无法找到 {source_file}")

        # 确保没有使用旧的 Skylight 插件
        self._clean_skylight_plugins()

        # 确保没有非 Metal 强制渲染首选项
        self._delete_nonmetal_enforcement()

        # 确保清理不在补丁集中的旧 kexts 在 /L*/E*
        kernelcache.KernelCacheSupport(
            mount_location_data=self.mount_location_data,
            detected_os=self.constants.detected_os,
            skip_root_kmutil_requirement=self.skip_root_kmutil_requirement
        ).clean_auxiliary_kc()

        # 确保 SNB kexts 与主机兼容
        if "Intel Sandy Bridge" in required_patches:
            sys_patch_helpers.SysPatchHelpers(self.constants).snb_board_id_patch(source_files_path)

        # 确保 KDK 正确安装
        self._merge_kdk_with_root(save_hid_cs=True if "Legacy USB 1.1" in required_patches else False)

        logging.info("- 完成预检，开始打补丁")

        return required_patches


    # Entry Function
    def start_patch(self):
        """
        Entry function for the patching process
        """

        logging.info("- 开始打补丁过程")
        logging.info(f"- 确定适用于 Darwin {self.constants.detected_os} 的所需补丁集")
        patchset_obj = HardwarePatchsetDetection(self.constants)
        self.patch_set_dictionary = patchset_obj.patches

        if self.patch_set_dictionary == {}:
            logging.info("- 您的机器不需要任何根卷补丁！")
            return

        logging.info("- 验证根补丁是否可用...")
        if patchset_obj.can_patch is False:
            logging.error("- Cannot continue with patching!!!")
            patchset_obj.detailed_errors()
            return

        logging.info("- 可以进行补丁！")
        if PatcherSupportPkgMount(self.constants).mount() is False:
            logging.error("- 依赖丢失，无法继续")
            return

        if self._mount_root_vol() is False:
            logging.error("- 未能挂载根目录，无法继续")
            return

        if self._run_sanity_checks() is False:
            self._unmount_root_vol()
            logging.error("- 完整性检查失败，无法继续修补!!")
            logging.error("- 请确保您没有任何待处理的更新")
            return

        self._patch_root_vol()


    def start_unpatch(self) -> None:
        """
        Entry function for unpatching the root volume
        """

        logging.info("- 开始卸载进程")
        patchset_obj = HardwarePatchsetDetection(self.constants)
        if patchset_obj.can_unpatch is False:
            logging.error("- 未能卸载补丁")
            patchset_obj.detailed_errors()
            return

        if self._mount_root_vol() is False:
            logging.error("- 无法挂载根目录，无法继续")
            return

        self._unpatch_root_vol()
