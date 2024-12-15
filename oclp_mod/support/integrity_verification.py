"""
integrity_verification.py: 验证通过 .chunklist 和 .integrityDataV1 文件下载的 Apple 文件完整性

基于 chunklist.py:
- https://gist.github.com/dhinakg/cbe30edf31ddc153fd0b0c0570c9b041
"""

import enum
import hashlib
import logging
import binascii
import threading

from typing import Union
from pathlib import Path

CHUNK_LENGTH = 4 + 32


class ChunklistStatus(enum.Enum):
    """
    Chunklist 状态
    """
    IN_PROGRESS = 0
    SUCCESS     = 1
    FAILURE     = 2


class ChunklistVerification:
    """
    库，用于根据 chunklist 格式验证 Apple 的文件
    支持 chunklist 和 integrityDataV1 文件
    - 参考: https://github.com/apple-oss-distributions/xnu/blob/xnu-8020.101.4/bsd/kern/chunklist.h

    参数:
        file_path      (Path): 要验证的文件路径
        chunklist_path (Path): chunklist 文件路径

    使用方法:
        >>> chunk_obj = ChunklistVerification("InstallAssistant.pkg", "InstallAssistant.pkg.integrityDataV1")
        >>> chunk_obj.validate()
        >>> while chunk_obj.status == ChunklistStatus.IN_PROGRESS:
        ...     print(f"正在验证 {chunk_obj.current_chunk} of {chunk_obj.total_chunks}")

        >>> if chunk_obj.status == ChunklistStatus.FAILURE:
        ...     print(chunk_obj.error_msg)
    """

    def __init__(self, file_path: Path, chunklist_path: Union[Path, bytes]) -> None:
        if isinstance(chunklist_path, bytes):
            self.chunklist_path: bytes = chunklist_path
        else:
            self.chunklist_path: Path = Path(chunklist_path)
        self.file_path:          Path = Path(file_path)

        self.chunks: dict = self._generate_chunks(self.chunklist_path)

        self.error_msg:     str = ""
        self.current_chunk: int = 0
        self.total_chunks:  int = len(self.chunks)

        self.status: ChunklistStatus = ChunklistStatus.IN_PROGRESS


    def _generate_chunks(self, chunklist: Union[Path, bytes]) -> dict:
        """
        生成包含 chunklist 头和块的字典

        参数:
            chunklist (Path | bytes): chunklist 文件路径或 chunklist 文件本身
        """

        chunklist: bytes = chunklist if isinstance(chunklist, bytes) else chunklist.read_bytes()

        # 参考: https://github.com/apple-oss-distributions/xnu/blob/xnu-8020.101.4/bsd/kern/chunklist.h#L59-L69
        header: dict = {
            "magic":       chunklist[:4],
            "length":      int.from_bytes(chunklist[4:8], "little"),
            "fileVersion": chunklist[8],
            "chunkMethod": chunklist[9],
            "sigMethod":   chunklist[10],
            "chunkCount":  int.from_bytes(chunklist[12:20], "little"),
            "chunkOffset": int.from_bytes(chunklist[20:28], "little"),
            "sigOffset":   int.from_bytes(chunklist[28:36], "little")
        }

        if header["magic"] != b"CNKL":
            return None

        all_chunks = chunklist[header["chunkOffset"]:header["chunkOffset"]+header["chunkCount"]*CHUNK_LENGTH]
        chunks = [{"length": int.from_bytes(all_chunks[i:i+4], "little"), "checksum": all_chunks[i+4:i+CHUNK_LENGTH]} for i in range(0, len(all_chunks), CHUNK_LENGTH)]

        return chunks


    def _validate(self) -> None:
        """
        验证提供的文件是否符合 chunklist
        """

        if self.chunks is None:
            self.status = ChunklistStatus.FAILURE
            return

        if not Path(self.file_path).exists():
            self.error_msg = f"文件 {self.file_path} 不存在"
            self.status = ChunklistStatus.FAILURE
            logging.info(self.error_msg)
            return

        if not Path(self.file_path).is_file():
            self.error_msg = f"文件 {self.file_path} 不是文件"
            self.status = ChunklistStatus.FAILURE
            logging.info(self.error_msg)
            return

        with self.file_path.open("rb") as f:
            for chunk in self.chunks:
                self.current_chunk += 1
                status = hashlib.sha256(f.read(chunk["length"])).digest()
                if status != chunk["checksum"]:
                    self.error_msg = f"块 {self.current_chunk} 校验和状态失败: 块校验和 {binascii.hexlify(chunk['checksum']).decode()}, 计算校验和 {binascii.hexlify(status).decode()}"
                    self.status = ChunklistStatus.FAILURE
                    logging.info(self.error_msg)
                    return

        self.status = ChunklistStatus.SUCCESS


    def validate(self) -> None:
        """
        启动 _validate() 线程
        """
        threading.Thread(target=self._validate).start()