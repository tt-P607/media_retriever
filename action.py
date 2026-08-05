"""media_retriever Action：通过 media_id 精确发送用户发过的媒体。

LLM Action，AI 通过 media_id 精确指定要发送的媒体。
支持 image / emoji / voice / video / file 五种类型。
"""

from __future__ import annotations

from typing import Annotated, AsyncGenerator, cast

from src.app.plugin_system.api.service_api import get_service
from src.app.plugin_system.base import BaseAction
from src.kernel.logger import get_logger

from .service import MediaRetrieverService

logger = get_logger(__name__)


class SendUserMediaAction(BaseAction):
    """通过 media_id 精确发送用户发过的媒体。

    media_id 直接从聊天记录的媒体占位符中提取：
    - [图片(media_id)] 或 [图片(media_id):描述]
    - [表情包(media_id)] 或 [表情包(media_id):描述]
    - [语音(media_id):text]
    file 类型使用 list_files 返回的完整文件名作为 media_id。
    """

    name: str = "send_user_media"
    description: str = (
        "发送用户之前发过的图片、表情包、语音、视频或文件。"
        "image/emoji/voice/video：media_id 直接从聊天记录的媒体占位符括号内提取，"
        "如 [图片(a1b2c3...)] 中的 a1b2c3... 即为 media_id。"
        "file：media_id 可以是已下载的文件名（通过 list_files 查看），"
        "也可以是电脑上任意文件的绝对路径（如 D:/Desktop/report.txt）。"
        "适用场景：复述某张图片、转发之前的语音、"
        "用别人发过的表情包回应、重新发送之前收到的文件、发送本地文件。"
    )
    primary_action: bool = False
    associated_types: list[str] = ["image", "emoji", "voice", "video", "file"]

    async def execute(
        self,
        media_id: Annotated[
            str,
            "要发送的媒体 ID。image/emoji/voice/video 为媒体占位符中的 media_id，"
            "file 类型为文件名（通过 list_files 查看）或绝对路径（如 D:/Desktop/report.txt）。",
        ],
        media_type: Annotated[
            str,
            "媒体类型：image/emoji/voice/video/file",
        ],
    ) -> AsyncGenerator[tuple[bool, str] | None, None]:
        """通过 media_id 精确发送指定媒体。

        Args:
            media_id: 媒体 ID（image/emoji/voice/video）或文件名（file）
            media_type: 媒体类型

        Yields:
            None 表示中间状态，最后 yield (bool, str) 为最终结果
        """
        service = get_service("media_retriever:service:media_retriever")
        if service is None:
            yield False, "media_retriever service 未加载"
            return

        service = cast(MediaRetrieverService, service)
        stream_id = self.chat_stream.stream_id
        platform = getattr(self.chat_stream, "platform", None)

        yield None

        if media_type == "file":
            ok, msg = await self._send_file_from_local(
                service, stream_id, platform, media_id
            )
            yield ok, msg
            return

        media_info = await service.get_media_by_id(media_id)
        if media_info is None:
            yield False, f"未找到 media_id={media_id} 对应的媒体"
            return

        file_path = media_info.get("path")
        if not file_path:
            yield False, f"media_id={media_id} 无有效路径"
            return

        ok, msg = await service.send_media(
            stream_id=stream_id,
            platform=platform,
            media_type=media_type,
            path=file_path,
        )
        yield ok, msg

    async def _send_file_from_local(
        self,
        service: MediaRetrieverService,
        stream_id: str,
        platform: str | None,
        file_name: str,
    ) -> tuple[bool, str]:
        """发送指定文件，支持绝对路径和已下载文件名。

        如果 file_name 是绝对路径（含盘符或路径分隔符），直接使用该路径。
        否则从已下载文件列表中查找匹配项。

        Args:
            service: MediaRetrieverService 实例
            stream_id: 聊天流 ID
            platform: 平台名称
            file_name: 文件名或绝对路径

        Returns:
            (是否成功, 描述消息)
        """
        from pathlib import PurePath

        # 判断是否为绝对路径（含盘符如 D:/ 或路径分隔符）
        is_path = "/" in file_name or "\\" in file_name
        if is_path:
            file_path = file_name
            display_name = PurePath(file_name).name
            return await service.send_media(
                stream_id=stream_id,
                platform=platform,
                media_type="file",
                path=file_path,
                file_name=display_name,
            )

        # 从已下载文件列表中查找
        files = service.list_files(stream_id)
        if not files:
            return False, "当前聊天流中没有已下载的文件"

        matched = [f for f in files if f["name"] == file_name]
        if not matched:
            return False, f"未找到文件: {file_name}"

        target = matched[0]
        file_path = service.resolve_downloaded_file(stream_id, target["name"])
        if file_path is None:
            return False, f"文件不存在: {file_name}"

        return await service.send_media(
            stream_id=stream_id,
            platform=platform,
            media_type="file",
            path=file_path,
            file_name=target["name"],
        )
