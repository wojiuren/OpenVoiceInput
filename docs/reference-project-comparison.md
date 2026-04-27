# 同类项目对照表

更新日期：2026-04-24

这份表是在 [reference-project-shortlist.md](reference-project-shortlist.md) 的基础上继续收的第二层。  
目标不是“挑一个抄”，而是快速回答三件事：

1. 它和我们哪里像？
2. 最值得借鉴什么？
3. 什么地方不建议直接照搬？

如果想先一眼看许可证、本地 API、插件和适配场景，请配合 [reference-project-cheatsheet.md](reference-project-cheatsheet.md) 一起看。
如果想直接看“那我们自己到底怎么做”，请继续看 [our-reference-conclusions.md](our-reference-conclusions.md)。

## 对照表

| 项目 | 和我们哪里像 | 最值得借鉴什么 | 不建议直接照搬什么 |
| --- | --- | --- | --- |
| [TypeWhisper for Windows](https://github.com/TypeWhisper/typewhisper-win) | 都是桌面语音输入工具，都有热键听写、文件转录、本地模型/云模型共存、后处理和本地 API 的方向。 | 本地 HTTP API、profile 机制、欢迎向导、插件市场、本地/云混合架构。 | 功能面已经很宽，插件市场、欢迎向导、统计面板这类整套产品化能力现在不该一口气全搬过来。 |
| [OpenWhispr](https://github.com/OpenWhispr/openwhispr) | 都在做“按热键说话，文字进光标”，也都同时关注本地模型、云模型和后续 API 接入。 | “语音 -> 文本 -> 笔记/动作”的主线很完整；Public API + MCP 也很适合给我们后面扩展留接口。 | 它已经明显扩成了完整桌面工作台，带 meeting transcription、notes、AI agent；我们现在不该被它带着越做越大。 |
| [Handy](https://github.com/cjpais/handy) | 都强调本地优先、离线、可改、热键说话后直接进输入框。 | 结构收敛、可 fork、好改；“隐私优先但体验不笨”的产品取向很适合我们。 | 它在“快速记录 / 关键词路由 / API 后处理”这类中文效率工作流上给的参考有限，不能当完整产品蓝图。 |
| [faster-whisper-dictation](https://github.com/bhargavchippada/faster-whisper-dictation) | 都是热键 dictation，都有 VAD、自动输入、可本地运行；而且它非常贴近我们后面“客户端 + 服务端”分离的想法。 | WebSocket + OpenAI 兼容 REST 双接口、本地 fallback、远程 server 模式、客户端/服务端边界。 | 它更像架构样板，不像成熟桌面产品；直接照搬 UI 或交互价值不高。 |
| [whisper-key-local](https://github.com/PinW/whisper-key-local) | 都是 Windows 本地热键听写路线。 | Auto-paste、auto-send、VAD 预检查、热键动作拆分。 | 更适合参考输入手感，不适合当整体产品架构模板。 |
| [whisper-type](https://github.com/TryoTrix/whisper-type) | 都关注 Windows 听写、热键触发、录音状态反馈。 | tray、overlay、history、spoken punctuation 这类手感增强点。 | 项目成熟度和体量还不够稳，更适合作为点子池，不适合直接做主参考。 |
| [OmniDictate](https://github.com/gurjar1/OmniDictate) | 都是 Windows GUI 听写工具，都在处理 VAD、PTT、typing delay 这类交互细节。 | GUI 设置项怎么收口得更直接，尤其是 VAD / PTT / 文本注入延迟这些可见参数。 | 许可证是 CC BY-NC 4.0，更适合当体验参考，不适合往后做更广的代码复用设想。 |
| [Whispering Tiger](https://github.com/Sharrnah/whispering) | 都涉及实时语音转文字和输出，但它更偏直播字幕/翻译/叠层。 | overlay、实时输出、流式接口、OSC/WebSocket 这类实时场景能力。 | 不属于我们当前的核心主线；现在把精力投入实时字幕和直播生态，会把 MVP 拖偏。 |
| [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) | 都在考虑小模型、本地模型、中文/方言能力，且我们已经把它列成候选后端。 | 0.6B / 1.7B 两档路线、离线/流式统一、中文/方言覆盖。 | 它是模型/后端路线，不是桌面产品参考；不能拿它来回答“我们的 GUI 和用户流程该长什么样”。 |
| [Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR) / [FunASR](https://github.com/modelscope/FunASR) | 都跟中文语音识别、口音和方言能力直接相关。 | 方言和口音能力、VAD / 标点 / 工具链完整度，对中文专项很关键。 | 更适合当方言专项后端，不适合现在直接替换我们的桌面产品主线。 |

## 先拿哪几条做下一阶段参考

### 第一优先级

1. TypeWhisper for Windows  
2. OpenWhispr  
3. faster-whisper-dictation  

原因很简单：

- `TypeWhisper` 最像成熟产品。
- `OpenWhispr` 最像“语音输入继续长成效率工作流”的路线。
- `faster-whisper-dictation` 最像“客户端/服务端拆分”的架构样板。

### 第二优先级

1. Handy  
2. whisper-key-local  
3. whisper-type  

这一组更适合拿来纠偏：

- 别把产品做得过重。
- 别把热键输入手感做笨。
- 别忽视 tray / overlay / 历史记录这类日常使用体验。

### 第三优先级

1. Qwen3-ASR  
2. Fun-ASR / FunASR  
3. Whispering Tiger  

这一组更像专项路线：

- Qwen3-ASR / FunASR：决定后端和模型方向。
- Whispering Tiger：只有当我们真的想走实时字幕/叠层输出时才该重看。

## 我对当前项目的取舍建议

如果只看接下来最该做的事情，我会这么建议：

1. 产品交互优先参考 `TypeWhisper` 和 `Handy`。  
   一个给“成熟产品感”，一个给“别把复杂度做炸”。

2. 工作流扩展优先参考 `OpenWhispr`。  
   尤其是“语音 -> 快速记录 / 动作 / API”的延展方向。

3. 架构拆分优先参考 `faster-whisper-dictation`。  
   这条线跟“7840HS 客户端 + 4090 服务端”最对口。

4. 模型路线继续盯 `Qwen3-ASR` 和 `FunASR`。  
   这两条影响的是“中文、方言、小模型、后端替换”，不是当前 GUI。

5. GUI 微文案继续降级。  
   现在更值钱的是把产品边界、参考路线和后续架构决定清楚。

## 按 7840HS / 4090 重新分档

这一版更贴近我们自己的实际使用场景：

- `7840HS`：日常主力机，要求轻、稳、低门槛、别太吃资源。
- `4090`：后续服务端，允许更复杂的模型、更重的后端和更完整的流式接口。

### 一档：7840HS 单机产品参考

这一档回答的是：“如果只靠迷你主机单机跑，我们应该把产品做成什么样？”

1. **TypeWhisper for Windows**
   - 最适合借产品骨架。
   - 原因：Windows 听写、文件转录、本地/云混合、本地 API，都已经很完整。
   - 我们该学：产品边界、设置向导、profile、本地 API。

2. **Handy**
   - 最适合借收敛感。
   - 原因：它提醒我们，离线工具可以好用，但不一定要越做越重。
   - 我们该学：结构清楚、可改、少包袱。

3. **whisper-key-local**
   - 最适合借输入手感。
   - 原因：热键、自动发送、VAD 预检查都很贴近“日常打字替代”。
   - 我们该学：热键录音的启动/结束手感。

4. **whisper-type / OmniDictate**
   - 作为第二层 GUI 体验参考。
   - 我们该学：tray、overlay、history、PTT/VAD 这些细节项怎么摆。

### 二档：4090 服务端 / 客户端-服务端架构参考

这一档回答的是：“等以后把重模型扔到 4090 上时，我们该怎么拆边界？”

1. **faster-whisper-dictation**
   - 这是最直接的架构参考。
   - 原因：它明确区分本地模式和 server 模式，还同时给了 WebSocket 和 OpenAI 兼容 REST。
   - 我们该学：客户端/服务端边界、本地 fallback、远程转录接口。

2. **TypeWhisper for Windows**
   - 这是第二好的架构参考。
   - 原因：它已经有本地 HTTP API，也有插件和 profile 思路。
   - 我们该学：如果后面真拆客户端/服务端，客户端这一侧该怎么保留“可接不同后端”的产品层接口。

3. **OpenWhispr**
   - 更适合借“服务端化之后怎么继续长成功能平台”。
   - 原因：它已经把 API、MCP、actions、notes 串起来了。
   - 我们该学：远程能力不只是“跑得更快”，还可以接成动作流和笔记流。

### 三档：模型 / 后端专项参考

这一档回答的是：“如果产品壳子不变，底层模型应该盯谁？”

1. **Qwen3-ASR**
   - 更适合作为中文/方言/小模型主候选。
   - 适用方向：7840HS 单机实验、4090 服务端增强，两边都能看。

2. **Fun-ASR / FunASR**
   - 更适合作为方言专项候选。
   - 适用方向：如果后面真的把“方言支持”做成卖点，它比很多桌面产品参考都重要。

3. **Whispering Tiger**
   - 不作为当前主后端候选，但保留为“实时字幕/流式输出”专项参考。

## 下一阶段优先级建议

如果只看我们接下来该投入的顺序，我会这么排：

### P1：先学产品壳子

1. TypeWhisper for Windows  
2. Handy  
3. whisper-key-local

原因：

- 先把“7840HS 单机真的好不好用”做对。
- 热键输入、文件转录、快速记录、设置体验，要先在单机上站稳。

### P2：再学服务端边界

1. faster-whisper-dictation  
2. TypeWhisper for Windows  
3. OpenWhispr

原因：

- 客户端/服务端分离现在还是下一阶段，不是眼前 MVP。
- 但接口边界、fallback 和 OpenAI 兼容接口，已经值得先设计时留口子。

### P3：持续盯模型路线

1. Qwen3-ASR  
2. Fun-ASR / FunASR

原因：

- 模型路线会影响识别质量和方言支持。
- 但它不该反过来拖着产品壳子无限改来改去。

## 来源

本页基于 2026-04-24 查看的项目官方 GitHub 仓库首页 / README 做第二轮整理，优先使用官方仓库而不是二手介绍页。首批主要来源：

- [TypeWhisper/typewhisper-win](https://github.com/TypeWhisper/typewhisper-win)
- [OpenWhispr/openwhispr](https://github.com/OpenWhispr/openwhispr)
- [cjpais/handy](https://github.com/cjpais/handy)
- [bhargavchippada/faster-whisper-dictation](https://github.com/bhargavchippada/faster-whisper-dictation)
- [PinW/whisper-key-local](https://github.com/PinW/whisper-key-local)
- [TryoTrix/whisper-type](https://github.com/TryoTrix/whisper-type)
- [gurjar1/OmniDictate](https://github.com/gurjar1/OmniDictate)
- [Sharrnah/whispering](https://github.com/Sharrnah/whispering)
- [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)
- [FunAudioLLM/Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR)
- [modelscope/FunASR](https://github.com/modelscope/FunASR)
