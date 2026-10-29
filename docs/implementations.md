# 实现

同一份线格式，多种语言。下表是**当前真实状态**，包括还不能用的部分。

| 实现 | 语言 | 状态 | 位置 |
|---|---|---|---|
| **msp-py** | Python 3.10+ | 参考实现，PyPI 预发布 `0.1.0a1`，272 个测试通过 | [PyPI](https://pypi.org/project/msp-py/) |
| **msp-ts** | TypeScript / Node ≥ 22.6 | 零依赖，与 msp-py 逐字节互通，24 个测试通过 | [msp-ts](https://github.com/ModelSensingProtocol/msp-ts) |
| **dsh-msp** | JavaScript | DeepSeek Harness 插件：把每个节点的工具变成 agent 工具 | [dsh-msp](https://github.com/hxh230802/dsh-msp) |
| **msp-cpp** | C++20 | CMake + CI + 互通测试，**仓库暂未公开** | 私有 |
| **msp-dotnet** | C# / .NET | `Msp.slnx` 解决方案，**仓库暂未公开** | 私有 |

## 什么叫"互通"

不是"看起来一样"，而是同一段字节：

- 4 字节大端长度前缀 + UTF-8 JSON，8 个顶层字段恒定
- 握手报文在两个实现之间逐字节比对
- `msp-ts` 的测试里直接启动一个 Python 节点，走真实的 TCP 连接

`msp-py` 与 `msp-ts` 的互通用例在 `msp-ts/test/` 下，跑测试时会去找同级的
`ModelSensingProtocol/src`（或已安装的 `msp` 包），找不到会明确报错而不是跳过。

## 一致性

规范里的 `schema/2026-10-10/` 是**唯一**的字段定义来源，各实现的清单字段以它为准；
`tools/gen_schema.py` 从 YAML 生成 JSON Schema 与字段索引，避免手抄。

## 想加一种语言

最小可用实现只需要四件事：

1. 分帧：4 字节大端长度 + JSON
2. 握手：`HELLO`（带 manifest）→ `ACK`
3. 发现：读写共享目录里的声明文件，并按 `node_id` 去重
4. 心跳：15 秒 `PING`，45 秒无响应判失联

其余（模式、授权、传输）都能后加——这正是"每层皆可扩展"的意思。
