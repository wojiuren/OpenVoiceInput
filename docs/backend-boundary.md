# 后端边界说明

这页用来防止后面接新模型、4090 服务端、外部 API 时把主链路搅乱。

最重要的一句话：

> ASR 后端负责“音频 -> 原始文字”，API 文本后处理负责“文字 -> 更干净的文字”，GUI 和 CLI 只负责编排，不直接知道具体模型怎么跑。

## 当前主链路

```text
麦克风 / 音频文件
  -> 录音或文件入口
  -> SelectionRequest 选择任务类型和优先级
  -> ModelProfile 选出模型和 backend id
  -> AsrBackend.transcribe_file()
  -> TranscriptionResult(raw text)
  -> 可选 API 文本后处理
  -> 输出到光标 / 剪贴板 / txt / srt / 快速记录
```

当前已经比较清楚的部分：

- `TranscriptionJob`：一次转写请求，包含音频路径、任务类型、语言、metadata。
- `TranscriptionResult`：一次 ASR 结果，包含文字、模型、语言、分段、metadata。
- `AsrBackend`：ASR 后端协议，只需要实现 `is_available()` 和 `transcribe_file()`。
- `BackendRegistry`：根据 `ModelProfile.backend` 找到具体后端。
- `ApiProviderConfig` / `call_chat_completion()`：只处理文本，不处理音频。

## 三类后端的职责

| 类型 | 输入 | 输出 | 负责什么 | 不负责什么 |
|---|---|---|---|---|
| 本地 ASR | 本机音频文件 | `TranscriptionResult` | 调本机模型，把音频转文字 | 不做润色排版，不直接粘贴到窗口 |
| 远程 ASR | 本机音频文件或上传后的音频引用 | `TranscriptionResult` | 调 4090 服务端或云端 ASR，把音频转文字 | 不复用文本 API 配置，不直接管 GUI |
| API 文本后处理 | 原始识别文字 + 可选上下文 | 整理后的文字 | 标点、润色、去口语、修误识别、提取待办 | 不接收音频，不选择 ASR 模型 |

这里最容易混的是“远程 ASR”和“API 文本后处理”。

- 远程 ASR 是识别模型：它看音频。
- API 文本后处理是文字助手：它只看文字。

哪怕它们都走 HTTP，也不能放进同一个配置桶里。

## GUI 和 CLI 应该知道什么

GUI / CLI 可以知道：

- 当前任务是 `dictation`、`file_transcription` 还是 `long_form`。
- 当前是否启用 API 文本后处理。
- 当前输出方式是自动粘贴、只复制、模拟输入、保存文件或快速记录。
- 当前推荐模型名和后端名，用来展示状态。

GUI / CLI 不应该知道：

- SenseVoice 需要哪些 ONNX 文件。
- Qwen3-ASR-GGUF 是 subprocess、DirectML 还是 Vulkan。
- 4090 服务端的内部模型路径。
- 某个后端用哪个 Python 包、哪个二进制、哪个推理参数。

这些应该藏在具体 `AsrBackend` 实现里。

## 本地 ASR 边界

本地 ASR 后端要满足同一个合约：

```text
TranscriptionJob(audio path, task, language)
  -> TranscriptionResult(text, model_id, language, segments, metadata)
```

现有例子：

- `SherpaOnnxSenseVoiceBackend`
- backend id: `sherpa-onnx`
- 模型：`sensevoice-small-onnx-int8`

后续 Qwen3-ASR-GGUF 如果接入主项目，建议先做：

- backend id: `qwen3-asr-gguf`
- 适配方式：subprocess adapter
- 输入：音频路径
- 输出：解析 stdout 或输出文件，转成 `TranscriptionResult`

不要让 GUI 直接调用 `transcribe.exe`。

## 远程 ASR 边界

4090 服务端应该被当作“远程 ASR 后端”，不是文本 API 后处理。

建议未来接口形态：

```text
RemoteAsrBackend.transcribe_file(job, profile)
  -> 上传音频或传本地可访问路径
  -> 等服务端返回 JSON
  -> 转成 TranscriptionResult
```

服务端返回的最小 JSON 建议：

```json
{
  "text": "识别结果",
  "model_id": "qwen3-asr-1.7b-q4",
  "language": "zh",
  "segments": [],
  "metadata": {
    "backend": "remote-asr",
    "server": "4090-desktop",
    "duration_s": "12.345"
  }
}
```

客户端收到后仍然走同一条后续链路：

```text
API 文本后处理 -> 输出 -> 快速记录 -> 日志
```

这样 7840HS 迷你主机只需要知道“有一个远程 ASR 后端可用”，不需要知道 4090 里具体怎么推理。

## API 文本后处理边界

API 文本后处理永远排在 ASR 后面。

它输入的是文字：

- 原始 ASR 文本
- 最近几条文字上下文
- 术语表
- 当前 preset 或自定义 system prompt

它输出的是文字：

- 清理后的正文
- 正式改写文本
- 待办列表
- 翻译结果

它不应该：

- 读取音频文件
- 选择 ASR 模型
- 影响 `SelectionRequest`
- 替代 `AsrBackend`

当前快速记录有一个重要规则：

```text
关键词路由用原始 ASR 文本判断；
保存正文可以使用 API 后处理后的文本。
```

这是对的，应该保留。

原因很简单：关键词通常是用户刚说出来的口令，API 后处理可能会删口头词、改措辞，如果用整理后的文本匹配关键词，反而容易不稳定。

## 任务路由边界

任务路由只决定“选什么 ASR 模型 / 后端”。

当前任务：

- `dictation`：短句听写，优先低延迟。
- `file_transcription`：文件转录，优先平衡速度和准确率。
- `long_form`：长音频，优先准确率和后台处理。

任务路由不应该决定：

- 是否自动粘贴。
- 是否保存快速记录。
- 是否调用 API 文本后处理。

这些是输出层和后处理层的事情。

## 后续接入新后端的顺序

以后接入新模型时，按这个顺序做：

1. 先登记 `ModelProfile`，写清楚 backend id、任务适配、资源要求、是否实验。
2. 再实现一个 `AsrBackend` adapter。
3. 注册到 `BackendRegistry`。
4. 用公开样例音频跑 `doctor` 或 `benchmark`。
5. 再决定是否暴露到 GUI 状态或默认推荐。

不要反过来从 GUI 加按钮开始。

## 当前不做什么

V1 当前不做：

- 不把文本 API provider 当作 ASR provider。
- 不让 GUI 直接知道某个模型的命令行参数。
- 不做多后端同时转写投票。
- 不做实时流式远程协议。
- 不默认把 Qwen3-ASR 或 FunASR 切进主链路。

这些都可以以后做，但要等边界稳定以后再说。

## 下一步建议

远程 ASR adapter 的最小配置骨架、`backend="remote-asr"` 的实验 `ModelProfile`、`RemoteAsrBackend` 空壳、请求 / 响应 JSON 纯函数、以及 fake transport 边界测试都已经落到代码里。当前这个后端能构造 request payload、解析成功响应、解析错误响应，也能通过测试假装调用服务端，但默认运行仍然不发真实 HTTP 请求。

下一步也不是直接写 4090 服务端，而是先把远程 ASR 配置入口补到 CLI：

- 能查看当前 `remote_asr` 是否启用、当前 profile、base URL、key 环境变量名。
- 能设置启用开关、base URL、key 环境变量名、超时和 fallback 模型。
- CLI 只读写配置，不主动测试远程服务。
- 继续不自动启动真实麦克风录音。

这样以后真正接 4090 时，就不是临时拼一条命令，而是把它放进同一条 ASR 后端链路。
