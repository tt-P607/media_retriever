"""media_retriever Tool：列出和读取已下载文件。

提供两个 LLM Tool：
- ListFilesTool：列出当前聊天流中已下载的文件
- ReadFileTool：读取当前聊天流中已下载文件的内容
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

    name: str = "list_files"
    description: str = (
        "列出当前聊天中用户发送过并被自动下载保存的文件列表。"
        "文件按聊天流分类存储，只能查看当前聊天的文件。"
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
