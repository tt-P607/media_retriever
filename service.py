"""media_retriever 服务实现。

提供媒体检索、文件下载/管理/LRU清理、文件读取、媒体发送能力。
"""

from __future__ import annotations

import ast
import asyncio
import base64
import json
from pathlib import Path
from typing import Any

import httpx

from src.app.plugin_system.api.adapter_api import (
    get_adapter,
    list_active_adapters,
    send_adapter_command,
)
from src.app.plugin_system.api.media_api import get_media_info
from src.app.plugin_system.api.send_api import (
    send_emoji,
    send_file,
    send_image,
    send_video,
    send_voice,
)
from src.app.plugin_system.base import BaseService
from src.kernel.logger import get_logger

from .config import MediaRetrieverConfig

logger = get_logger(__name__)

_SEND_FUNC_MAP: dict[str, Any] = {
    "image": send_image,
    "emoji": send_emoji,
    "voice": send_voice,
    "video": send_video,
}


def to_wsl_path(path: str) -> str:
    """将 Windows 路径转换为 WSL/容器挂载形式。

    如 `E:/MoFox-Bot/file.txt` → `/mnt/e/MoFox-Bot/file.txt`。
    非盘符路径原样返回（仅统一分隔符）。

    Args:
        path: 原始路径字符串

    Returns:
        WSL 形式的路径
    """
    normalized = path.replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        return f"/mnt/{normalized[0].lower()}{normalized[2:]}"
    return normalized


def _parse_content(content_raw: Any) -> dict[str, Any] | None:
    """解析消息 content 字段为 dict。

    框架的 _serialize_content_for_db 使用 Python str() 而非 json.dumps()，
    因此数据库中存储的是 Python repr 格式（单引号），需要兼容。

    Args:
        content_raw: content 原始值，可能是 JSON 字符串、Python repr 字符串或 dict

    Returns:
        解析后的 dict，解析失败返回 None
    """
    if isinstance(content_raw, dict):
        return content_raw
    if isinstance(content_raw, str):
        try:
            result = json.loads(content_raw)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            result = ast.literal_eval(content_raw)
            if isinstance(result, dict):
                return result
        except (ValueError, SyntaxError):
            pass
    return None


class MediaRetrieverService(BaseService):
    """媒体检索与文件管理服务。

    对外提供媒体检索、文件下载/管理/LRU清理、文件读取、媒体发送能力。
    """
    service_description = "媒体检索与文件管理服务"
    service_name = "media_retriever"

    name: str = "media_retriever"
    description: str = "媒体检索与文件管理服务"
    version: str = "1.0.2"

    def _cfg(self) -> MediaRetrieverConfig:
        """获取插件配置实例。"""
        cfg = self.plugin.config
        if not isinstance(cfg, MediaRetrieverConfig):
            raise RuntimeError("media_retriever plugin config 未正确加载")
        return cfg

    def _data_dir(self) -> Path:
        """获取文件存储根目录并确保存在。"""
        path = Path(self._cfg().file.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _stream_files_dir(self, stream_id: str) -> Path:
        """获取指定聊天流的文件存储目录：{data_dir}/{stream_id}/。

        Args:
            stream_id: 聊天流 ID

        Returns:
            该聊天流对应的文件目录 Path
        """
        return self._data_dir() / stream_id

    def _allowed_extensions_set(self) -> set[str]:
        """获取允许读取的文件扩展名集合。"""
        raw = self._cfg().read.allowed_extensions
        return {ext.strip().lower() for ext in raw.split(",") if ext.strip()}

    # ─── 媒体发送 ───

    @staticmethod
    async def load_media_as_base64(path: str) -> str | None:
        """从文件路径读取媒体文件并转为 base64。

        Args:
            path: 文件路径

        Returns:
            base64 编码字符串，读取失败返回 None
        """
        try:
            data = await asyncio.to_thread(Path(path).read_bytes)
            return base64.b64encode(data).decode("utf-8")
        except Exception as e:
            logger.warning(f"读取媒体文件失败 {path}: {e}")
            return None

    async def get_media_by_id(
        self,
        media_id: str,
    ) -> dict[str, Any] | None:
        """根据媒体 ID 查询媒体信息（含路径和描述）。

        支持 image / emoji / voice / video 四种媒体类型。

        Args:
            media_id: 媒体哈希值

        Returns:
            媒体信息字典，未找到返回 None
        """
        return await get_media_info(media_id)

    async def send_media(
        self,
        stream_id: str,
        platform: str | None,
        media_type: str,
        path: str,
        file_name: str | None = None,
    ) -> tuple[bool, str]:
        """发送指定路径的媒体文件。

        Args:
            stream_id: 聊天流 ID
            platform: 平台名称（可选）
            media_type: 媒体类型（image/emoji/voice/video/file）
            path: 文件路径
            file_name: 文件名（仅 file 类型需要）

        Returns:
            (是否成功, 描述消息)
        """
        if media_type == "file":
            cfg = self._cfg()
            send_path = to_wsl_path(path) if cfg.file.wsl_mode else path
            try:
                ok = await send_file(
                    file_path=send_path,
                    stream_id=stream_id,
                    platform=platform,
                    file_name=file_name,
                )
                if ok:
                    return True, f"已发送文件: {file_name or path}"
                return False, "文件发送失败"
            except Exception as e:
                logger.warning(f"发送文件失败: {e}")
                return False, f"发送文件异常: {e}"

        send_func = _SEND_FUNC_MAP.get(media_type)
        if send_func is None:
            return False, f"不支持的媒体类型: {media_type}"

        b64_data = await self.load_media_as_base64(path)
        if b64_data is None:
            return False, f"无法读取媒体文件: {path}"

        try:
            ok = await send_func(b64_data, stream_id, platform)
            if ok:
                return True, f"已发送{media_type}"
            return False, f"{media_type}发送失败"
        except Exception as e:
            logger.warning(f"发送{media_type}失败: {e}")
            return False, f"发送{media_type}异常: {e}"

    # ─── 文件管理 ───

    def _resolve_adapter_signature(self, platform: str | None) -> str | None:
        """解析用于文件 URL 命令的适配器签名。

        优先选择与消息平台匹配的活跃适配器（napcat / snowluma 均支持
        OneBot v11 的 get_group_file_url / get_private_file_url 命令），
        用户无需手动配置；无匹配时回退到配置的 adapter_signature。

        Args:
            platform: 消息来源平台（可空）

        Returns:
            适配器签名；未找到可用适配器返回 None
        """
        cfg_adapter = self._cfg().file.adapter_signature.strip()
        if platform:
            for sig in list_active_adapters():
                adapter = get_adapter(sig)
                if adapter is not None and getattr(adapter, "platform", "") == platform:
                    logger.debug(f"文件下载使用平台匹配适配器: {sig}")
                    return sig
        return cfg_adapter or None

    async def download_file(
        self,
        stream_id: str,
        group_id: str | None,
        user_id: str | None,
        file_id: str,
        file_name: str,
        file_size: int | None,
        platform: str | None = None,
    ) -> bool:
        """下载文件到 stream_id 子目录。

        流程：
        1. 检查文件大小是否超过 max_file_size_mb，超过则跳过
        2. 解析目标适配器：优先按消息 platform 匹配活跃适配器，
           无匹配时回退到配置的 adapter_signature（默认无需配置）
        3. 通过 adapter_api 调用 OneBot API 获取下载 URL
           - 群文件：get_group_file_url（需要 group_id + file_id）
           - 私聊文件：get_private_file_url（需要 user_id + file_id）
        4. httpx 下载文件到 {data_dir}/{stream_id}/{file_name}
        5. 检查总容量，超过 max_total_size_mb 则 LRU 删除最旧文件

        Args:
            stream_id: 聊天流 ID
            group_id: 群号（群文件场景需要，私聊为 None）
            user_id: 用户号（私聊文件场景需要，群聊为 None）
            file_id: OneBot 文件 ID
            file_name: 保存的文件名
            file_size: 文件大小（字节），None 表示未知
            platform: 消息来源平台，用于自动匹配适配器（可空）

        Returns:
            是否下载成功
        """
        cfg = self._cfg()
        if not cfg.file.enabled:
            return False

        max_bytes = int(cfg.file.max_file_size_mb * 1024 * 1024)
        if file_size is not None and file_size > max_bytes:
            logger.info(f"文件 {file_name} 大小 {file_size} 超过限制 {max_bytes}，跳过下载")
            return False

        adapter_sig = self._resolve_adapter_signature(platform)
        if not adapter_sig:
            logger.warning(f"未找到可用的文件下载适配器，跳过下载 {file_name}")
            return False

        download_url: str | None = None

        if group_id:
            try:
                resp = await send_adapter_command(
                    adapter_sign=adapter_sig,
                    command_name="get_group_file_url",
                    command_data={
                        "group_id": int(group_id),
                        "file_id": file_id,
                    },
                    timeout=cfg.file.download_timeout,
                )
                data = resp.get("data")
                if isinstance(data, dict):
                    download_url = data.get("url")
            except Exception as e:
                logger.warning(f"获取群文件 URL 失败: {e}")

        elif user_id:
            try:
                resp = await send_adapter_command(
                    adapter_sign=adapter_sig,
                    command_name="get_private_file_url",
                    command_data={
                        "user_id": int(user_id),
                        "file_id": file_id,
                    },
                    timeout=cfg.file.download_timeout,
                )
                data = resp.get("data")
                if isinstance(data, dict):
                    download_url = data.get("url")
            except Exception as e:
                logger.warning(f"获取私聊文件 URL 失败: {e}")

        if not download_url:
            logger.warning(f"无法获取文件 {file_name} 的下载 URL")
            return False

        stream_dir = self._stream_files_dir(stream_id)
        stream_dir.mkdir(parents=True, exist_ok=True)
        target_path = stream_dir / file_name

        try:
            timeout = httpx.Timeout(cfg.file.download_timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(download_url)
                resp.raise_for_status()
                await asyncio.to_thread(
                    target_path.write_bytes, resp.content
                )
        except Exception as e:
            logger.warning(f"下载文件 {file_name} 失败: {e}")
            return False

        await self._enforce_size_limit()
        logger.info(f"文件 {file_name} 已下载到 {target_path}")
        return True

    def _get_total_size(self) -> int:
        """计算所有子目录文件总大小（字节）。

        Returns:
            总字节数
        """
        total = 0
        root = self._data_dir()
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    total += path.stat().st_size
                except OSError:
                    pass
        return total

    async def _enforce_size_limit(self) -> None:
        """LRU 清理：按文件修改时间排序，删除最旧文件直到总容量回到上限内。"""
        cfg = self._cfg()
        max_bytes = int(cfg.file.max_total_size_mb * 1024 * 1024)
        root = self._data_dir()

        all_files: list[Path] = [p for p in root.rglob("*") if p.is_file()]
        total = sum(
            f.stat().st_size for f in all_files
            if self._safe_stat_size(f)
        )

        if total <= max_bytes:
            return

        all_files.sort(key=lambda p: self._safe_mtime(p))

        for f in all_files:
            if total <= max_bytes:
                break
            try:
                size = f.stat().st_size
                f.unlink(missing_ok=True)
                total -= size
                logger.debug(f"LRU 清理删除文件: {f}")
            except OSError:
                pass

    @staticmethod
    def _safe_stat_size(path: Path) -> int:
        """安全获取文件大小，失败返回 0。"""
        try:
            return path.stat().st_size
        except OSError:
            return 0

    @staticmethod
    def _safe_mtime(path: Path) -> float:
        """安全获取文件修改时间，失败返回 0。"""
        try:
            return path.stat().st_mtime
        except OSError:
            return 0.0

    # ─── 文件读取 ───

    def resolve_downloaded_file(self, stream_id: str, file_name: str) -> str | None:
        """解析已下载文件在存储目录中的绝对路径。

        仅接受已下载列表中的文件名，防止任意路径拼接。

        Args:
            stream_id: 聊天流 ID
            file_name: 已下载文件名

        Returns:
            文件的绝对路径字符串，文件不存在时返回 None
        """
        target = self._stream_files_dir(stream_id) / file_name
        if not target.is_file():
            return None
        return str(target)

    def list_files(self, stream_id: str) -> list[dict[str, Any]]:
        """列出当前聊天流子目录中的文件。

        Args:
            stream_id: 聊天流 ID

        Returns:
            文件信息字典列表，每项含 name/size/modified
        """
        stream_dir = self._stream_files_dir(stream_id)
        if not stream_dir.exists():
            return []

        files: list[dict[str, Any]] = []
        for path in stream_dir.iterdir():
            if not path.is_file():
                continue
            stat = path.stat()
            files.append({
                "name": path.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })

        files.sort(key=lambda f: f["modified"], reverse=True)
        return files

    def read_file(
        self,
        stream_id: str,
        file_name: str,
        max_lines: int = 200,
        offset: int = 0,
    ) -> str | None:
        """读取当前聊天流子目录中指定文件的内容。

        安全限制：
        - 仅允许读取当前 stream_id 子目录下的文件
        - 路径校验防止目录穿越（.. 攻击）
        - 仅允许读取 allowed_extensions 中的扩展名
        - 按行读取，支持 offset/max_lines 分页

        Args:
            stream_id: 聊天流 ID
            file_name: 文件名（不含路径）
            max_lines: 最多读取的行数，默认 200
            offset: 起始行号（0-based），默认 0

        Returns:
            文件文本内容，无法读取则返回 None；
            若内容被截断，末尾附带提示信息
        """
        stream_dir = self._stream_files_dir(stream_id)
        target = (stream_dir / file_name).resolve()

        try:
            stream_dir_resolved = stream_dir.resolve()
        except OSError:
            return None

        if not str(target).startswith(str(stream_dir_resolved)):
            logger.warning(f"路径穿越被拦截: {file_name}")
            return None

        if not target.is_file():
            return None

        ext = target.suffix.lower()
        if ext not in self._allowed_extensions_set():
            return f"[不支持的文件类型: {ext}]"

        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"读取文件 {file_name} 失败: {e}")
            return None

        lines = text.splitlines()
        total_lines = len(lines)

        if offset >= total_lines:
            return f"[offset={offset} 超出文件总行数 {total_lines}]"

        end = min(offset + max_lines, total_lines)
        result_lines = lines[offset:end]
        result = "\n".join(result_lines)

        if end < total_lines:
            result += f"\n\n[已读取第 {offset}~{end - 1} 行，共 {total_lines} 行，还有 {total_lines - end} 行未读取，可增大 offset 继续]"
        else:
            result += f"\n\n[文件共 {total_lines} 行，已全部读取完毕]"

        return result
