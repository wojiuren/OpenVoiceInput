# 新手上手说明

这份文档按“我完全不熟悉工程项目”的角度写。先不用理解所有代码，先把几个动作跑通。

## 1. 先做体检

```powershell
py -m local_voice_input doctor --run-transcribe-smoke
```

这条命令会检查：

- `sherpa_onnx`：语音识别引擎有没有装好。
- `soundfile`：能不能读写 wav。
- `sounddevice`：能不能访问麦克风。
- `model:sensevoice`：模型文件在不在。
- `audio:input_devices`：系统能不能看到麦克风。
- `smoke:transcribe`：用模型包自带中文音频试转一次。

全部是 `OK`，说明基础环境是通的。

## 1.1. 先做小样本测速

体检只能告诉你“能不能跑”，不能告诉你“跑得快不快”。为了避免一上来就拿大模型转一整节课，建议先跑：

```powershell
py -m local_voice_input benchmark
```

它会用已经安装的模型包样例音频做一次小测试，输出类似：

```text
sensevoice-zh-sample    model=sensevoice-small-onnx-int8    duration=5.592s    elapsed=1.543s    rtf=0.276    verdict=usable
advice    适合后台文件转写；如果是长课，先用几分钟样例估算总耗时。
```

这里最重要的是 `rtf`。

现在程序还会多给一行 `advice`。你可以把它理解成“把测速结果翻译成人话”：

- `适合热键短句输入`：比较适合你这种按住说一句、松开立刻上屏的场景。
- `适合后台文件转写`：适合慢一点跑整段音频，但不强调马上出字。
- `不建议直接转整节长课`：先别拿一小时音频硬上，最好先测几分钟样例，或者换轻一点的模型。

`rtf` 可以理解成“处理速度比例”：

- `0.2`：10 秒音频大约 2 秒处理完，很快。
- `0.5`：10 秒音频大约 5 秒处理完，还可以。
- `1.0`：10 秒音频大约 10 秒处理完，已经接近实时。
- 大于 `1.0`：处理比音频本身还慢，拿它转一节课就很危险。

如果想看结构化结果：

```powershell
py -m local_voice_input benchmark --json
```

如果想多跑几次，并让摘要主要看后面几轮：

```powershell
py -m local_voice_input benchmark --repeat 3 --discard-first --json
```

这条命令会输出：

- `all_summary`：所有轮次都算。
- `warm_summary`：去掉第 1 轮以后再算。
- `summary`：如果加了 `--discard-first`，就等于 `warm_summary`。

这样可以避免“第一次加载模型比较慢”把真实使用速度看得太差。

如果想测自己的音频文件：

```powershell
py -m local_voice_input benchmark .\captures\sample.wav --language zh --json
```

后面测试 Qwen3-ASR-GGUF 之类的新模型，也应该先用这个小测速流程跑通，再考虑长音频。

## 2. 看看有哪些麦克风

```powershell
py -m local_voice_input devices
```

输出第一列是设备编号，例如：

```text
1    麦克风 (K7)    channels=2    default_rate=44100
```

如果你想用这个麦克风，后面命令可以加：

```powershell
--device 1
```

## 2.1. 打开最小 GUI 原型

如果你不想每次都记命令，现在优先从 GUI 面板开始。

```powershell
py -m local_voice_input gui
```

也可以直接双击项目根目录里的：

```text
打开语音输入面板.cmd
```

这个入口会优先用 `pyw` 拉起窗口，尽量不再先弹一个命令行黑框。它现在是一个“启动器 + 设置面板”，不是最终完整版桌面应用，但已经能承担日常主入口：

- 看推荐模型和环境体检状态。
- 保存语言、输入设备、热键和提交方式。
- 检查热键冲突，并一键填入推荐热键。
- 开关 API 整理、选择 preset、设置失败退回原文。
- 开关快速记录，让从 GUI 启动的后台热键自动带 `--quick-note`。
- 启动或停止后台按住说话。
- 启用或关闭开机自启。
- 打开配置目录和 `captures` 目录。

第一次用 GUI 时，热键建议先试 `f8`。`caps_lock` 也能用，而且很好按，但它可能影响大小写切换或输入法习惯。后面命令行示例里如果看到 `--hold-key caps_lock`，也可以直接改成 `--hold-key f8`。

从 GUI 里点“启动按住说话”时，热键模式会直接在后台启动；点“停止按住说话”会停掉当前后台进程。窗口底部会给出当前状态。如果启动失败，先看窗口里的提示，再参考 `docs\troubleshooting.md`。

GUI 右上角的关闭按钮不会直接退出，而是会缩到任务栏；如果你真想退出，再点窗口里的“退出面板”。

如果你只想确认 GUI 看到的状态，不想真打开窗口：

```powershell
py -m local_voice_input gui --json
```

## 3. 保存常用设置

如果你主要说中文，并且常用 1 号麦克风：

```powershell
py -m local_voice_input config set --language zh --input-device 1
```

查看当前配置：

```powershell
py -m local_voice_input config show
```

配置文件只是一个 JSON 文件，程序启动时会读它。这样以后不用每次都手写语言和设备。

## 4. 录一段音频

```powershell
py -m local_voice_input record .\captures\sample.wav --seconds 5
```

这条命令只录音，不识别。录完以后会得到一个 wav 文件。

## 5. 转录一个音频文件

```powershell
py -m local_voice_input transcribe .\captures\sample.wav --language zh
```

如果还想把结果保存成 txt：

```powershell
py -m local_voice_input transcribe .\captures\sample.wav --language zh --text-out .\captures\sample.txt
```

如果还想保存基础字幕：

```powershell
py -m local_voice_input transcribe .\captures\sample.wav --language zh --srt-out .\captures\sample.srt
```

当前 SenseVoice 路径没有细分时间戳，所以会先输出一个覆盖整段音频的字幕块。以后换成能返回分段时间戳的后端时，SRT 会自动按分段输出。

如果有多个文件，可以一次传进去，并让程序自动按源文件名保存：

```powershell
py -m local_voice_input transcribe .\audio1.wav .\audio2.wav --language zh --text-out-dir .\transcripts --srt-out-dir .\subtitles
```

这会生成类似：

```text
transcripts\audio1.txt
transcripts\audio2.txt
subtitles\audio1.srt
subtitles\audio2.srt
```

这个形式是为了后面接 Windows “发送到”或“打开方式”做准备。也就是说，先让命令行能稳稳接住文件路径，后面再把它包装成右键菜单或拖拽入口。

### 5.1. 生成一个“拖到这里转录”的脚本

第一版拖拽入口不是 GUI 窗口，而是一个 Windows `.cmd` 小脚本。你可以把音频文件拖到这个脚本上，它会自动调用：

```powershell
py -m local_voice_input transcribe 被拖进来的音频文件 --text-out-dir transcripts
```

先在项目目录里生成一个脚本：

```powershell
py -m local_voice_input sendto install --output .\OpenVoiceInput-Transcribe.cmd --language zh --text-out-dir .\transcripts --srt-out-dir .\subtitles --overwrite
```

生成后，你可以把一个或多个 wav 文件拖到：

```text
OpenVoiceInput-Transcribe.cmd
```

程序会把识别结果保存到：

```text
transcripts\音频文件名.txt
subtitles\音频文件名.srt
```

如果你想把它放进 Windows 右键“发送到”菜单，可以直接安装到默认 SendTo 文件夹：

```powershell
py -m local_voice_input sendto install --language zh --text-out-dir .\transcripts --srt-out-dir .\subtitles --overwrite
```

安装后，在资源管理器里右键音频文件，选择“发送到”，再选 `OpenVoiceInput Transcribe.cmd`。这一步本质上还是调用命令行，只是入口更顺手。

如果你只想看看 Windows 的 SendTo 文件夹在哪里：

```powershell
py -m local_voice_input sendto path
```

## 6. 录音并立刻识别

```powershell
py -m local_voice_input listen-once --seconds 5 --language zh --json
```

这就是当前最小闭环：

```text
麦克风 -> wav 文件 -> SenseVoice 模型 -> 文字
```

## 7. 循环听写

```powershell
py -m local_voice_input dictate-loop --seconds 5 --language zh --copy --text-out-dir .\captures
```

启动后：

- 按 Enter：录一段并识别。
- 输入 `q` 再按 Enter：退出。
- `--copy`：把每次识别结果复制到剪贴板。
- `--text-out-dir`：把每次识别结果保存成 txt。

这个命令还不是最终形态的“按住快捷键说话”，但已经可以当早期听写工具试用。

## 8. 按住热键说话

实验命令：

```powershell
py -m local_voice_input hold-to-talk --hold-key caps_lock --language zh --device 1 --text-out-dir .\captures --srt-out-dir .\captures
```

这里用 `caps_lock` 是因为它适合“按住说话”。如果你是第一次试，或者担心和输入法、大小写切换冲突，可以把命令里的 `--hold-key caps_lock` 改成 `--hold-key f8`。GUI 里的推荐热键也是优先填 `f8`。

启动后：

- 按住 `caps_lock`：开始录音。
- 松开 `caps_lock`：停止录音并识别。
- 按 `esc`：退出监听。

终端里现在还会顺手打印状态线，方便看它卡在哪一步：

```text
startup: submit_strategy=clipboard_paste (自动粘贴到当前光标)
startup: api_processing=disabled (未启用，直接输出原始识别文本)
startup: language=zh (固定中文识别)
startup: input_device_source=cli_override (命令行临时指定)
startup: input_device=1 (固定设备)
startup: recommended_model=sensevoice-small-onnx-int8 (sherpa-onnx)
status: recording_started
status: recording_stopped
status: transcribing
status: completed
status: failed
```

前面这几行 `startup: ...` 都很有用。它们不是识别结果，而是在你开始说话前先告诉你：这次热键听写会按什么方式送出去、有没有启用 API 后处理、当前识别语言是什么、当前输入设备到底来自命令行临时指定还是系统默认，以及现在推荐用哪个模型。这样后面如果你看到“有识别但没上屏”“只进了剪贴板”“输出文字像是被整理过”“好像走错了设备”“模型和你以为的不一样”，第一眼就能先确认是不是启动配置和你想的不一样。

默认模式是 `clipboard_paste`：

1. 程序先给你原来的剪贴板做快照。
2. 临时把识别结果放进剪贴板。
3. 自动发送 `Ctrl+V`，粘贴到当前光标位置。
4. 再把原来的剪贴板恢复回来。

在 Windows 上，程序会优先用原生剪贴板 API 保存多种格式，不只是文本。普通文字、富文本、图片、文件列表大多可以恢复；极少数特殊程序自定义格式可能无法完整保存，日志里会记录跳过的格式数量。

如果你只想复制到剪贴板、不想自动粘贴：

```powershell
py -m local_voice_input hold-to-talk --hold-key caps_lock --language zh --device 1 --clipboard-only
```

## 9. 快速记录

快速记录的意思是：识别出来的文字不只是粘贴，还可以按关键词自动保存到指定文件夹。

入门先记住三步就够了。

第一步，先加一条最小规则：

```powershell
py -m local_voice_input quick-rule add --name ideas --keyword 灵感 --target-dir ideas
```

这条规则的意思是：文本开头附近出现“灵感”时，保存到 `notes\ideas`。

第二步，试着保存一条文字：

```powershell
py -m local_voice_input quick-note 灵感 今天想到一个语音输入工具的点子
```

第三步，如果想让热键识别结果也进入快速记录，启动热键时加 `--quick-note`：

```powershell
py -m local_voice_input hold-to-talk --hold-key caps_lock --language zh --device 1 --quick-note
```

关键词只会在识别文本开头附近触发。这样做是为了避免你后面随口说到“灵感”“待办”时误保存到错误文件夹。

多关键词、保留关键词、命中反馈、没命中时为什么进 inbox，都放在更详细的样例文档里：

```text
docs\quick-note-keyword-examples.md
```

## 10. 模型、任务路由、热词和 API 配置

先说一句大白话：这些命令现在主要是在“写设置”。真正识别时，程序再按这些设置选模型或准备后续 API 接入。

查看当前全局模型设置：

```powershell
py -m local_voice_input model show
```

手动指定一个模型：

```powershell
py -m local_voice_input model set sensevoice-small-onnx-int8
```

恢复自动选择：

```powershell
py -m local_voice_input model auto
```

查看不同任务的模型路由：

```powershell
py -m local_voice_input route show
```

默认思路是：

- `dictation`：日常语音输入，优先快。
- `file_transcription`：文件转写，可以后台跑，优先平衡。
- `long_form`：长音频，可以后台跑，优先准确。

例如，把文件转写改成更重视准确率：

```powershell
py -m local_voice_input route set file_transcription --priority accuracy --background true
```

给某个任务单独指定模型：

```powershell
py -m local_voice_input route set file_transcription --manual-model-id vibevoice-asr-hf-8b
```

清除这个任务的手动模型，恢复自动：

```powershell
py -m local_voice_input route set file_transcription --auto-model
```

热词是“希望模型更容易听准的词”，比如人名、项目名、术语：

```powershell
py -m local_voice_input hotword add Codex 语音输入 硅基流动
py -m local_voice_input hotword list
```

当前 SenseVoice/sherpa-onnx 这条路径还没有真正使用热词；现在先把热词配置保存下来，等后端支持或接 API 时再传进去。

API provider 也是先配置，不会把密钥明文写进项目：

```powershell
py -m local_voice_input api-provider set --provider siliconflow --base-url https://api.siliconflow.cn/v1 --api-key-env SILICONFLOW_API_KEY --model your-model-name
py -m local_voice_input api-provider show
```

这里 `--api-key-env SILICONFLOW_API_KEY` 的意思是：真正的密钥以后放在环境变量 `SILICONFLOW_API_KEY` 里，配置文件只记这个环境变量的名字。

如果网页插件给的是完整接口地址，也可以直接填完整地址：

```powershell
py -m local_voice_input api-provider set --provider siliconflow --base-url https://api.siliconflow.cn/v1/chat/completions --api-key-env SILICONFLOW_API_KEY --model Qwen/Qwen3-8B
```

当前 PowerShell 临时设置密钥：

```powershell
$env:SILICONFLOW_API_KEY="你的 API key"
```

测试 API 是否能跑通：

```powershell
py -m local_voice_input api-provider test --text 请只回复 OK --max-tokens 20
```

这一步只测试“文本发出去、文本拿回来”。它还没有接入语音输入流程。

把 API 接到语音识别后处理：

```powershell
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --api-process
```

意思是：

```text
麦克风 -> 本地语音识别 -> API 整理文字 -> 输出/粘贴/保存
```

如果 API 失败时你希望先用原始识别文本顶上，而不是整条命令失败：

```powershell
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --api-process --api-fallback-raw
```

热键模式也可以加：

```powershell
py -m local_voice_input hold-to-talk --hold-key caps_lock --language zh --device 1 --api-process --api-fallback-raw
```

热键模式启动时也会打印一行 API 摘要。没开时会显示 `api_processing=disabled`；开了以后会显示 `api_processing=enabled`，并写清楚提示词来源是 `preset:clean` 这类预设，还是 `custom:--api-system-prompt` 这类自定义提示词。

如果你是从 GUI 启动后台热键听写，就不需要手动记这些参数。面板里的“API 整理”开关、preset 下拉框和“失败退回原文”会保存到配置里；下次点“启动按住说话”时，GUI 会自动把它们翻译成 `--api-process`、`--api-preset`、`--api-fallback-raw` 这些命令参数。

默认后处理提示词会让模型“修错字、补标点、去掉明显口头填充词，只输出正文”。如果你想换成自己的指令：

```powershell
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --api-process --api-system-prompt "把下面的口语整理成正式中文，只输出正文。"
```

也可以用内置预设，不用自己写提示词：

```powershell
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --api-process --api-preset clean
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --api-process --api-preset formal
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --api-process --api-preset todo
py -m local_voice_input listen-once --seconds 5 --language zh --device 1 --api-process --api-preset translate
```

这些预设分别是：

- `clean`：口语整理，修错字、补标点、去掉明显口头填充词。
- `formal`：正式改写，把口语改成更正式清楚的中文。
- `todo`：待办提取，把内容整理成待办清单。
- `translate`：翻译成简体中文；如果原文已经是中文，就轻微润色。

如果同时使用快速记录：

```powershell
py -m local_voice_input hold-to-talk --hold-key caps_lock --language zh --device 1 --quick-note --api-process --api-fallback-raw
```

程序会用“原始识别文本”开头附近的关键词做路由，用“API 整理后的文本”保存到文件。这样关键词不容易被 API 改没。

## 11. 转录日志

转录命令默认会写一行简要日志到：

```text
captures\transcriptions.jsonl
```

它记录：

- 用的是哪个命令。
- 音频路径。
- 模型名。
- 语言。
- 识别耗时。
- 输出文本长度。
- 有没有复制剪贴板。
- 有没有自动粘贴。
- 有没有恢复旧剪贴板。
- 恢复了多少种剪贴板格式。
- 跳过了多少种剪贴板格式。
- 有没有保存 txt。

现在的新日志还会保存一份 `text` 字段，也就是本次最终输出的文本。这样做是为了后面的“增强上下文”：API 整理时可以参考最近几条你刚刚说过的话，只把文字上下文发给 API，不会发送音频文件。

这意味着：日志不是录音，也不是完整隐私快照；但它可能包含你说出来的文字。如果你这次说的内容不想留下日志，加：

```powershell
--no-log
```

旧日志里如果没有 `text` 字段，增强上下文会自动跳过那条记录。

## 12. 现在的代码分层

- `audio_capture.py`：只管录音。
- `sherpa_backend.py`：只管调用 SenseVoice 模型。
- `text_output.py`：只管保存文本、复制剪贴板。
- `usage_log.py`：只管写简要 JSONL 日志。
- `subtitles.py`：只管把识别结果格式化成 SRT 字幕。
- `quick_note.py`：只管按关键词把记录保存到对应文件夹。
- `model_selector.py`：只管根据任务和硬件选模型。
- `config.py`：只管读写配置。
- `app.py`：把上面这些模块串起来。
- `cli.py`：命令行入口。

这样拆开的好处是：如果录音坏了，就看录音层；如果模型坏了，就看后端层；如果复制失败，就看输出层。不会所有东西搅成一锅。

## 13. 下一步读什么

这份文档只负责把项目跑起来。后面遇到不同问题时，可以按这个顺序去看：

- 想确认 GUI 和环境能不能跑通：看 `docs\troubleshooting.md`。
- 想把“灵感、待办、素材”按关键词自动存到不同文件夹：看 `docs\quick-note-keyword-examples.md`。
- 想排查 GUI、模型文件、麦克风或粘贴失败：看 `docs\troubleshooting.md`。
- 想了解外部 API 和本地录音的隐私边界：看 `docs\privacy.md`。
- 想避免拿大模型跑长音频跑几个小时：看 `docs\model-benchmark-results.md`。
- 想理解模型怎么选：看 `docs\model-selection.md`。
- 想知道项目目标和范围：看 `docs\requirements.md`。

简单说：先用 GUI 跑通，再看快速记录；如果识别文字不够好，再看 API 增强；如果速度不对劲，再看模型测速。
