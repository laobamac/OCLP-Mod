"""
install.py: 安装OpenCore文件到ESP
"""

import logging
import plistlib
import subprocess
import re

from pathlib import Path

from . import utilities, subprocess_wrapper

from .. import constants


class tui_disk_installation:
    def __init__(self, versions):
        self.constants: constants.Constants = versions

    def list_disks(self):
        all_disks = {}
        # TODO: AllDisksAndPartitions 在Snow Leopard及更早版本中不受支持
        try:
            # High Sierra及更新版本
            disks = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "list", "-plist", "physical"], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        except ValueError:
            # Sierra及更早版本
            disks = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "list", "-plist"], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        for disk in disks["AllDisksAndPartitions"]:
            try:
                disk_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", disk["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip().encode())
            except:
                # Chinesium USB可能在MediaName中有垃圾数据
                diskutil_output = subprocess.run(["/usr/sbin/diskutil", "info", "-plist", disk["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip()
                ungarbafied_output = re.sub(r'(<key>MediaName</key>\s*<string>).*?(</string>)', r'\1\2', diskutil_output).encode()
                disk_info = plistlib.loads(ungarbafied_output)
            try:
                all_disks[disk["DeviceIdentifier"]] = {"identifier": disk_info["DeviceNode"], "name": disk_info.get("MediaName", "Disk"), "size": disk_info["TotalSize"], "partitions": {}}
                for partition in disk["Partitions"]:
                    partition_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", partition["DeviceIdentifier"]], stdout=subprocess.PIPE).stdout.decode().strip().encode())
                    all_disks[disk["DeviceIdentifier"]]["partitions"][partition["DeviceIdentifier"]] = {
                        "fs": partition_info.get("FilesystemType", partition_info["Content"]),
                        "type": partition_info["Content"],
                        "name": partition_info.get("VolumeName", ""),
                        "size": partition_info["TotalSize"],
                    }
            except KeyError:
                # 避免安装CD时崩溃
                continue

        supported_disks = {}
        for disk in all_disks:
            if not any(all_disks[disk]["partitions"][partition]["fs"] in ("msdos", "EFI") for partition in all_disks[disk]["partitions"]):
                continue
            supported_disks.update({
                disk: {
                    "disk": disk,
                    "name": all_disks[disk]["name"],
                    "size": utilities.human_fmt(all_disks[disk]['size']),
                    "partitions": all_disks[disk]["partitions"]
                }
            })
        return supported_disks

    def list_partitions(self, disk_response, supported_disks):
        # 接受磁盘UUID以及由list_disks生成的diskutil数据集
        # 返回FAT32分区列表
        disk_identifier = disk_response
        selected_disk = supported_disks[disk_identifier]

        supported_partitions = {}

        for partition in selected_disk["partitions"]:
            if selected_disk["partitions"][partition]["fs"] not in ("msdos", "EFI"):
                continue
            supported_partitions.update({
                partition: {
                    "partition": partition,
                    "name": selected_disk["partitions"][partition]["name"],
                    "size": utilities.human_fmt(selected_disk["partitions"][partition]["size"])
                }
            })
        return supported_partitions


    def _determine_sd_card(self, media_name: str):
        # 包含常见SD卡名称的数组
        # 注意大多数基于USB的SD卡读卡器通常报告为"Storage Device"
        # 因此没有可靠的方法进一步解析IOService输出(kUSBProductString)
        if any(x in media_name for x in ("SD Card", "SD/MMC", "SDXC Reader", "SD Reader", "Card Reader")):
            return True
        return False


    def install_opencore(self, full_disk_identifier: str):
        # TODO: Apple Script在Yosemite(?)及更早版本中失败
        logging.info(f"正在挂载分区: {full_disk_identifier}")
        result = subprocess_wrapper.run_as_root(["/usr/sbin/diskutil", "mount", full_disk_identifier], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode != 0:
            logging.info("挂载失败")
            subprocess_wrapper.log(result)
            return

        partition_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", full_disk_identifier], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        parent_disk = partition_info["ParentWholeDisk"]
        drive_host_info = plistlib.loads(subprocess.run(["/usr/sbin/diskutil", "info", "-plist", parent_disk], stdout=subprocess.PIPE).stdout.decode().strip().encode())
        sd_type = drive_host_info.get("MediaName", "Disk")
        try:
            ssd_type = drive_host_info["SolidState"]
        except KeyError:
            ssd_type = False
        mount_path = Path(partition_info["MountPoint"])
        disk_type = partition_info["BusProtocol"]

        if not mount_path.exists():
            logging.info("EFI挂载失败！")
            return False

        if (mount_path / Path("EFI/OC")).exists():
            logging.info("正在删除已存在的EFI/OC文件夹")
            subprocess.run(["/bin/rm", "-rf", mount_path / Path("EFI/OC")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if (mount_path / Path("System")).exists():
            logging.info("正在删除已存在的System文件夹")
            subprocess.run(["/bin/rm", "-rf", mount_path / Path("System")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if (mount_path / Path("boot.efi")).exists():
            logging.info("正在删除已存在的boot.efi")
            subprocess.run(["/bin/rm", "-rf", mount_path / Path("boot.efi")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        logging.info("正在将OpenCore复制到EFI分区")
        subprocess.run(["/bin/mkdir", "-p", mount_path / Path("EFI")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["/bin/cp", "-r", self.constants.opencore_release_folder / Path("EFI/OC"), mount_path / Path("EFI/OC")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(["/bin/cp", "-r", self.constants.opencore_release_folder / Path("System"), mount_path / Path("System")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if Path(self.constants.opencore_release_folder / Path("boot.efi")).exists():
            subprocess.run(["/bin/cp", self.constants.opencore_release_folder / Path("boot.efi"), mount_path / Path("boot.efi")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if self.constants.boot_efi is True:
            logging.info("正在将Bootstrap转换为BOOTx64.efi")
            if (mount_path / Path("EFI/BOOT")).exists():
                subprocess.run(["/bin/rm", "-rf", mount_path / Path("EFI/BOOT")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            Path(mount_path / Path("EFI/BOOT")).mkdir()
            subprocess.run(["/bin/mv", mount_path / Path("System/Library/CoreServices/boot.efi"), mount_path / Path("EFI/BOOT/BOOTx64.efi")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(["/bin/rm", "-rf", mount_path / Path("System")], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        if self._determine_sd_card(sd_type) is True:
            logging.info("正在添加SD卡图标")
            subprocess.run(["/bin/cp", self.constants.icon_path_sd, mount_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        elif ssd_type is True:
            logging.info("正在添加SSD图标")
            subprocess.run(["/bin/cp", self.constants.icon_path_ssd, mount_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        elif disk_type == "USB":
            logging.info("正在添加外部USB驱动器图标")
            subprocess.run(["/bin/cp", self.constants.icon_path_external, mount_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        else:
            logging.info("正在添加内部驱动器图标")
            subprocess.run(["/bin/cp", self.constants.icon_path_internal, mount_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        logging.info("正在清理安装位置")
        if not self.constants.recovery_status:
            logging.info("正在卸载EFI分区")
            subprocess.run(["/usr/sbin/diskutil", "umount", mount_path], stdout=subprocess.PIPE).stdout.decode().strip().encode()

        logging.info("OpenCore传输完成")

        return True