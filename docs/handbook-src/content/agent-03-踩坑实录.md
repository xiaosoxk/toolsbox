# 第3章 踩坑实录：真实事故与排查过程

本章是手册的核心资产。以下七个坑全部来自本机真实开发过程，每个都按"现象→排查→根因→修复"四段讲。面试时讲踩坑比讲成功更能证明"代码是你写的"。

## 3.1 坑一：MATLAB 秒回 exit=0，但什么都没执行

现象：`matlab_run` 工具首次真机调用，0.1 秒返回 exit=0、无任何输出——理论上 MATLAB 冷启动至少要 30 秒。

排查：时间是最硬的证据。0.1 秒说明"被调用方根本没干活"。查 Windows 上 matlab.exe 的行为，结合官方文档确认：Windows 版 matlab.exe 是一个"启动器（launcher）"，它派生真正的 MATLAB 进程后立即返回，成功码代表"派生成功"而非"执行完成"。

根因：subprocess.run 拿到的是启动器的退出，不是 MATLAB 会话的退出。

修复：命令行加 `-wait`，让启动器等到会话真正结束再退出。这个坑在 Linux 上不存在（matlab 是前台进程），属于典型的"Windows 平台特有行为"。

> 追问式总结：同一个参数在文档里叫"等待会话结束"，但只有踩过才知道不加它时的表现是"假装成功"——静默失败比报错危险得多，所以工具层必须校验"产物存在"而不只看退出码。

## 3.2 坑二：加了 -wait 之后直接挂死 300 秒超时（连环坑）

现象：加 `-wait` 后重跑，300 秒超时；把超时放大到 600 秒仍然超时。工具层正确兜住了（异常归一化为错误文本），但任务不可能完成。

排查：超时期间用 `tasklist` 看到 MATLAB.exe 已加载 739MB 内存——说明 MATLAB 在跑，但永远不结束。怀疑方向有两个：license 联网检查卡住（当时网络确实断了），或有对话框在等人点击。用 PowerShell `Get-Process MATLAB | Select MainWindowTitle` 一看，窗口标题是 **MATLAB R2016b**——真相大白。

根因：我用的 `-batch` 参数是 **R2019a 才引入的**。R2016b 不认识这个参数，直接忽略了它并启动了完整的桌面 GUI，桌面自然永远不退出（-wait 就永远等）。这不是代码 bug，是"环境假设错误"：我默认了较新的 MATLAB。

修复：改用全版本通用的组合拳，R2016b 到 R2024 都兼容：

```text
matlab.exe -nosplash -nodesktop -minimize -wait -logfile out.log -sd workdir -r "try, run('script.m'), catch e, disp(getReport(e)), end, exit"
```

四个参数各有职责：`-r` 以"命令"方式执行（老版本标准做法）；`-logfile` 把输出写文件（绕开启动器不转发 stdout 的第二个坑）；`try/catch` 保证脚本报错也能走到 `exit`——否则 `-r` 模式报错后会停在下一次提示符，会话永不退出；`exit` 保证无交互退出。

> 面试讲法：这个坑展示了完整的排查链——超时→看进程内存证明"在跑"→看窗口标题证明"跑错了东西"。Windows 下 `Get-Process MainWindowTitle` 是分辨"程序卡死"与"程序在等输入"的利器。

## 3.3 坑三：Python 的空 bytes 是 falsy（一行代码的静默炸弹）

现象：MATLAB 无输出时，工具在 `_decode(proc.stdout or "")` 处抛 `AttributeError: 'str' object has no attribute 'decode'`。

根因：`proc.stdout` 是 bytes 类型，捕获时为空字节串 `b""`；而 **`bool(b"") == False`**，`or` 短路后返回了字符串 `""`，后续 `.decode()` 自然崩。正确写法是 `proc.stdout or b""`，或者显式判 None。

修复与防御：两个工具（matlab/python）统一改为 `or b""`，并加注释说明为什么。这类坑的通用教训：**对 bytes 判空必须区分 None 与空串**，`or` 兜底时要保证兜底值与原值同类型。

## 3.4 坑四：测试的 Fake 记录了可变引用，断言被污染

现象：test_history_is_reusable 断言"LLM 收到的最后一条消息是本次任务"，实际拿到的是"好的"（本次任务的回答）。

根因：FakeLLM.chat 里 `self.calls.append(messages)` 存的是**列表引用**；Agent 循环随后继续往这个列表追加 assistant 消息，测试再读时内容已经变了。这是 Python 一等对象引用语义的经典陷阱。

修复：`self.calls.append([dict(m) for m in messages])` 存浅拷贝快照。教训：任何"记录调用参数供事后断言"的测试替身，都必须存快照而非引用。

## 3.5 坑五：Windows 路径分隔符让断言时好时坏

现象：list_files 断言 `"matlab/demo.m" in listing` 失败，实际返回的是 `matlab\demo.m`。

根因：`Path.relative_to()` 在 Windows 上生成反斜杠分隔符。工具输出给人看没问题，但 LLM 与测试都更期望统一的正斜杠（URL 风格，跨平台一致）。

修复：输出前统一 `.replace("\\", "/")`。配套经验：**对外的机器可读输出应做规范化**，平台差异留在内部。

## 3.6 坑六：中文用户名的 Git Bash 乱码

现象：在 Git Bash 里 `ls` WPS 目录时，路径里的中文用户名显示为 `璧栦匠璞`（UTF-8 字节按 GBK 解码的典型乱码）。

排查与处理：这只是 Bash 显示层乱码，真正的路径校验放到 Python 侧做（config.yaml 里写的是正确的中文路径，Python 的 Path 处理正常）。教训：**跨编码环境的脚本，关键路径操作交给 Python 而不是 shell 字符串拼接**；这也是为什么 doctor 命令用 Python 做路径体检而不是一个 .bat。

## 3.7 坑七：git push 时好时坏（DNS 阵发失效）

现象：同一条 `git push`，前一次成功，后一次报 `Could not resolve host: github.com`。

排查：分层定位——`ping 223.5.5.5` 通（基础网络正常）→ `nslookup github.com` 超时（DNS 挂了）→ DoH 查询也不通（出口整体异常）→ 结论是代理/VPN 阵发掉线，不是 git 或凭据问题。

处理：不与网络硬刚。本地 commit 已经做好，等网络恢复后重试一次即成功。教训：**把"提交"与"推送"解耦**，任何时候先保证本地仓库状态完整；推送是幂等重试操作。

## 3.8 踩坑的方法论沉淀（面试收尾用）

七个坑背后是同一条排查方法论：先看时间量级（0.1 秒不可能完成冷启动）→ 再看进程状态（内存证明在跑）→ 然后看环境事实（窗口标题暴露版本）→ 最后才是改代码。以及三条工程原则：外部工具的调用必须校验产物而不只是退出码；对 bytes/路径/编码这类"类型边界"保持警惕；所有可变默认值与引用传递处存快照。