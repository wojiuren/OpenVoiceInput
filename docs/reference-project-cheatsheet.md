# 同类项目速查表

更新日期：2026-04-24

这份表给的是“查得快”的版本。  
如果想看完整取舍理由，请配合这两份一起看：

- [reference-project-shortlist.md](reference-project-shortlist.md)
- [reference-project-comparison.md](reference-project-comparison.md)
- [our-reference-conclusions.md](our-reference-conclusions.md)

## 速查表

| 项目 | 许可证 | 本地 API / 外部接口 | 插件 / 扩展 | 更适合 7840HS 单机还是 4090 服务端 | 备注 |
| --- | --- | --- | --- | --- | --- |
| [TypeWhisper for Windows](https://github.com/TypeWhisper/typewhisper-win) | GPL-3.0 | 有本地 HTTP API | 有插件系统和插件市场 | 两边都适合，但更像单机产品壳子 | 最完整，最适合借产品结构 |
| [OpenWhispr](https://github.com/OpenWhispr/openwhispr) | MIT | 有 Public API 和 MCP | README 里未见插件市场；更偏 API / actions 扩展 | 两边都适合，偏“平台化”路线 | 更适合借“语音 -> 笔记 / 动作 / API” |
| [Handy](https://github.com/cjpais/handy) | MIT | README 未强调本地 API | 强调 extensible，但未见插件市场 | 更适合 7840HS 单机 | 很适合拿来提醒我们别把产品做得太重 |
| [faster-whisper-dictation](https://github.com/bhargavchippada/faster-whisper-dictation) | MIT | WebSocket + OpenAI 兼容 REST | 未见插件系统 | 更适合 4090 服务端 / 客户端-服务端拆分 | 最适合借架构边界 |
| [whisper-key-local](https://github.com/PinW/whisper-key-local) | MIT | README 未强调本地 API | 有 voice commands / snippets 级扩展 | 更适合 7840HS 单机 | 更适合借热键输入手感 |
| [whisper-type](https://github.com/TryoTrix/whisper-type) | MIT | README 未强调本地 API | 未见插件系统；有 tray / overlay / history | 更适合高配单机；对 7840HS 参考价值主要在交互 | 偏 Windows + NVIDIA GPU |
| [OmniDictate](https://github.com/gurjar1/OmniDictate) | CC BY-NC 4.0 | README 未强调本地 API | 未见插件系统 | 更适合单机 GUI 体验参考 | 更适合当体验参考，不适合往后做广泛代码复用设想 |
| [Whispering Tiger](https://github.com/Sharrnah/whispering) | MIT | WebSocket / OSC | 有 plugins | 更适合 4090 服务端或实时字幕专项 | 不属于当前主线，但实时输出很值得参考 |
| [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) | Apache-2.0 | 仓库更偏模型与推理工具，不是现成桌面本地 API | 无插件市场；更像模型后端 | 两边都适合，偏后端候选 | 更适合决定模型路线，不适合决定 GUI |
| [Fun-ASR](https://github.com/FunAudioLLM/Fun-ASR) | Apache-2.0 | 仓库更偏模型与工具链 | 无插件市场；更像模型后端 | 两边都适合，偏方言专项 | 更适合中文/方言路线 |
| [FunASR](https://github.com/modelscope/FunASR) | Apache-2.0 | 有离线文件转录服务、实时转录服务文档 | 无插件市场；更像工具包 | 两边都适合，偏后端候选 | 方言、VAD、标点这些配套能力很强 |

## 快速读法

如果你只想一分钟看懂：

- **产品壳子最值得看**：TypeWhisper、Handy
- **工作流扩展最值得看**：OpenWhispr
- **客户端/服务端拆分最值得看**：faster-whisper-dictation
- **热键手感最值得看**：whisper-key-local
- **模型路线最值得盯**：Qwen3-ASR、FunASR

## 对我们项目的直接结论

### 现在最该学谁

1. `TypeWhisper`
2. `Handy`
3. `faster-whisper-dictation`

### 现在先别被谁带偏

1. `OpenWhispr`
   - 很强，但太容易把我们带向“大而全桌面工作台”。

2. `Whispering Tiger`
   - 很酷，但会把主线带去实时字幕/直播/VR。

3. `OmniDictate`
   - GUI 体验有参考价值，但许可证让它更适合看思路，不适合想太多代码复用。

## 来源

本页基于 2026-04-24 查看的各项目官方 GitHub 仓库首页 / README 做整理，优先使用项目官方仓库。已经明确核过的关键信息包括：

- TypeWhisper：GPL-3.0、插件系统、插件市场、本地 HTTP API
- OpenWhispr：MIT、Public API、MCP
- Handy：MIT、离线、extensible
- faster-whisper-dictation：MIT、WebSocket、OpenAI 兼容 REST
- whisper-key-local：MIT、voice commands / snippets
- whisper-type：MIT、tray / overlay / history
- OmniDictate：CC BY-NC 4.0
- Whispering Tiger：MIT、WebSocket / OSC、plugins
- Qwen3-ASR：Apache-2.0
- Fun-ASR / FunASR：Apache-2.0
