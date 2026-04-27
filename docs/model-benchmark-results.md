# 模型测速结果

这份文档记录真实测速结果。没有实测的数据不要填成结论。

## 测试环境

### 7840HS 迷你主机

- 日期：2026-04-24
- Windows 版本：Microsoft Windows 11 专业版 `10.0.26200`
- CPU：AMD Ryzen 7 7840HS
- RAM：约 `55.7 GB`
- GPU / 驱动：AMD Radeon 780M Graphics，驱动 `32.0.21030.2001`，约 `4 GB` 显存
- 电源模式：待补充

### RTX 4090 服务端

- 日期：
- Windows / Linux 版本：
- CPU：
- RAM：
- GPU / 驱动：
- 网络连接方式：

## 结果表

| 模型 | 机器 | 后端 | 音频 | 冷启动 | 热启动/转写 | RTF | RAM | 显存 | 准确率备注 | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sensevoice-small-onnx-int8` | 7840HS | sherpa-onnx | 模型包 `zh.wav`，5.592s | 第 1 轮约 1.623s / RTF 0.290 | repeat=3 剔除第 1 轮后平均 1.376s | 剔除第 1 轮后平均 0.246 | 待测 | 不适用 | 输出“开放时间早上9点至下午5点。” | 热状态 fast；仍需真实短句样例 |
| `qwen3-asr-0.6b` | 7840HS | qwen3-asr-gguf | 公开 `zh.wav`，5.592s | 引擎初始化约 2.19s（DML+Vulkan） | 总处理约 0.83s（补丁后完整跑通） | 约 0.149 | 待测 | 待测 | 输出“开放时间：早上9点至下午5点。”；实验副本去掉 emoji 打印后可完整退出 | 速度很强，但当前只在实验副本中靠补丁绕过 Windows 控制台编码问题 |
| `qwen3-asr-1.7b-q4` | 4090 | qwen-asr-gguf | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | 不下载前不填 |

## 原始命令记录

```powershell
py -m local_voice_input benchmark --json
```

输出摘要：

```json
{
  "count": 1,
  "avg_elapsed_s": 1.543,
  "avg_rtf": 0.276,
  "verdict": "usable"
}
```

注意：这是第一轮短样例测试，还没有把冷启动和热启动拆开。后续要用 `--repeat` 和用户主动提供的样例继续测。

补充 repeat=2：

```powershell
py -m local_voice_input benchmark --repeat 2 --json
```

```json
{
  "count": 2,
  "avg_elapsed_s": 1.534,
  "avg_rtf": 0.274,
  "worst_rtf": 0.288,
  "verdict": "usable"
}
```

补充 repeat=3 并剔除第 1 轮：

```powershell
py -m local_voice_input benchmark --repeat 3 --discard-first --json
```

```json
{
  "summary": {
    "count": 2,
    "discarded_first_count": 1,
    "avg_elapsed_s": 1.376,
    "avg_rtf": 0.246,
    "worst_rtf": 0.247,
    "verdict": "fast"
  },
  "all_summary": {
    "count": 3,
    "avg_elapsed_s": 1.458,
    "avg_rtf": 0.261,
    "worst_rtf": 0.290,
    "verdict": "usable"
  }
}
```

解释：`summary` 是剔除第 1 轮后的热状态结果，`all_summary` 是三轮全算。这个差异说明第一轮确实会拖慢平均值，因此后续比较模型时应同时看两个摘要。

现在 `benchmark` 命令还会直接给一条人话建议，例如当前 SenseVoice 基线更接近：

```text
适合后台文件转写，日常短句输入也够快。
```

这条建议是为了避免用户只看到 `fast` / `usable` 却不知道该不该拿去转长课。

补充复测（2026-04-24，同样是 `repeat=3 --discard-first`）：

```text
summary: avg_elapsed 约 1.345s，avg_rtf 约 0.240，verdict=fast
advice: 适合后台文件转写，日常短句输入也够快。
```

再次复测（2026-04-24，系统负载不同）：

```text
summary: avg_elapsed 约 1.813s，avg_rtf 约 0.324，verdict=usable
advice: 适合后台文件转写；如果是长课，先用几分钟样例估算总耗时。
```

这说明单次测速会受系统负载影响。后续比较新模型时，不能只盯一次跑分，最好保留多次重复测试。

## 暂定推荐

当前只根据已跑通程度，不根据未实测宣传数据：

1. `sensevoice-small-onnx-int8`：当前默认稳定模型。
2. `qwen3-asr-0.6b`：下一步最值得在 7840HS 上测试的候选。
3. `qwen3-asr-1.7b-q4`：后续 4090 服务端候选。
4. `fun-asr-1.5-dialect-api`：方言专项 API 候选。
5. `nemotron-speech-streaming-en-0.6b-foundry-local`：英文流式专项候选。

## 下载决策

截至 2026-04-24，`Qwen3-ASR-GGUF 0.6B` 的下载决策是：

- **Go，但只做受控实验**
- 第一轮只下载：
  - `Qwen3-ASR-Transcribe-20260223.zip`（约 `98.6 MB`）
  - `Qwen3-ASR-0.6B-gguf.zip`（约 `537.8 MB`）
- 第一轮不下载：
  - `Qwen3-ASR-1.7B-gguf.zip`（约 `1345.2 MB`）
  - `Qwen3-ForceAligner-0.6B-gguf.zip`（约 `481.4 MB`）

原因很简单：当前 SenseVoice 已经证明“能用而且够快”，所以 Qwen3 这一步应该是实验加分项，不该反过来把主线拖乱。

## 第一轮实验记录：Qwen3-ASR-GGUF 0.6B

本轮只做了受控实验边界内的动作：

1. 下载 `Qwen3-ASR-Transcribe-20260223.zip`
2. 下载 `Qwen3-ASR-0.6B-gguf.zip`
3. 解压到独立目录 `experiments/qwen3-asr-0.6b/`
4. 用公开样例 `sample-zh.wav` 做 smoke test

实际命令是：

```powershell
.\transcribe.exe ..\..\sample-zh.wav --model-dir ..\..\model-0.6b --language Chinese --no-ts -q -y
```

第一次结果：

- 模型链路能启动
- DML / Vulkan 路线在这台 7840HS 上能进初始化
- 公开样例成功转出：

```text
开放时间：
早上9点至下午5点。
```

- `sample-zh.txt` 已实际写出
- 但打包版 `transcribe.exe` 会在保存完成后，因为打印 `✅` / `📊` 这类 emoji 触发 `UnicodeEncodeError: 'gbk' codec can't encode character ...`

因此当时判断是：

- **模型可跑**
- **文本结果可落盘**
- **Windows 打包 CLI 还不够稳，暂时不能直接拿来当默认可交付路线**

后续绕过实验：

- 只修改 `experiments/qwen3-asr-0.6b/` 里的第三方副本
- 把 `qwen_asr_gguf/inference/asr.py` 和 `exporters.py` 里的 emoji 打印改成普通文本
- 不改主项目源码

补丁后复测：

```text
引擎初始化耗时: 2.19 秒
RTF: 0.149
总处理耗时: 0.83 秒
文本成功写出，进程 0 退出
```

这说明：

- **Qwen3-ASR-GGUF 0.6B 在这台 7840HS 上不只是能跑，而且样例速度明显快**
- **真正的问题不在模型推理本身，而在 Windows 打包版的控制台输出兼容性**
- **现阶段它仍然更像“有前途的实验后端”，还不是主项目里可以直接默认交付的稳定后端**

补充 CPU-only 复测（关闭 DML / Vulkan）：

```text
引擎初始化耗时: 1.91 秒
总处理耗时: 1.90 秒
RTF: 0.340
文本成功写出，进程 0 退出
```

这说明：

- 开启 DML / Vulkan 时，Qwen3 这条路线在 7840HS 上确实很有竞争力。
- 纯 CPU 时，它仍然能跑，但速度优势就没那么夸张了，已经接近当前 SenseVoice 基线。

## 当前定性结论

截至 2026-04-24，`Qwen3-ASR-GGUF 0.6B` 更适合定位成：

- **独立实验工具**
- **主项目的候选实验后端**

但**暂时不建议直接接成主项目里的默认实验后端实现**。

原因：

1. 当前可跑通的版本依赖第三方副本补丁，而不是原版稳定发布。
2. 它的运行链路和依赖栈明显不同于当前 `sherpa-onnx`，接入成本不只是“换个模型名”。
3. Windows 打包 CLI 虽然已被实验补丁绕过，但还没有形成主项目内可维护、可测试、可解释的稳定适配层。
4. 在 CPU-only 情况下，它的优势会缩小；真正亮眼的是 DML / Vulkan 路线，而这又会增加环境差异。

所以更稳妥的路线是：

- **现在：继续把它当独立实验工具**
- **以后如果要接入：优先做 subprocess 适配层，把它当外部后端调用，而不是立刻把第三方内部代码揉进主项目**
