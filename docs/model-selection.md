# 模型选择策略

## 核心原则

模型选择不是简单的“越大越好”。语音输入工具最重要的是低延迟、稳定、可恢复；文件转录和长音频才更需要大模型、时间戳和说话人信息。

因此第一版把任务分成三类：

- `dictation`：实时/准实时语音输入，优先低延迟。
- `file_transcription`：音视频文件转文字，优先稳定输出和字幕能力。
- `long_form`：长会议、长讲座，优先长上下文、时间戳、说话人信息。

## 默认推荐

### 当前硬件假设

当前项目的模型推荐优先服务两台机器：

- 日常主力机：AMD Ryzen 7 7840HS 迷你主机。
- 后续服务端：RTX 4090 台式机。

7840HS 机器代表“普遍适用性”：模型不能太重，安装不能太绕，热键输入必须低延迟。4090 机器代表“服务端增强”：可以跑更大模型，但不应该影响日常客户端的轻量体验。

### CPU-only

默认选择小模型：

- 中文/中英输入：`sensevoice-small-onnx-int8`
- 中文低配备用：`paraformer-zh-onnx`
- 需要跨平台备用：`whisper-small-ctranslate2`

原因：CPU-only 场景最怕延迟不可控。小模型先保证输入体验，不让用户等太久。

### NVIDIA GPU

自动检测最大显存：

- 4GB 以下：仍使用 CPU 小模型或轻量 GPU 后端。
- 4GB 到 8GB：可选择 `qwen3-asr-0.6b` 或 `funasr-nano-gguf`。
- 8GB 以上：优先 `qwen3-asr-1.7b-q4` 作为高准确率语音输入模型。
- 16GB/24GB 以上且任务是长音频：考虑 `vibevoice-asr-hf-8b`。

### 7840HS 候选路线

7840HS 上不要一开始下载一堆模型。先把候选列出来，再按 `py -m local_voice_input benchmark` 做小样本测速。

当前优先顺序：

1. `sensevoice-small-onnx-int8`：已安装，作为真实基线。
2. `qwen3-asr-0.6b`：下一步重点候选，采用 HaujetZhao/Qwen3-ASR-GGUF 的 ONNX Encoder + GGUF Decoder 路线，重点测试 DirectML / Vulkan / CPU。
3. `paraformer-zh-onnx`：中文轻量备用。
4. `whisper-small-ctranslate2`：跨语言备用。

在 Qwen3-ASR-GGUF 0.6B 没有完成 7840HS 实测前，不把它设为默认模型。

### 4090 服务端路线

4090 不用于证明普通用户默认体验，而用于后续服务端能力：

- `qwen3-asr-1.7b-q4`：高准确率文件转写和可能的远程 ASR 服务。
- `vibevoice-asr-hf-8b`：长音频、会议、说话人结构化转写。

客户端/服务端分离后，7840HS 客户端负责热键、录音、粘贴、快速记录；4090 服务端负责重模型推理。

### 方言/API 特殊项目

Fun-ASR 1.5 先作为特殊项目 profile 记录为：

- `fun-asr-1.5-dialect-api`
- 后端：`aliyun-bailian-api`
- 目标：中文普通话和方言/地方口音转写
- 定位：文件转写、长音频、方言用户的专项路线

这个 profile 目前不是本地默认模型。原因很简单：截至本次整理，公开线索更偏向阿里云百炼 API 和魔搭体验入口，暂时没有像 SenseVoice ONNX 那样已经接进本项目的本地模型目录。它适合下一步做成“API ASR provider”，也就是把音频发到配置好的 provider，拿回转写文本。

已知宣传能力包括：30 种语言、汉语七大方言、20 多种地方口音，方言识别 CER 相对下降 56.2%。这些指标需要以后用用户真实方言样例或公开测试集再验证，不能直接当成本项目实测结果。

### 英文流式实验模型

NVIDIA Nemotron Speech Streaming 0.6B 先作为英文实验模型记录为：

- `nemotron-speech-streaming-en-0.6b-foundry-local`
- 后端：`foundry-local`
- 目标：英文流式 ASR
- Foundry Local catalog 里看到的 CPU ONNX 变体约 697 MiB

它不是中文模型，不应该替换当前中文默认模型。它的价值在于“流式”：模型卡描述它使用 5.6 秒上下文窗口，每次处理 0.56 秒音频块，可以低延迟连续识别英文语音。

### 手动选择

用户手动选择永远优先。系统只做两件事：

- 检查资源是否可能不足。
- 给出警告和降级建议。

## 为什么不默认用 VibeVoice-ASR

VibeVoice-ASR-HF 是 MIT 许可，能力很强，适合长音频、时间戳、说话人结构化转录；但它是 8B 级模型，BF16 权重，作为“每句话都要立刻上屏”的默认模型并不理想。

更好的定位是：

- `long_form` 默认候选。
- 高显存 NVIDIA 用户的高级选项。
- 文件转录/会议整理功能的增强后端。

## 第一版模型矩阵

| 模型 profile | 默认用途 | 推荐硬件 | 备注 |
| --- | --- | --- | --- |
| `sensevoice-small-onnx-int8` | CPU 语音输入 | CPU, 4GB RAM | 低延迟，多语言，适合默认 |
| `paraformer-zh-onnx` | 中文低配备用 | CPU, 4GB RAM | 中文体验成熟 |
| `fun-asr-1.5-dialect-api` | 方言/API 特殊项目 | API provider | 实验项，适合方言转写路线 |
| `nemotron-speech-streaming-en-0.6b-foundry-local` | 英文流式实验 | CPU/Foundry Local | 英文 ASR，约 697 MiB catalog 变体 |
| `whisper-small-ctranslate2` | 兼容备用 | CPU/GPU | 生态成熟，但中文输入未必最优 |
| `funasr-nano-gguf` | 平衡模式 | CPU/GPU | 适合中高配，热词潜力好 |
| `qwen3-asr-0.6b` | 7840HS 重点候选 | 7840HS / DirectML / Vulkan / CPU | 候选，不下载前不设默认 |
| `qwen3-asr-1.7b-q4` | 4090 服务端候选 | NVIDIA 8GB+ | 高准确率，先不作为迷你主机默认 |
| `vibevoice-asr-hf-8b` | 长音频/会议 | NVIDIA 16GB+ | 长上下文、时间戳、说话人信息 |

## 测速先于下载

模型选择结论必须来自本机测试，而不是宣传指标。

当前规则：

- 不下载所有候选模型。
- 先测已安装的 `sensevoice-small-onnx-int8`。
- 只有当测试计划明确后，再下载 `qwen3-asr-0.6b`。
- 先测 0.6B，不先下载 1.7B。
- 4090 服务端模型等客户端体验稳定后再测。

测速结果记录在：

- `docs/model-benchmark-results.md`

## 许可证注意

不同模型和转换版本的许可不同。项目需要为每个模型 profile 记录：

- 模型来源。
- 代码许可证。
- 权重许可证。
- 是否允许商用。
- 是否需要额外署名或使用限制。

第一版不要把模型权重直接打包进程序，建议让用户按需下载，并在 UI 中显示来源和许可证链接。
