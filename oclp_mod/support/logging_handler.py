"""
logging_handler.py: 初始化程序的日志框架
"""

import os
import sys
import pprint
import logging
import threading
import traceback
import subprocess
import applescript

from pathlib import Path
from datetime import datetime

from .. import constants

from . import (
    analytics_handler,
    global_settings
)


class InitializeLoggingSupport:
    """
    初始化程序的日志框架

    主要职责：
    - 确定日志文件的存储位置
    - 如果日志文件接近最大文件大小，则清理日志文件
    - 初始化日志框架配置
    - 实现自定义回溯处理器
    - 实现文件写入错误处理

    使用方法：
    >>> from resources.logging_handler import InitializeLoggingSupport
    >>> InitializeLoggingSupport()

    开发者注意：
    - 在调用'_attempt_initialize_logging_configuration()'之后才可调用日志记录

    """

    def __init__(self, global_constants: constants.Constants) -> None:
        self.constants: constants.Constants = global_constants

        log_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")

        self.log_filename: str  = f"OCLP-Mod_{self.constants.patcher_version}_{log_time}.log"
        self.log_filepath: Path = None

        self.original_excepthook:        sys       = sys.excepthook
        self.original_thread_excepthook: threading = threading.excepthook

        self.max_file_size:     int = 1024 * 1024               # 1 MB
        self.file_size_redline: int = 1024 * 1024 - 1024 * 100  # 900 KB, 当达到此值时开始清理日志文件

        self._initialize_logging_path()
        self._attempt_initialize_logging_configuration()
        self._start_logging()
        self._implement_custom_traceback_handler()
        self._clean_prior_version_logs()


    def _initialize_logging_path(self) -> None:
        """
        初始化日志框架存储路径
        """

        base_path = Path("~/Library/Logs").expanduser()
        if not base_path.exists() or str(base_path).startswith("/var/root/"):
            # 可能处于安装环境，存储在 /Users/Shared
            base_path = Path("/Users/Shared")
        else:
            # 如果 laobamac 文件夹不存在则创建
            base_path = base_path / "laobamac"
            if not base_path.exists():
                try:
                    base_path.mkdir()
                except Exception as e:
                    print(f"创建 laobamac 文件夹失败: {e}")
                    base_path = Path("/Users/Shared")

        self.log_filepath = Path(f"{base_path}/{self.log_filename}").expanduser()
        self.constants.log_filepath = self.log_filepath

    def _clean_prior_version_logs(self) -> None:
        """
        清理旧版本 Patcher 的日志

        保留最新的 10 个日志
        """

        paths = [
            self.log_filepath.parent,        # ~/Library/Logs/laobamac
            self.log_filepath.parent.parent, # ~/Library/Logs (旧位置)
        ]

        logs = []

        for path in paths:
            for file in path.glob("OCLP-Mod*"):
                if not file.is_file():
                    continue

                if not file.name.endswith(".log"):
                    continue

                if file.name == self.log_filename:
                    continue

                logs.append(file)

        logs.sort(key=lambda x: x.stat().st_mtime, reverse=True)

        for log in logs[9:]:
            try:
                log.unlink()
            except Exception as e:
                logging.error(f"删除日志文件失败: {e}")


    def _initialize_logging_configuration(self, log_to_file: bool = True) -> None:
        """
        初始化日志框架配置

        StreamHandler 的格式用于模仿 print() 的默认行为
        而 FileHandler 的格式用于更详细的日志记录

        参数：
            log_to_file (bool): 是否将日志记录到文件

        """

        logging.basicConfig(
            level=logging.NOTSET,
            format="[%(asctime)s] [%(filename)-32s] [%(lineno)-4d]: %(message)s",
            handlers=[
                logging.StreamHandler(stream = sys.stdout),
                logging.FileHandler(self.log_filepath) if log_to_file is True else logging.NullHandler()
            ],
        )
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().handlers[0].setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger().handlers[1].maxBytes = self.max_file_size


    def _attempt_initialize_logging_configuration(self) -> None:
        """
        尝试初始化日志框架配置

        如果我们无法初始化日志框架，我们将禁用文件日志记录
        """

        try:
            self._initialize_logging_configuration()
        except Exception as e:
            print(f"初始化日志框架失败: {e}")
            print("重试不记录文件日志...")
            self._initialize_logging_configuration(log_to_file=False)


    def _start_logging(self):
        """
        开始日志记录，作为日志中的易于识别的起点
        """

        str_msg = f"# OCLP-Mod ({self.constants.patcher_version}) #"
        str_len = len(str_msg)

        logging.info('#' * str_len)
        logging.info(str_msg)
        logging.info('#' * str_len)

        logging.info("日志文件设置:")
        logging.info(f"  {self.log_filepath}")
        # 显示相对路径以避免泄露用户名
        try:
            path = self.log_filepath.relative_to(Path.home())
            logging.info(f"~/{path}")
        except ValueError:
            logging.info(self.log_filepath)


    def _implement_custom_traceback_handler(self) -> None:
        """
        将回溯重定向到日志模块
        """

        def custom_excepthook(type, value, tb) -> None:
            """
            将主线程中的回溯重定向到日志模块
            """
            logging.error("主线程中未捕获的异常", exc_info=(type, value, tb))
            self._display_debug_properties()

            if "wx/" in "".join(traceback.format_exception(type, value, tb)):
                # 可能是 GUI 错误，不显示错误对话框
                return

            if self.constants.cli_mode is True:
                threading.Thread(target=analytics_handler.Analytics(self.constants).send_crash_report, args=(self.log_filepath,)).start()
                return

            error_msg = f"OCLP-Mod 遇到了以下内部错误:\n\n"
            error_msg += f"{type.__name__}: {value}"
            if tb:
                error_msg += f"\n\n{traceback.extract_tb(tb)[-1]}"

            cant_log: bool = global_settings.GlobalEnviromentSettings().read_property("DisableCrashAndAnalyticsReporting")
            if not isinstance(cant_log, bool):
                cant_log = False

            if self.constants.commit_info[0].startswith("refs/tags"):
                cant_log = True

            if cant_log is True:
                error_msg += "\n\n显示日志文件？"
            else:
                error_msg += "\n\n向 laobamac 发送崩溃报告？"

            # 询问用户是否要发送崩溃报告
            try:
                result = applescript.AppleScript(f'display dialog "{error_msg}" with title "OCLP-Mod ({self.constants.patcher_version})" buttons {{"Yes", "No"}} default button "Yes" with icon caution').run()
            except Exception as e:
                logging.error(f"显示崩溃报告对话框失败: {e}")
                return

            if result[applescript.AEType(b'bhit')] != "Yes":
                return

            if cant_log is True:
                subprocess.run(["/usr/bin/open", "--reveal", self.log_filepath])
                return

            threading.Thread(target=analytics_handler.Analytics(self.constants).send_crash_report, args=(self.log_filepath,)).start()


        def custom_thread_excepthook(args) -> None:
            """
            将生成的线程中的回溯重定向到日志模块
            """
            logging.error("生成的线程中未捕获的异常", exc_info=(args))

        sys.excepthook = custom_excepthook
        threading.excepthook = custom_thread_excepthook


    def _restore_original_excepthook(self) -> None:
        """
        恢复原始的回溯处理器
        """

        sys.excepthook = self.original_excepthook
        threading.excepthook = self.original_thread_excepthook


    def _display_debug_properties(self) -> None:
        """
        显示调试属性，主要用于主线程崩溃后
        """
        logging.info("主机属性:")
        logging.info(f"  XNU 版本: {self.constants.detected_os}.{self.constants.detected_os_minor}")
        logging.info(f"  XNU 构建: {self.constants.detected_os_build}")
        logging.info(f"  macOS 版本: {self.constants.detected_os_version}")
        logging.info("调试属性:")
        logging.info(f"  有效用户 ID: {os.geteuid()}")
        logging.info(f"  有效组 ID: {os.getegid()}")
        logging.info(f"  真实用户 ID: {os.getuid()}")
        logging.info(f"  真实组 ID: {os.getgid()}")
        logging.info("  传递给 Patcher 的参数:")
        for arg in sys.argv:
            logging.info(f"    {arg}")

        logging.info(f"主机属性:\n{pprint.pformat(self.constants.computer.__dict__, indent=4)}")
