"""media_retriever Tool：列出、读取与强制下载已下载文件。

提供三个 LLM Tool：
- ListFilesTool：列出当前聊天流中已下载的文件
- ReadFileTool：读取当前聊天流中已下载文件的内容
- DownloadFileTool：强制下载超自动限制的文件（bot 按需主动下载）
"""

from __future__ import annotations

from typing import Annotated, cast

from src.app.plugin_system.api.service_api import get_service
from src.app.plugin_system.base import BaseTool
from src.kernel.logger import get_logger

from .service import MediaRetrieverService

logger = get_logger(__name__)


class ListFilesTool(BaseTool):
    """列出当前聊天流中已下载的文件。"""
    tool_description = "列出当前聊天中用户发送过并被自动下载保存的文件列表"
    tool_name = "list_files"

    name: str = "list_files"
    description: str = (
        "列出当前聊天中用户发送过并被自动下载保存的文件列表。"
        "文件按聊天流分类存储，只能查看当前聊天的文件。"
        "可用于判断某个文件是否已自动下载：列表里有即已下载，可直接处理；"
        "列表里没有（通常因超过自动下载阈值）则需调用 download_file 强制下载。"
    )

    async def execute(self) -> tuple[bool, str]:
        """返回当前聊天流子目录中的文件列表。

        Returns:
            (是否成功, 文件列表文本)
        """
        service = get_service("media_retriever:service:media_retriever")
        if service is None:
            return False, "media_retriever service 未加载"

        service = cast(MediaRetrieverService, service)
        stream_id = self.get_current_stream_id()
        if not stream_id:
            return False, "无法获取当前聊天流 ID"

        files = service.list_files(stream_id)
        if not files:
            return True, "当前聊天中没有已下载的文件"

        lines: list[str] = []
        for f in files:
            size_kb = f["size"] / 1024
            lines.append(f"- {f['name']} ({size_kb:.1f} KB)")

        return True, "\n".join(lines)


class ReadFileTool(BaseTool):
    """读取当前聊天流中已下载文件的内容。"""
    tool_description = "读取当前聊天中已下载保存的文件内容"
    tool_name = "read_file"

    name: str = "read_file"
    description: str = (
        "读取当前聊天中已下载保存的文件内容。"
        "支持文本类文件（txt、py、json、md、csv、log、xml、yaml、toml、js、ts 等），"
        "二进制文件不会被读取为文本。"
        "只能读取当前聊天的文件，不能跨聊天流访问。"
        "支持分页读取：通过 offset 和 max_lines 参数控制读取范围，适用于大文件。"
    )

    async def execute(
        self,
        file_name: Annotated[str, "要读取的文件名（不含路径，含消息ID后缀）"],
        max_lines: Annotated[int, "最多读取的行数，默认200"] = 200,
        offset: Annotated[int, "起始行号（0-based），默认0，可用于分页读取大文件"] = 0,
    ) -> tuple[bool, str]:
        """读取文件内容。

        Args:
            file_name: 文件名（不含路径，含消息ID后缀）
            max_lines: 最多读取的行数
            offset: 起始行号（0-based）

        Returns:
            (是否成功, 文件文本内容)
        """
        service = get_service("media_retriever:service:media_retriever")
        if service is None:
            return False, "media_retriever service 未加载"

        service = cast(MediaRetrieverService, service)
        stream_id = self.get_current_stream_id()
        if not stream_id:
            return False, "无法获取当前聊天流 ID"

        content = service.read_file(stream_id, file_name, max_lines=max_lines, offset=offset)
        if content is None:
            return False, f"无法读取文件: {file_name}"

        return True, content


class DownloadFileTool(BaseTool):
    """强制下载当前消息中的文件（绕过自动下载的大小限制）。"""

    name: str = "download_file"
    description: str = (
        "主动下载当前消息中用户发来的文件（含超过自动下载大小限制的大文件）。"
        "判断是否需调用：文件大小超过自动下载阈值（见本描述末尾标注的阈值）"
        "或不确定是否已下载时，先调用 list_files 确认；未下载才调用本工具强制下载。"
        "从当前消息中提取文件信息并强制下载保存到聊天流目录。下载后按类型处理："
        "文本/代码类文件（txt/py/json/md 等）用 read_file 读取内容；"
        "图片/音频/视频等多媒体文件用 send_user_media 发送给用户，"
        "或按当前场景交给其他可用工具处理。"
        "file_name 传 LLM 可见的 [文件:名字(大小)] 占位符中的名字即可，无需知道 file_id。"
    )

    async def execute(
        self,
        file_name: Annotated[str, "要下载的文件名（LLM 可见 [文件:名字(大小)] 占位符中的名字，不含大小括号）"],
    ) -> tuple[bool, str]:
        """从当前触发消息提取文件段并强制下载。

        Args:
            file_name: 文件名（不含路径）。

        Returns:
            (是否成功, 下载结果或错误信息)。
        """
        service = get_service("media_retriever:service:media_retriever")
        if service is None:
            return False, "media_retriever service 未加载"
        service = cast(MediaRetrieverService, service)

        stream_id = self.get_current_stream_id()
        if not stream_id:
            return False, "无法获取当前聊天流 ID"

        message = self.trigger_message
        if message is None:
            return False, "无法获取当前消息（没有触发消息上下文）"

        # 从当前消息的 extra["media"] 中找匹配的文件段，提取 file_id / size
        media_list = (getattr(message, "extra", None) or {}).get("media") or []
        file_seg: dict | None = None
        for m in media_list:
            if not isinstance(m, dict) or m.get("type") != "file":
                continue
            data = m.get("data")
            if not isinstance(data, dict):
                continue
            seg_name = str(data.get("name") or data.get("file") or "")
            if seg_name == file_name:
                file_seg = data
                break
        if file_seg is None:
            return False, (
                f"当前消息中未找到文件 '{file_name}'。仅能下载当前消息中发送的文件，"
                "请确认文件名与 [文件:名字(大小)] 占位符中的名字一致。"
            )

        file_id = str(file_seg.get("id") or file_seg.get("file_id") or "")
        if not file_id:
            return False, f"文件 '{file_name}' 缺少文件 ID，无法下载"

        size_raw = file_seg.get("size") or file_seg.get("file_size")
        file_size: int | None = None
        if isinstance(size_raw, (int, float)):
            file_size = int(size_raw)
        elif isinstance(size_raw, str) and size_raw.strip().isdigit():
            file_size = int(size_raw.strip())

        # 群/私聊上下文：群号从 extra 取，私聊用 sender_id
        extra = getattr(message, "extra", None) or {}
        chat_type = getattr(message, "chat_type", "")
        group_id: str | None = None
        user_id: str | None = None
        if chat_type == "group":
            group_id = str(extra.get("group_id") or extra.get("target_group_id") or "")
        else:
            user_id = str(getattr(message, "sender_id", "") or "")

        platform = getattr(message, "platform", None)

        ok = await service.download_file(
            stream_id=stream_id,
            group_id=group_id or None,
            user_id=user_id or None,
            file_id=file_id,
            file_name=file_name,
            file_size=file_size,
            platform=platform,
            force=True,
        )
        if not ok:
            return False, f"强制下载文件 '{file_name}' 失败（可能无下载 URL 或已超总容量）"

        path = service.resolve_downloaded_file(stream_id, file_name)
        size_mb = (file_size or 0) / 1024 / 1024
        return True, (
            f"已强制下载文件 '{file_name}'（{size_mb:.1f}MB）到本地，"
            f"路径: {path}。可继续用 read_file 读取内容、用 send_user_media 发送，"
            "或交给其他工具处理。"
        )
