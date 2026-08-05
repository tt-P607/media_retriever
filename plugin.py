"""media_retriever 插件入口。

注册 5 个组件：
- MediaRetrieverService（Service）
- FileMessageHandler（EventHandler）
- SendUserMediaAction（Action）
- ListFilesTool（Tool）
- ReadFileTool（Tool）
"""

from __future__ import annotations


from src.app.plugin_system.base import BasePlugin, register_plugin
from src.kernel.logger import get_logger

from .action import SendUserMediaAction
from .config import MediaRetrieverConfig
from .file_handler import FileMessageHandler
from .service import MediaRetrieverService
from .tool import ListFilesTool, ReadFileTool

logger = get_logger(__name__)


@register_plugin
class MediaRetrieverPlugin(BasePlugin):
    """media_retriever 插件。

    从聊天历史检索并发送用户发过的媒体，
    自动下载管理文件，提供文件读取能力。
    """

    plugin_name: str = "media_retriever"
    plugin_description: str = (
        "从聊天历史检索并发送用户发过的媒体，"
        "自动下载管理文件，提供文件读取能力"
    )
    plugin_version: str = "1.0.1"

    configs: list[type] = [MediaRetrieverConfig]
    dependent_components: list[str] = []

    def get_components(self) -> list[type]:
        """返回本插件提供的组件类。"""
        return [
            MediaRetrieverService,
            FileMessageHandler,
            SendUserMediaAction,
            ListFilesTool,
            ReadFileTool,
        ]

    async def on_plugin_loaded(self) -> None:
        """插件加载完成后：同步自定义指令到组件描述。"""
        if isinstance(self.config, MediaRetrieverConfig):
            custom = self.config.prompt.custom_instructions.strip()
            if custom:
                SendUserMediaAction.description = (
                    SendUserMediaAction.description.rstrip()
                    + "\n\n自定义指令：\n"
                    + custom
                )
                logger.debug("已将自定义指令追加到 send_user_media 描述")

    async def on_plugin_unloaded(self) -> None:
        """插件卸载时的清理。"""
        # Service 不持有需要显式释放的资源，无需额外清理
        pass
