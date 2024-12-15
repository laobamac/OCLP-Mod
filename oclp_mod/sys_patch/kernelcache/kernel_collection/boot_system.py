"""
boot_system.py: 启动和系统内核集合管理
"""

import logging
import subprocess

from ..base.cache import BaseKernelCache
from ....support  import subprocess_wrapper
from ....datasets import os_data


class BootSystemKernelCollections(BaseKernelCache):

    def __init__(self, mount_location: str, detected_os: int, auxiliary_kc: bool) -> None:
        self.mount_location = mount_location
        self.detected_os  = detected_os
        self.auxiliary_kc = auxiliary_kc


    def _kmutil_arguments(self) -> list[str]:
        """
        生成用于创建或更新启动、系统和辅助内核集合的kmutil参数
        """

        args = ["/usr/bin/kmutil"]

        if self.detected_os >= os_data.os_data.ventura:
            args.append("create")
            args.append("--allow-missing-kdk")
        else:
            args.append("install")

        args.append("--volume-root")
        args.append(self.mount_location)

        args.append("--update-all")

        args.append("--variant-suffix")
        args.append("release")

        if self.auxiliary_kc is True:
            # 以下参数用于在禁用SIP时创建辅助KC时跳过kext同意提示
            args.append("--no-authentication")
            args.append("--no-authorization")

        return args


    def rebuild(self) -> bool:
        logging.info(f"- 重建 {'启动和系统' if self.auxiliary_kc is False else '启动、系统和辅助'} 内核集合")
        if self.auxiliary_kc is True:
            logging.info("  (您将收到系统偏好设置的提示，暂时忽略)")

        result = subprocess_wrapper.run_as_root(self._kmutil_arguments(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode != 0:
            subprocess_wrapper.log(result)
            return False

        return True