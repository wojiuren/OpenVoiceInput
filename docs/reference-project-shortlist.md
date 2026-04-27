# 同类项目候选清单

更新日期：2026-04-24

这份清单不是“谁最火”的排行榜，而是给 OpenVoiceInput-MVP 找可借鉴路线的备选池。优先看和我们真正同路的项目：本地语音输入、热键听写、文件转录、可替换模型、后续客户端/服务端分离。

如果想直接看横向取舍，请继续看 [reference-project-comparison.md](reference-project-comparison.md)。  
如果想先扫许可证、本地 API、插件/扩展和适配场景，请看 [reference-project-cheatsheet.md](reference-project-cheatsheet.md)。
如果想直接看“我们自己的 V1 结论”，请看 [our-reference-conclusions.md](our-reference-conclusions.md)。

## 先看这 4 个

### 1. TypeWhisper for Windows

- 定位：功能最完整、最像成熟桌面产品的 Windows 语音输入项目。
- 官方仓库：[TypeWhisper/typewhisper-win](https://github.com/TypeWhisper/typewhisper-win)
- 我为什么把它放第一：
  - 系统级热键听写。
  - 本地模型和云模型都能接。
  - 支持拖拽文件转录、字幕导出。
  - 有本地 HTTP API，天然适合外部自动化和后续拆客户端/服务端。
  - 有欢迎向导、扩展/插件入口、按场景切换 profile 的设计方向。
- 值得我们重点借鉴：
  - “本地默认 + 云可选”的产品结构。
  - 本地 HTTP API 这条路。
  - 配置向导和首次上手体验。
  - 文件转录和系统级听写共存。
- 不建议直接照搬：
  - 体量已经明显偏产品化，功能面很宽；我们现在还在 MVP，不该一口气复制整套复杂度。

### 2. OpenWhispr

- 定位：从“语音输入”进一步延伸到“笔记、动作、API”的桌面产品。
- 官方仓库：[OpenWhispr/openwhispr](https://github.com/OpenWhispr/openwhispr)
- 为什么重要：
  - 热键说话、文本进光标，这条主链路和我们很像。
  - 同时支持本地和云端转录。
  - 已经把 notes / actions / API / MCP 做成产品的一部分。
- 值得我们重点借鉴：
  - “语音 -> 文本 -> 笔记/动作”的产品叙事。
  - 如果以后要把“快速记录”做成更强功能，它是很好的参考。
  - API / MCP 这类外部接入能力怎么做成产品层能力。
- 不建议直接照搬：
  - 它的目标比我们大很多，已经不是单纯的 dictation 工具了；现在拿来做“方向参考”比拿来做“功能 checklist”更合适。

### 3. Handy

- 定位：强调真正离线、真正开源、真正可 fork 的跨平台听写工具。
- 官方仓库：[cjpais/handy](https://github.com/cjpais/handy)
- 为什么重要：
  - 它的自我定位非常清楚：不是追求所有功能都最强，而是追求最开放、最容易改。
  - 这和我们现在“边做边学、自己能接着改”的需求很贴近。
- 值得我们重点借鉴：
  - 尽量保持结构清楚、容易 fork、容易改。
  - “一个工具只做好一件事”的收敛感。
  - 隐藏启动、无托盘等朴素但实用的桌面参数化思路。
- 不建议直接照搬：
  - 它更像“干净的基础设施型工具”；如果我们要做中文快速记录、关键词路由，还是需要更贴近中文场景的产品层设计。

### 4. faster-whisper-dictation

- 定位：在“本地 dictation”之外，明确给了“本地/服务端双模 + WebSocket/REST”的架构路线。
- 官方仓库：[bhargavchippada/faster-whisper-dictation](https://github.com/bhargavchippada/faster-whisper-dictation)
- 为什么重要：
  - 它和我们后面想做的“7840HS 客户端 + 4090 服务端”非常相关。
  - 明确区分了本地引擎和服务端引擎。
  - 服务端同时支持 WebSocket 流式和 OpenAI 兼容 REST。
- 值得我们重点借鉴：
  - 客户端/服务端分离的接口边界。
  - 本地 fallback + 远程高性能服务端这条路线。
  - 用 OpenAI 兼容接口承接音频转录服务。
- 不建议直接照搬：
  - 它更偏架构和工程方案，不是轻量桌面产品；直接照搬 UI/交互意义不大。

## 第二梯队：专项功能参考

### 5. whisper-key-local

- 定位：偏轻量的 Windows 本地热键听写工具。
- 官方仓库：[PinW/whisper-key-local](https://github.com/PinW/whisper-key-local)
- 适合参考的点：
  - Auto-paste / auto-send。
  - VAD 预检查，减少空白误触发。
  - 热键动作拆分得比较细。
- 对我们最有价值的地方：
  - 如果后面要继续打磨热键录音手感，它值得细看。

### 6. whisper-type

- 定位：Windows 本地听写工具，强调热键、托盘、历史、覆盖层体验。
- 官方仓库：[TryoTrix/whisper-type](https://github.com/TryoTrix/whisper-type)
- 适合参考的点：
  - 托盘 + 历史日志 + overlay 反馈。
  - 录音状态的视觉反馈。
  - Spoken punctuation 这类提高输入手感的小功能。
- 备注：
  - 目前仓库体量和社区成熟度还比较早，但产品感觉值得参考。

### 7. OmniDictate

- 定位：Windows 本地 GUI dictation。
- 官方仓库：[gurjar1/OmniDictate](https://github.com/gurjar1/OmniDictate)
- 适合参考的点：
  - 更直接的 Windows GUI 听写面板。
  - VAD / PTT / typing delay / filter words 这些设置项。
- 备注：
  - 许可证是 CC BY-NC 4.0，更适合当产品体验参考，不适合当以后可能要广泛复用的代码来源。

### 8. Whispering Tiger

- 定位：偏实时字幕、翻译、直播/VR/叠层输出。
- 官方仓库：[Sharrnah/whispering](https://github.com/Sharrnah/whispering)
- 适合参考的点：
  - WebSocket / OSC / overlay 这类实时输出能力。
  - 如果以后要做实时字幕、悬浮输出、直播字幕，这条线很值得看。
- 备注：
  - 不属于我们当前最核心的“语音输入到光标”主线。

## 模型/后端专项参考

### 9. Qwen3-ASR

- 官方仓库：[QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
- 为什么留在清单里：
  - 官方明确支持 52 种语言和方言。
  - 0.6B / 1.7B 两档很适合我们继续做模型路线比较。
  - 同时支持离线 / 流式统一推理。
- 我们怎么用它：
  - 更适合当“后端/模型候选”，不是直接当桌面产品参考。

### 10. Fun-ASR / FunASR

- 官方仓库：
  - [FunAudioLLM/Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR)
  - [modelscope/FunASR](https://github.com/modelscope/FunASR)
- 为什么留在清单里：
  - 中文方言和口音覆盖很强。
  - 工具链不只 ASR，还包含 VAD、标点等能力。
  - 对我们后面“方言专项路线”很关键。
- 我们怎么用它：
  - 更像“中文/方言特殊项目”后端候选，不是当前 GUI/热键体验的直接参考物。

## 我给你的初步分档

### A 档：最值得继续深挖

1. TypeWhisper for Windows
2. OpenWhispr
3. Handy
4. faster-whisper-dictation

这 4 个基本覆盖了我们现在最关心的四条线：

- 桌面产品完成度
- 语音输入 + 笔记/动作扩展
- 开源可 fork 的工程取向
- 客户端/服务端分离

### B 档：功能点借鉴

1. whisper-key-local
2. whisper-type
3. OmniDictate
4. Whispering Tiger

这批更适合拿来拆某个具体点：

- 热键
- VAD
- 自动发送
- overlay
- tray
- 实时字幕/流式输出

### C 档：模型和后端路线

1. Qwen3-ASR
2. Fun-ASR / FunASR

这批不直接回答“产品怎么做”，但很影响“我们底层该押哪条模型路线”。

## 对我们项目的直接启发

如果只说对 OpenVoiceInput-MVP 最实在的下一步，我会这样排：

1. 继续把产品主线收紧在“热键输入 + 快速记录 + 文件转录 + 可切换后端”。
2. 产品层优先借鉴 TypeWhisper / OpenWhispr / Handy。
3. 架构层优先借鉴 faster-whisper-dictation。
4. 模型层继续跟 Qwen3-ASR 和 FunASR。
5. GUI 小文案微调先降级，不要继续无限抛光。

## 来源说明

本清单基于 2026-04-24 在线查看的官方 GitHub 仓库首页 / README / 发布信息做的第一轮筛选，优先使用项目官方仓库而不是二手介绍页。后续调研可以继续补：

- 更细的功能对照表
- 各项目许可证差异
- 是否有本地 API
- 是否支持插件
- 是否适合 7840HS 单机
- 是否适合 4090 服务端拆分
