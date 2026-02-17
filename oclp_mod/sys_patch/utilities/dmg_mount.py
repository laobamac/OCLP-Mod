"""
dmg_mount.py: PatcherSupportPkg DMG 挂载。处理 Universal-Binaries 和 laobamacInternalResources DMGs。
"""

import logging
import subprocess
import applescript

from pathlib import Path

from ... import constants

from ...support import subprocess_wrapper


class PatcherSupportPkgMount:

    def __init__(self, global_constants: constants.Constants) -> None:
        self.constants: constants.Constants = global_constants
        self.icon_path = str(self.constants.app_icon_path).replace("/", ":")[1:]


    def _mount_universal_binaries_dmg(self) -> bool:
        """
        Mount PatcherSupportPkg's Universal-Binaries.dmg
        """
        if not Path(self.constants.payload_local_binaries_root_path_dmg).exists():
            logging.info("- PatcherSupportPkg 资源缺失，Patcher 可能已损坏!!!")
            return False

        output = subprocess_wrapper.run_as_root(
            [
                "/usr/bin/hdiutil", "attach", "-noverify", f"{self.constants.payload_local_binaries_root_path_dmg}",
                "-mountpoint", Path(self.constants.payload_path / Path("Universal-Binaries")),
                "-nobrowse",
                "-shadow", Path(self.constants.payload_path / Path("Universal-Binaries_overlay")),
                "-passphrase", "password"
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        if output.returncode != 0:
            logging.info("- 挂载 Universal-Binaries.dmg 失败")
            subprocess_wrapper.log(output)
            return False

        logging.info("- 已挂载 Universal-Binaries.dmg")
        return True


    def _mount_laobamac_internal_resources_dmg(self) -> bool:
        """
        Mount PatcherSupportPkg's laobamacInternalResources.dmg (if available)
        """
        if not Path(self.constants.overlay_psp_path_dmg).exists():
            return True
        if not Path("~/.laobamac_developer").expanduser().exists():
            return True
        if self.constants.cli_mode is True:
            return True

        logging.info("- 找到 laobamacInternal 资源，正在挂载...")

        for i in range(3):
            key = self._request_decryption_key(i)
            output = subprocess.run(
                [
                    "/usr/bin/hdiutil", "attach", "-noverify", f"{self.constants.overlay_psp_path_dmg}",
                    "-mountpoint", Path(self.constants.payload_path / Path("laobamacInternal")),
                    "-nobrowse",
                    "-passphrase", key
                ],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            if output.returncode != 0:
                logging.info("- 挂载 laobamacInternal 资源失败")
                subprocess_wrapper.log(output)

                if "Authentication error" not in output.stdout.decode():
                    self._display_authentication_error()

                if i == 2:
                    self._display_too_many_attempts()
                    return False
                continue
            break

        logging.info("- 已挂载 laobamacInternal 资源")
        return self._merge_laobamac_internal_resources()


    def _merge_laobamac_internal_resources(self) -> bool:
        """
        Merge laobamacInternal resources with Universal-Binaries
        """
        result = subprocess.run(
            [
                "/usr/bin/ditto", f"{self.constants.payload_path / Path('laobamacInternal')}", f"{self.constants.payload_path / Path('Universal-Binaries')}"
            ],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        if result.returncode != 0:
            logging.info("- 合并 laobamacInternal 资源失败")
            subprocess_wrapper.log(result)
            return False

        return True


    def _request_decryption_key(self, attempt: int) -> str:
        """
        Fetch the decryption key for laobamacInternalResources.dmg
        """
        # Only return on first attempt
        if attempt == 0:
            if Path("~/.laobamac_developer_key").expanduser().exists():
                return Path("~/.laobamac_developer_key").expanduser().read_text().strip()

        password = ""
        msg = "欢迎使用 laobamacInternal 计划，请提供解密密钥以访问内部资源。点击取消以跳过。"
        if attempt > 0:
            msg = f"解密失败，请重试。剩余尝试次数 {2 - attempt} 次。 "

        try:
            password = applescript.AppleScript(
                f"""
                set theResult to display dialog "{msg}" default answer "" with hidden answer with title "OCLP-Mod" with icon file "{self.icon_path}"

                return the text returned of theResult
                """
            ).run()
        except Exception as e:
            pass

        return password


    def _display_authentication_error(self) -> None:
        """
        Display authentication error dialog
        """
        try:
            applescript.AppleScript(
                f"""
                display dialog "挂载 laobamacInternal 资源失败，请提交内部雷达。" with title "OCLP-Mod" with icon file "{self.icon_path}"
                """
            ).run()
        except Exception as e:
            pass


    def _display_too_many_attempts(self) -> None:
        """
        Display too many attempts dialog
        """
        try:
            applescript.AppleScript(
                f"""
                display dialog "挂载 laobamacInternal 资源失败，密码错误次数过多。如果继续出现此问题且使用了正确的解密密钥，请提交内部雷达。" with title "OCLP-Mod" with icon file "{self.icon_path}"
                """
            ).run()
        except Exception as e:
            pass


    def mount(self) -> bool:
        """
        Mount PatcherSupportPkg resources

        Returns:
            bool: True if all resources are mounted, False otherwise
        """
        # If already mounted, skip
        if Path(self.constants.payload_local_binaries_root_path).exists():
            logging.info("- 本地 PatcherSupportPkg 资源可用，继续...")
            return True

        if self._mount_universal_binaries_dmg() is False:
            return False

        if self._mount_laobamac_internal_resources_dmg() is False:
            return False

        return True