"""media_retriever 插件配置定义。"""

from src.app.plugin_system.base import BaseConfig, Field, SectionBase, config_section


class MediaRetrieverConfig(BaseConfig):
    """media_retriever 插件配置。

    包含三个配置节：
    - file: 文件下载与管理
    - read: 文件读取安全限制
    - prompt: 自定义提示词
    """

    name = "config"
    description = "media_retriever 插件配置"

    @config_section("file")
    class FileSection(SectionBase):
        """文件下载与管理配置。"""

        enabled: bool = Field(
            default=True,
            description="是否启用文件自动下载",
        )
        data_dir: str = Field(
            default="data/media_retriever/files",
            description="文件存储根目录",
        )
        max_file_size_mb: float = Field(
            default=10.0,
            description="单个文件最大大小(MB)，超过不下载",
        )
        max_total_size_mb: float = Field(
            default=500.0,
            description="所有文件总容量上限(MB)，超过LRU清理",
        )
        download_timeout: float = Field(
            default=60.0,
            description="下载超时秒数",
        )
        adapter_signature: str = Field(
            default="",
            description="回退用的适配器签名（留空则自动按消息平台匹配活跃适配器）",
        )
        wsl_mode: bool = Field(
            default=False,
            description="是否将文件路径转换为 WSL/容器挂载形式（如 E:/ → /mnt/e/），用于 Docker 部署的 SnowLuma 客户端",
        )

    @config_section("read")
    class ReadSection(SectionBase):
        """文件读取安全限制配置。"""

        allowed_extensions: str = Field(
            default=".txt,.py,.json,.md,.csv,.log,.xml,.yaml,.yml,.toml,.js,.ts,.html,.css,.ini,.cfg,.sh,.bat,.sql,.go,.rs,.java,.c,.cpp,.h,.hpp",
            description="允许读取的文件扩展名（逗号分隔）",
        )

    @config_section("prompt")
    class PromptSection(SectionBase):
        """自定义提示词配置。"""

        custom_instructions: str = Field(
            default="",
            description="追加到 action/tool 描述的自定义指令",
        )

    file: FileSection = Field(default_factory=FileSection)
    read: ReadSection = Field(default_factory=ReadSection)
    prompt: PromptSection = Field(default_factory=PromptSection)
