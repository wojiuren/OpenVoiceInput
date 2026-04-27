# 快速记录关键词口语样例

这页只解释一件事：你说一句话以后，程序怎么判断它应该存到哪个文件夹。

快速记录的关键词是“路由词”。它不是为了提高识别准确率，而是为了告诉程序：“这条记录应该放到哪里”。比如“灵感”放到 ideas，“待办”放到 todo，“素材”放到 materials。

## 最推荐的说法

把关键词放在开头附近，然后停顿一下，再说正文。

```text
灵感 做一个可以按关键词自动分类的语音记录。
待办 明天上午检查一下 GUI 的开机自启。
素材 看到一句话，先让工具稳定，再让工具聪明。
小说 主角第一次发现语音输入工具会误解他的意思。
```

这种说法最稳，因为程序默认只在开头附近找关键词。这样做的好处是：你后面正文里偶然提到“灵感”“待办”时，不会乱跳到别的文件夹。

## 不太推荐的说法

不要把关键词放到很后面。

```text
我刚才想到一个功能，可以自动分类，算了这个放到灵感里面。
今天还有好多事情要处理，其中一个待办是检查日志。
```

这类句子里，关键词虽然出现了，但位置太靠后。按默认规则，它可能不会触发分类，而是保存到 inbox。

这不是坏事。宁可先进 inbox，也不要因为一句话后面随口提到关键词，就把记录误放到错误文件夹。

## 关键词被去掉和保留的区别

每条规则都可以决定是否从保存正文里去掉关键词。

默认更适合去掉关键词。比如你说：

```text
灵感 做一个按住说话松开粘贴的小工具。
```

如果规则是“移除关键词”，最终保存的正文会更干净：

```text
做一个按住说话松开粘贴的小工具。
```

如果规则是“保留关键词”，最终保存的是原句：

```text
灵感 做一个按住说话松开粘贴的小工具。
```

我的建议是：

- “灵感”“待办”“素材”这类只是分类用的词，通常移除。
- “小说”“会议”“课程”这类本身也像标题的词，可以考虑保留。
- 如果不确定，先用默认移除。后面发现保存出来的文本少了你想保留的标题，再改成保留。

## 多个关键词放到同一个文件夹

一个文件夹可以有多个入口词。比如 materials 文件夹可以同时收“素材”“摘录”“引用”。

```text
素材 今天看到一个好句子。
摘录 先把这段话放进材料库。
引用 这里有一句之后可能会用到的话。
```

这三句可以都进同一个 materials 文件夹。这样你说话时不用死记一个固定词，顺嘴说也能归到同类。

## 配置例子

第一版先用命令行配规则。下面这些命令的意思是：

- 名字叫 ideas 的规则，听到“灵感”就放到 `notes\ideas`。
- 名字叫 todo 的规则，听到“待办”就放到 `notes\todo`。
- 名字叫 materials 的规则，“素材”和“摘录”都放到 `notes\materials`。

```powershell
py -m local_voice_input quick-rule add --name ideas --keyword 灵感 --target-dir ideas
py -m local_voice_input quick-rule add --name todo --keyword 待办 --target-dir todo
py -m local_voice_input quick-rule add --name materials --keyword 素材 --keyword 摘录 --target-dir materials
```

如果你想让某条规则保留关键词，加上 `--keep-keyword`。

```powershell
py -m local_voice_input quick-rule add --name novel --keyword 小说 --target-dir novel --keep-keyword
```

## 怎么判断有没有命中规则

启用快速记录后，命令行或后台日志里会有类似这样的反馈。

命中规则时：

```text
quick_note_status: matched_rule (命中规则，已保存到规则目录)
saved_quick_note: notes\ideas\20260425-092000-ideas.txt
matched_rule: ideas
matched_keyword: 灵感
removed_keyword: true
```

没有命中关键词时：

```text
quick_note_status: inbox (未命中关键词，已保存到 inbox)
saved_quick_note: notes\inbox\20260425-092000-inbox.txt
```

看到 inbox 不代表失败，只是说明这句话开头附近没有命中任何规则。

## 小规则

- 关键词尽量短一点，比如“灵感”“待办”“素材”。
- 关键词尽量放开头，最好前几个字就出现。
- 不要把太常见的词当关键词，比如“这个”“那个”“今天”。
- 同一类内容可以设置多个关键词，降低说话时的记忆负担。
- 不确定是否要自动分类时，先让它进 inbox，后面人工整理也可以。
