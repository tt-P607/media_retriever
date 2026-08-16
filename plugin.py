"""media_retriever 插件入口。

注册 6 个组件：
- MediaRetrieverService（Service）
- FileMessageHandler（EventHandler）
- SendUserMediaAction（Action）
- ListFilesTool（Tool）
- ReadFileTool（Tool）
- DownloadFileTool（Tool）
"""

from __future__ import annotations


from src.app.plugin_system.base import BasePlugin, register_plugin
from src.kernel.logger import get_logger

from .action import SendUserMediaAction
from .config import MediaRetrieverConfig
from .file_handler import FileMessageHandler
from .service import MediaRetrieverService
from .tool import DownloadFileTool, ListFilesTool, ReadFileTool

logger = get_logger(__name__)


@register_plugin
class MediaRetrieverPlugin(BasePlugin):
    """media_retriever 插件。

    从聊天历史检索并发送用户发过的媒体，
    自动下载管理文件，提供文件读取能力。
    """

    plugin_name: str = "media_retriever"

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
            DownloadFileTool,
        ]

    async def on_plugin_loaded(self) -> None:
        """插件加载完成后：注入动态阈值与自定义指令到组件描述。"""
        if not isinstance(self.config, MediaRetrieverConfig):
            return

        # 注入当前自动下载阈值到 DownloadFileTool 描述，使 bot 能判断文件是否
        # 已被自动下载（≤阈值自动下，无需调用；>阈值未自动下，才需调用）。
        threshold = self.config.file.max_file_size_mb
        DownloadFileTool.description = (
            DownloadFileTool.description.rstrip()
            + (
                f"\n\n【当前自动下载阈值】{threshold:g}MB："
                f"≤{threshold:g}MB 的文件已被自动下载，直接用 read_file / "
                f"send_user_media 处理即可，无需调用本工具；"
                f">{threshold:g}MB 的文件未自动下载，才调用本工具强制下载。"
            )
        )

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
