# media_retriever

Neo-MoFox 插件（作者：言柒）：从聊天历史检索并发送用户发过的媒体，自动下载管理文件，提供文件读取能力。

## 功能

- **媒体检索与重发**：通过聊天记录媒体占位符中的 `media_id` 精确发送用户发过的图片、表情包、语音、视频或文件。
- **文件自动下载**：监听消息事件，自动下载聊天中的文件到插件存储目录，支持群文件与私聊文件。
- **文件管理**：按聊天流分类存储，LRU 清理超限文件，`list_files` 列出已下载文件。
- **文件读取**：`read_file` 安全读取已下载的文本类文件（扩展名白名单、路径穿越防护、分页读取）。

## 组件

| 组件类型 | 组件名 | 说明 |
|---------|--------|------|
| service | `media_retriever` | 媒体检索、文件下载/管理/LRU 清理、文件读取、媒体发送 |
| event_handler | `file_message_handler` | 监听消息事件，自动下载 file 类型媒体 |
| action | `send_user_media` | LLM Action，通过 media_id 精确发送历史媒体 |
| tool | `list_files` | 列出当前聊天流已下载的文件 |
| tool | `read_file` | 读取当前聊天流已下载文件的内容 |

## 安装

将本插件目录放入 Neo-MoFox 的 `plugins/` 目录，然后启用插件：

```bash
uv sync
uv run main.py
```

插件依赖的 API 版本要求见 `manifest.json` 的 `api_version`。

## 配置

配置项位于 `config/plugins/media_retriever/config.toml`，首次运行后自动生成。主要配置节：

### `[file]` 文件下载与管理

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | `true` | 是否启用文件自动下载 |
| `data_dir` | `data/media_retriever/files` | 文件存储根目录 |
| `max_file_size_mb` | `10.0` | 单个文件最大大小（MB），超过不下载 |
| `max_total_size_mb` | `500.0` | 总容量上限（MB），超过 LRU 清理 |
| `download_timeout` | `60.0` | 下载超时秒数 |
| `adapter_signature` | 见下 | 用于调用文件下载 API 的适配器签名 |
| `wsl_mode` | `false` | 是否将文件路径转换为 WSL/容器挂载形式 |

> `adapter_signature` 需按实际部署环境填写为对应适配器的组件签名（格式 `plugin_name:adapter:adapter_name`），不同部署使用的适配器可能不同，请勿沿用默认值。

### `[read]` 文件读取安全限制

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `allowed_extensions` | 常见文本扩展名 | 允许读取的文件扩展名（逗号分隔） |

### `[prompt]` 自定义提示词

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `custom_instructions` | `""` | 追加到 action/tool 描述的自定义指令 |

## 使用

### 发送历史媒体（LLM Action）

AI 可通过 `send_user_media` Action 指定 `media_id` 与 `media_type`：

- `image` / `emoji` / `voice` / `video`：`media_id` 从聊天记录媒体占位符括号内提取，如 `[图片(a1b2c3...)]` 中的 `a1b2c3...`。
- `file`：`media_id` 可以是已下载的文件名（通过 `list_files` 查看），也可以是本机任意文件的绝对路径。

### 命令 / 工具

- `list_files`：列出当前聊天流中已下载的文件（LLM Tool）。
- `read_file`：读取已下载文件内容，支持 `offset` / `max_lines` 分页（LLM Tool）。

## 开发

代码检查：

```bash
uv run ruff check .
```
