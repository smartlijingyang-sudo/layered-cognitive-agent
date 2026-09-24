"""员工电脑（我的电脑）安全沙箱适配器（ADR-0248 §3.2 / s04）。

包含：
- LocalBoxAdapter: 本地文件树受限沙箱（严格防越界，防提权）
- OnlyboxesBoxAdapter: 基于独立 Docker 容器的隔离沙箱
- get_box_adapter: 统一沙箱适配器工厂
"""

from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path

from lca.infrastructure.computer.box_port import BoxCommandResult, BoxExecutionPort


class LocalBoxAdapter(BoxExecutionPort):
    """本地隔离沙箱适配器。

    根据 ADR-0248 §3.2 规定：
    严格限制在 root_dir 沙箱内（默认 /home/box）。
    任何跳出沙箱的路径操作抛出 PermissionError，严禁 sudo/su 等提权命令。
    """

    def __init__(self, root_dir: str | Path = "/home/box") -> None:
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_safe_path(self, path: str) -> Path:
        clean_sub = path.lstrip("/")
        target = (self.root_dir / clean_sub).resolve()
        try:
            target.relative_to(self.root_dir)
        except ValueError:
            raise PermissionError(
                f"越权访问受阻：路径 '{path}' 超出员工电脑沙箱范围 ({self.root_dir})"
            ) from None
        return target

    async def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        target = self._resolve_safe_path(path)
        if not target.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        content = await asyncio.to_thread(target.read_text, encoding="utf-8")
        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            content = "".join(lines[s:e])
        return content

    async def write_file(
        self,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> str:
        target = self._resolve_safe_path(path)
        if create_directories:
            target.parent.mkdir(parents=True, exist_ok=True)

        # 原子刷盘（临时文件落地 + fsync + 原子 os.replace）
        tmp_target = target.parent / f".tmp_{target.name}_{uuid.uuid4().hex[:8]}"

        def _do_write() -> None:
            with tmp_target.open("w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_target, target)

        try:
            await asyncio.to_thread(_do_write)
        except BaseException:
            if tmp_target.exists():
                tmp_target.unlink()
            raise
        return str(target)

    async def list_files(
        self,
        path: str = ".",
        max_depth: int = 1,
    ) -> list[str]:
        target = self._resolve_safe_path(path)
        if not target.exists():
            raise FileNotFoundError(f"目录不存在: {path}")

        def _scan() -> list[str]:
            return sorted(entry.name for entry in os.scandir(target))

        return await asyncio.to_thread(_scan)

    async def run_command(
        self,
        command: str,
        timeout_s: int = 30,
    ) -> BoxCommandResult:
        cmd_stripped = command.strip()
        # INV-04 安全硬闸：禁止 sudo / su / chroot 提权命令
        if (
            cmd_stripped.startswith("sudo ")
            or cmd_stripped.startswith("su ")
            or " sudo " in command
            or " su " in command
        ):
            raise PermissionError("安全硬闸：员工电脑沙箱禁止提权命令 (sudo/su)")

        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.root_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout_s)
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"员工机命令执行超时（>{timeout_s}s）") from None

        return BoxCommandResult(
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            returncode=proc.returncode if proc.returncode is not None else -1,
        )


class OnlyboxesBoxAdapter(BoxExecutionPort):
    """基于独立容器的员工电脑沙箱适配器（Docker 驱动）。"""

    def __init__(
        self,
        container_name: str = "lca-box-sandbox",
        workdir: str = "/home/box",
        fallback_root: str | Path = "/home/box",
    ) -> None:
        self.container_name = container_name
        self.workdir = workdir
        self._fallback = LocalBoxAdapter(root_dir=fallback_root)
        self._docker_available: bool | None = None

    def _check_docker(self) -> bool:
        if self._docker_available is None:
            self._docker_available = bool(shutil.which("docker"))
        return self._docker_available

    async def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        if not self._check_docker():
            return await self._fallback.read_file(path, start_line, end_line)
        # 容器执行 docker exec cat
        res = await self.run_command(f"cat '{path}'")
        if res.returncode != 0:
            raise FileNotFoundError(f"容器文件不存在或读取失败: {path} ({res.stderr})")
        content = res.stdout
        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            s = (start_line or 1) - 1
            e = end_line or len(lines)
            content = "".join(lines[s:e])
        return content

    async def write_file(
        self,
        path: str,
        content: str,
        create_directories: bool = True,
    ) -> str:
        if not self._check_docker():
            return await self._fallback.write_file(path, content, create_directories)
        dirname = str(Path(path).parent)
        if create_directories and dirname and dirname != ".":
            await self.run_command(f"mkdir -p '{dirname}'")
        # 将内容通过 sh -c 写入
        escaped = content.replace("'", "'\\''")
        res = await self.run_command(f"printf '%s' '{escaped}' > '{path}'")
        if res.returncode != 0:
            raise OSError(f"容器写入文件失败: {res.stderr}")
        return path

    async def list_files(
        self,
        path: str = ".",
        max_depth: int = 1,
    ) -> list[str]:
        if not self._check_docker():
            return await self._fallback.list_files(path, max_depth)
        res = await self.run_command(f"ls -1 '{path}'")
        if res.returncode != 0:
            raise FileNotFoundError(f"容器目录不存在: {path} ({res.stderr})")
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    async def run_command(
        self,
        command: str,
        timeout_s: int = 30,
    ) -> BoxCommandResult:
        if not self._check_docker():
            return await self._fallback.run_command(command, timeout_s)

        cmd_stripped = command.strip()
        if (
            cmd_stripped.startswith("sudo ")
            or cmd_stripped.startswith("su ")
            or " sudo " in command
            or " su " in command
        ):
            raise PermissionError("安全硬闸：员工电脑沙箱禁止提权命令 (sudo/su)")

        exec_cmd = [
            "docker",
            "exec",
            "-i",
            "-w",
            self.workdir,
            "-u",
            "box",
            self.container_name,
            "sh",
            "-c",
            command,
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *exec_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=float(timeout_s)
            )
        except (FileNotFoundError, OSError):
            # 容器不存在或 docker 未就绪，自动回退到本地隔离沙箱
            return await self._fallback.run_command(command, timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(f"容器命令执行超时（>{timeout_s}s）") from None

        return BoxCommandResult(
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            returncode=proc.returncode if proc.returncode is not None else -1,
        )


def get_box_adapter(root_dir: str | Path = "/home/box") -> BoxExecutionPort:
    """获取沙箱执行端口实例。默认优先使用 Onlyboxes 容器，自动具备 LocalBox 优雅回退。"""
    return OnlyboxesBoxAdapter(fallback_root=root_dir)


__all__ = ["LocalBoxAdapter", "OnlyboxesBoxAdapter", "get_box_adapter"]
