"""media_retriever EventHandler：监听文件消息并自动下载。

监听 ON_MESSAGE_RECEIVED 事件，检测消息中的 file 类型 media 项，
调用 Service 下载到插件存储目录。
"""

from __future__ import annotations

from typing import Any, cast

from src.app.plugin_system.api.service_api import get_service
from src.app.plugin_system.base import BaseEventHandler
from src.core.components.types import EventType
from src.kernel.event import EventDecision
from src.kernel.logger import get_logger

from .service import MediaRetrieverService, _parse_content

logger = get_logger(__name__)


class FileMessageHandler(BaseEventHandler):
    """监听消息事件，检测 file 类型消息并下载。

    订阅 ON_MESSAGE_RECEIVED 事件，从消息 content 中提取 file media 项，
    调用 MediaRetrieverService.download_file 下载文件。
    不阻断消息传播流程（返回 EventDecision.PASS）。
    """
    handler_description = "监听文件消息并自动下载到插件存储目录"
    handler_name = "file_message_handler"

    name: str = "file_message_handler"
    description: str = "监听文件消息并自动下载到插件存储目录"
    init_subscribe: list[EventType | str] = [EventType.ON_MESSAGE_RECEIVED]

    async def execute(
        self,
        event_name: str,
        params: dict[str, Any],
    ) -> tuple[EventDecision, dict[str, Any]]:
        """处理消息接收事件。

        从 params 获取 message 对象，检查是否含 file media 项，
        触发下载但不阻断消息传播。

        Args:
            event_name: 事件名称
            params: 事件参数字典，含 message 和 envelope

        Returns:
            (EventDecision.PASS, params) — 不阻断后续处理器
        """
        message = params.get("message")
        if message is None:
            return EventDecision.PASS, params

        stream_id = getattr(message, "stream_id", None)
        if not stream_id:
            return EventDecision.PASS, params

        raw_content = getattr(message, "content", None)
        if not raw_content:
            return EventDecision.PASS, params

        content = _parse_content(raw_content)
        if not content:
            return EventDecision.PASS, params

        media_list = content.get("media")
        if not isinstance(media_list, list):
            return EventDecision.PASS, params

        file_items: list[dict[str, Any]] = []
        for media_item in media_list:
            if not isinstance(media_item, dict):
                continue
            if media_item.get("type") == "file":
                file_items.append(media_item)

        if not file_items:
            return EventDecision.PASS, params

        envelope = params.get("envelope")
        chat_type = getattr(message, "chat_type", "")
        if chat_type == "group":
            group_id = _extract_group_id(envelope)
            user_id = None
        else:
            group_id = None
            user_id = _extract_user_id(envelope)

        service = get_service("media_retriever:service:media_retriever")
        if service is None:
            logger.warning("media_retriever service 未加载，无法下载文件")
            return EventDecision.PASS, params

        service = cast(MediaRetrieverService, service)

        platform = getattr(message, "platform", None)

        for file_item in file_items:
            data = file_item.get("data")
            if not isinstance(data, dict):
                continue
            file_id = str(data.get("id", ""))
            file_name = str(data.get("name", f"file_{file_id}"))
            file_size = data.get("size")

            if not file_id:
                continue

            try:
                await service.download_file(
                    stream_id=stream_id,
                    group_id=group_id,
                    user_id=user_id,
                    file_id=file_id,
                    file_name=file_name,
                    file_size=file_size,
                    platform=platform,
                )
            except Exception as e:
                logger.warning(f"下载文件 {file_name} 失败: {e}")

        return EventDecision.PASS, params


def _extract_group_id(envelope: Any) -> str | None:
    """从信封中提取 group_id。

    envelope 结构为 message_info.group_info.group_id。

    Args:
        envelope: 原始 MessageEnvelope 字典

    Returns:
        group_id 字符串，不存在则返回 None
    """
    if not isinstance(envelope, dict):
        return None
    msg_info = envelope.get("message_info")
    if not isinstance(msg_info, dict):
        return None
    group_info = msg_info.get("group_info")
    if not isinstance(group_info, dict):
        return None
    group_id = group_info.get("group_id")
    if group_id is None:
        return None
    return str(group_id)


def _extract_user_id(envelope: Any) -> str | None:
    """从信封中提取 user_id（私聊场景）。

    envelope 结构为 message_info.user_info.user_id。

    Args:
        envelope: 原始 MessageEnvelope 字典

    Returns:
        user_id 字符串，不存在则返回 None
    """
    if not isinstance(envelope, dict):
        return None
    msg_info = envelope.get("message_info")
    if not isinstance(msg_info, dict):
        return None
    user_info = msg_info.get("user_info")
    if not isinstance(user_info, dict):
        return None
    user_id = user_info.get("user_id")
    if user_id is None:
        return None
    return str(user_id)
