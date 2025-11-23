"""
network_handler.py: Library dedicated to Network Handling tasks including downloading files

Primarily based around the DownloadObject class, which provides a simple
object for libraries to query download progress and status
"""

import time
import requests
import threading
import logging
import enum
import hashlib
import atexit

from typing import Union
from pathlib import Path

from ..constants import Constants

from . import utilities

SESSION = requests.Session()

settings = Constants()

class DownloadStatus(enum.Enum):
    """
    Enum for download status
    """

    INACTIVE:    str = "Inactive"
    DOWNLOADING: str = "Downloading"
    ERROR:       str = "Error"
    COMPLETE:    str = "Complete"


class NetworkUtilities:
    """
    Utilities for network related tasks, primarily used for downloading files
    """

    def __init__(self, url: str = None) -> None:
        self.url: str = url

        if self.url is None:
            if settings.use_github_proxy == True:
                self.url = "https://next.oclpapi.simplehac.cn/"
            else:
                self.url = "https://dortania.github.io/"

        # 配置SESSION，禁用SSL验证
        SESSION.verify = False
        # 忽略不安全的HTTPS请求警告
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


    def verify_network_connection(self) -> bool:
        """
        Verifies that the network is available

        Returns:
            bool: True if network is available, False otherwise
        """

        try:
            # 禁用SSL验证
            response = requests.head(self.url, timeout=5, allow_redirects=True, verify=False)
            if response.status_code == 404:
                return False
            else:
                return True
        except requests.exceptions.SSLError:
            # SSL错误也认为网络可用（因为只是证书问题，不是网络连接问题）
            logging.warning(f"SSL证书验证失败，但网络连接正常: {self.url}")
            return True
        except Exception as e:
            logging.debug(f"网络检测异常: {self.url} -> 错误: {str(e)}")
            return False

    def validate_link(self) -> bool:
        """
        Check for 404 error

        Returns:
            bool: True if link is valid, False otherwise
        """
        try:
            response = SESSION.head(self.url, timeout=5, allow_redirects=True)
            if response.status_code == 404:
                return False
            else:
                return True
        except (
            requests.exceptions.Timeout,
            requests.exceptions.TooManyRedirects,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError
        ):
            return False


    def get(self, url: str, **kwargs) -> requests.Response:
        """
        Wrapper for requests's get method
        Implement additional error handling

        Parameters:
            url (str): URL to get
            **kwargs: Additional parameters for requests.get

        Returns:
            requests.Response: Response object from requests.get
        """

        result: requests.Response = None

        try:
            # 确保禁用SSL验证
            kwargs['verify'] = False
            kwargs['timeout'] = kwargs.get('timeout', 30)
            result = SESSION.get(url, **kwargs)
        except (
            requests.exceptions.Timeout,
            requests.exceptions.TooManyRedirects,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError
        ) as error:
            logging.warn(f"Error calling requests.get: {error}")
            # Return empty response object
            return requests.Response()
        except requests.exceptions.SSLError as ssl_error:
            logging.warn(f"SSL错误，尝试不使用验证: {ssl_error}")
            # 重试一次，不使用SSL验证
            try:
                kwargs['verify'] = False
                result = SESSION.get(url, **kwargs)
            except Exception as retry_error:
                logging.error(f"重试下载失败: {retry_error}")
                return requests.Response()

        return result

    def post(self, url: str, **kwargs) -> requests.Response:
        """
        Wrapper for requests's post method
        Implement additional error handling

        Parameters:
            url (str): URL to post
            **kwargs: Additional parameters for requests.post

        Returns:
            requests.Response: Response object from requests.post
        """

        result: requests.Response = None

        try:
            result = SESSION.post(url, **kwargs)
        except (
            requests.exceptions.Timeout,
            requests.exceptions.TooManyRedirects,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError
        ) as error:
            logging.warn(f"Error calling requests.post: {error}")
            # Return empty response object
            return requests.Response()

        return result


class DownloadObject:
    """
    Object for downloading files from the network

    Usage:
        >>> download_object = DownloadObject(url, path)
        >>> download_object.download(display_progress=True)

        >>> if download_object.is_active():
        >>>     print(download_object.get_percent())

        >>> if not download_object.download_complete:
        >>>     print("Download failed")

        >>> print("Download complete"")

    """

    def __init__(self, url: str, path: str, size: str = None) -> None:
        self.url:       str = url
        self.status:    str = DownloadStatus.INACTIVE
        self.size:      str = size
        self.error_msg: str = ""
        self.filename:  str = self._get_filename()

        self.filepath:  Path = Path(path)

        self.total_file_size:      float = 0.0
        self.downloaded_file_size: float = 0.0
        self.start_time:           float = time.time()

        self.error:             bool = False
        self.should_stop:       bool = False
        self.download_complete: bool = False
        self.has_network:       bool = True  # 假设有网络，实际在下载时验证

        self.active_thread: threading.Thread = None

        self.should_checksum: bool = False

        self.checksum = None
        self._checksum_storage: hash = None

        # 注释掉初始的文件大小获取，在下载时再获取
        # if self.has_network:
        #     self._populate_file_size()


    def __del__(self) -> None:
        self.stop()


    def download(self, display_progress: bool = False, spawn_thread: bool = True, verify_checksum: bool = False) -> None:
        """
        Download the file

        Spawns a thread to download the file, so that the main thread can continue
        Note sleep is disabled while the download is active

        Parameters:
            display_progress (bool): Display progress in console
            spawn_thread (bool): Spawn a thread to download the file, otherwise download in the current thread
            verify_checksum (bool): Calculate checksum of downloaded file if True

        """
        self.status = DownloadStatus.DOWNLOADING
        logging.info(f"开始下载: {self.filename}")
        if spawn_thread:
            if self.active_thread:
                logging.error("下载正在进行中")
                return
            self.should_checksum = verify_checksum
            self.active_thread = threading.Thread(target=self._download, args=(display_progress,))
            self.active_thread.start()
            return

        self.should_checksum = verify_checksum
        self._download(display_progress)


    def download_simple(self, verify_checksum: bool = False) -> Union[str, bool]:
        """
        Alternative to download(), mimics  utilities.py's old download_file() function

        Parameters:
            verify_checksum (bool): Return checksum of downloaded file if True

        Returns:
            If verify_checksum is True, returns the checksum of the downloaded file
            Otherwise, returns True if download was successful, False otherwise
        """

        if verify_checksum:
            self.should_checksum = True
            self.checksum = hashlib.sha256()

        self.download(spawn_thread=False)

        if not self.download_complete:
            return False

        return self.checksum.hexdigest() if self.checksum else True


    def _get_filename(self) -> str:
        """
        Get the filename from the URL

        Returns:
            str: Filename
        """

        return Path(self.url).name


    def convert_size(self, size_str):
        units = {'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
        for unit, factor in units.items():
            if unit in size_str:
               return float(size_str.replace(unit, '')) * factor
        return float(size_str)

    def _populate_file_size(self) -> None:
        """
        Get the file size of the file to be downloaded

        If unable to get file size, set to zero
        """

        try:
            result = SESSION.head(self.url, allow_redirects=True, timeout=5, verify=False)
            if 'Content-Length' in result.headers:
                self.total_file_size = float(result.headers['Content-Length'])
                if self.size != None:
                    self.total_file_size = self.convert_size(self.size)
            else:
                raise Exception("Content-Length 头部缺失")
        except Exception as e:
            logging.error(f"确定文件大小时出错 {self.url}: {str(e)}")
            logging.error("假设文件大小为0")
            self.total_file_size = 0.0


    def _update_checksum(self, chunk: bytes) -> None:
        """
        Update checksum with new chunk

        Parameters:
            chunk (bytes): Chunk to update checksum with
        """
        self._checksum_storage.update(chunk)


    def _prepare_working_directory(self, path: Path) -> bool:
        """
        Validates working enviroment, including free space and removing existing files

        Parameters:
            path (str): Path to the file

        Returns:
            bool: True if successful, False if not
        """

        try:
            if Path(path).exists():
                logging.info(f"删除现有文件: {path}")
                Path(path).unlink()
                return True

            if not Path(path).parent.exists():
                logging.info(f"创建目录: {Path(path).parent}")
                Path(path).parent.mkdir(parents=True, exist_ok=True)

            available_space = utilities.get_free_space(Path(path).parent)
            if self.total_file_size > available_space:
                msg = f"没有足够的可用空间下载 {self.filename}，需要 {utilities.human_fmt(self.total_file_size)}，现有 {utilities.human_fmt(available_space)}"
                logging.error(msg)
                raise Exception(msg)

        except Exception as e:
            self.error = True
            self.error_msg = str(e)
            self.status = DownloadStatus.ERROR
            logging.error(f"准备工作目录时出错 {path}: {self.error_msg}")
            return False

        logging.info(f"- 目录已准备好: {path}")
        return True


    def _download(self, display_progress: bool = False) -> None:
        """
        Download the file

        Libraries should invoke download() instead of this method

        Parameters:
            display_progress (bool): Display progress in console
        """

        utilities.disable_sleep_while_running()

        try:
            # 直接尝试下载，不进行前置网络检测
            logging.info(f"开始下载: {self.url}")
            
            if self._prepare_working_directory(self.filepath) is False:
                raise Exception(self.error_msg)

            # 在下载前获取文件大小
            self._populate_file_size()

            # 使用相同的SESSION确保一致性
            response = SESSION.get(self.url, stream=True, timeout=30, allow_redirects=True)
            
            # 详细记录响应信息
            logging.info(f"下载响应状态码: {response.status_code}")
            if response.history:
                logging.info(f"经历了重定向: {[r.status_code for r in response.history]}")

            # 检查响应状态 - 200表示成功
            if response.status_code != 200:
                raise Exception(f"服务器返回错误状态码: {response.status_code}")

            # 如果_populate_file_size没有获取到大小，尝试从响应头获取
            if self.total_file_size == 0.0 and 'Content-Length' in response.headers:
                content_length = response.headers['Content-Length']
                if content_length and content_length.isdigit():
                    self.total_file_size = float(content_length)
                    logging.info(f"从响应头获取到文件大小: {utilities.human_fmt(self.total_file_size)}")

            with open(self.filepath, 'wb') as file:
                atexit.register(self.stop)
                for i, chunk in enumerate(response.iter_content(1024 * 1024 * 4)):
                    if self.should_stop:
                        raise Exception("下载已停止")
                    if chunk:
                        file.write(chunk)
                        self.downloaded_file_size += len(chunk)
                        if self.should_checksum:
                            self._update_checksum(chunk)
                        if display_progress and i % 100 == 0:
                            # 不要在这里使用日志记录，因为我们会向日志文件中大量写入
                            if self.total_file_size == 0.0:
                                print(f"已下载 {utilities.human_fmt(self.downloaded_file_size)} 的 {self.filename}")
                            else:
                                print(f"已下载 {self.get_percent():.2f}% 的 {self.filename} ({utilities.human_fmt(self.get_speed())}/秒) ({self.get_time_remaining():.2f} 秒剩余)")
                self.download_complete = True
                logging.info(f"下载完成: {self.filename}")
                logging.info("统计信息:")
                logging.info(f"- 已下载大小: {utilities.human_fmt(self.downloaded_file_size)}")
                logging.info(f"- 经过时间: {(time.time() - self.start_time):.2f} 秒")
                logging.info(f"- 速度: {utilities.human_fmt(self.downloaded_file_size / (time.time() - self.start_time))}/秒")
                logging.info(f"- 位置: {self.filepath}")
        except Exception as e:
            self.error = True
            self.error_msg = str(e)
            self.status = DownloadStatus.ERROR
            logging.error(f"下载时出错 {self.url}: {self.error_msg}")
            # 添加详细错误信息
            logging.error(f"完整错误: {str(e)}")

        self.status = DownloadStatus.COMPLETE
        utilities.enable_sleep_after_running()


    def get_percent(self) -> float:
        """
        Query the download percent

        Returns:
            float: The download percent, or -1 if unknown
        """

        if self.total_file_size == 0.0:
            return -1
        return self.downloaded_file_size / self.total_file_size * 100


    def get_speed(self) -> float:
        """
        Query the download speed

        Returns:
            float: The download speed in bytes per second
        """

        return self.downloaded_file_size / (time.time() - self.start_time)


    def get_time_remaining(self) -> float:
        """
        Query the time remaining for the download

        Returns:
            float: The time remaining in seconds, or -1 if unknown
        """

        if self.total_file_size == 0.0:
            return -1
        speed = self.get_speed()
        if speed <= 0:
            return -1
        return (self.total_file_size - self.downloaded_file_size) / speed


    def get_file_size(self) -> float:
        """
        Query the file size of the file to be downloaded

        Returns:
            float: The file size in bytes, or 0.0 if unknown
        """

        return self.total_file_size


    def is_active(self) -> bool:
        """
        Query if the download is active

        Returns:
            boolean: True if active, False if completed, failed, stopped, or inactive
        """

        if self.status == DownloadStatus.DOWNLOADING:
            return True
        return False


    def stop(self) -> None:
        """
        Stop the download

        If the download is active, this function will hold the thread until stopped
        """

        self.should_stop = True
        if self.active_thread:
            while self.active_thread.is_alive():
                time.sleep(1)