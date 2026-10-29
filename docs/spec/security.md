# MSP 安全模型 —— 信任边界、节点认证与授权

| | |
|---|---|
| **协议修订** | `2026-10-10` |
| **状态** | 🟡 部分实现 |
| **本页定义** | 信任边界的判定规则、威胁模型、跨机部署所需的 TLS / 节点认证 / 身份绑定，以及授权表 `grants` 的完整语义与执行点 |

> 规范性用语（**必须** / **不得** / **应当** / **不应当** / **可以**）与状态标记（✅ 已实现 / 🟡 部分实现 / 🔵 规划中）的定义见[规范索引 §2](index.md#2-规范性用语)。正文中加粗的关键词承担规范效力。

**本页的状态分布**：信任边界 = 传输可达范围，是**当前实现的事实姿态**（✅）；TLS、节点认证、身份绑定、授权表全部为 🔵 **规划中**——设计已定稿、实现待排期。规划中的条文「**实现者可以不实现，但一旦实现必须符合条文**」（[README §7](index.md#7-一致性) 第 6 条）。


## 1. 概述

### 1.1 核心结论

> **信任边界就是传输可达范围——谁能连上来，谁就在信任域内。**

三条推论：

1. 协议层因此**不得**把 TLS / 认证 / 授权做成每条消息自带的默认校验；安全由**部署形态**决定，而不是由每一条消息自己决定。
2. 「连上来」之后还要分两层：**认证**（Authentication：你是谁）与**授权**（Authorization：你能做什么）。二者不可互相替代。
3. 一个不能真正提供安全性的安全功能，比没有更危险。因此本规范**不得**给出虚假的默认安全承诺；反过来，只要声明的边界与实现一致，**不实现**扩展安全机制就是合规的（[README §7](index.md#7-一致性) 第 6 条）。

当前参考实现即此姿态：没有任何认证与授权代码，连接成功即视为可信对端（✅）；本页的其余机制全部是 🔵 规划。

### 1.2 一句话对照表

| 部署形态 | 信任边界 | 需要什么 |
|---|---|---|
| localhost 自组网 | 同一 OS 用户 | 无需 TLS / 认证 / 授权 |
| 跨机 / 公网 | 网络可达范围 | TLS + 节点认证 + 授权（默认只留应答通道） |

> **安全是部署决策，不是协议默认值。** 因此 MSP 选择把边界说清楚，而不是给一个虚假的默认安全承诺。


## 2. 模型与契约

### 2.1 认证 ≠ 授权

| | 问题 | 手段 | 局限 |
|---|---|---|---|
| **认证** Authentication | 你是谁 | 证书 / 密钥 | 只能证明「你是 `node_b`」 |
| **授权** Authorization | 你能做什么 | 本地策略表（`grants`） | 决定「`node_b` 能否调 `rm -rf` 工具」 |

证书**不能**证明 `node_b` 有权调某个危险工具：身份可信与行为可信是两件事。**认证通过**只意味着「这条连接确实来自 `node_b`」，它**不得**被当作「`node_b` 可以做任何事」的依据；反过来，未做认证也**不得**作为授权缺失的借口——两者**必须**独立配置、独立生效。

### 2.2 威胁模型

| 攻击者 | 能干什么 | 对策 |
|---|---|---|
| 链路上的窃听 / 篡改者 | 读、改、重放消息 | TLS（§2.4.1） |
| 未经认证就连接进来的节点 | 冒充任意 `node_id`，混入发现、搅乱去重、白嫖广播 | 节点认证（§2.4.2） |
| 已认证但不可信的节点 | 调未开放的工具、`publish` 触发副作用、偷看广播 | 授权（§3） |

三类攻击者不是并列选项，而是纵深关系：只在**不可信链路**上才需要 TLS；只在**存在不属于同一信任域的对端**时才需要节点认证；只要对端已经连进来，就需要授权。**已认证**只抬高冒充成本，**不降低**任何一条授权检查的必要性。

### 2.3 本机自组网：为什么不做认证

MSP 面向的第一类场景是**本机自组织网络**：同一台机器上的一组进程 / 节点通过 localhost 互联，各自独立编组、共享发现注册表、互相广播。这种形态下做认证**没有意义**，因为每个节点的**权限集合相等**：

- 所有节点跑在**同一个 OS 用户**之下，文件系统、网络端口、环境变量、进程信号的可达权限完全相同；
- 一个节点能读到的、能调用的、能写到的，另一个节点同样能读到、调用、写到；
- 加密通道（TLS）保护的是「传输途中」的机密性，而 localhost 回环**不经过不可信网络段**，没有中间人可拦。

> **认证一个和你权限相同的对端，等于认证你自己**——不增加任何真实的安全收益，只增加握手复杂度与部署成本。

同一条推理也适用于授权：同一 OS 用户下，「允许 `node_b` 读某个文件」并不构成任何额外保护，因为 `node_b` 本就能直接读。**因此本机对端的整张授权表绕过、全量信任**（见 §3.5）。

**边界条件**（此结论失效的情形）：跨 OS 用户、容器 / 沙箱隔离、虚拟化边界、以及 SSH 转发或代理把远端流量伪装成回环的场景。这些形态下「权限集合相等」的前提不成立，**必须**按跨机处理（§2.4）。

### 2.4 跨机：安全随传输走

**状态**：🔵 规划中（设计已定稿，实现待排期）。

跨机暴露是**显式开启、默认关闭**的模式：节点默认只监听 localhost（✅ 事实），谁要跨机、谁自己去监听 `0.0.0.0`，并同时配好本节四项。安全模型是「**随传输走**」而不是「随协议走」的：当信任边界从同一 OS 用户扩大到网络可达范围，**必须**在**传输层之上、协议核心不动**的前提下补上四项；以下条文**实现者可以不实现，但一旦实现必须符合条文**。

#### 2.4.1 TLS

- TLS **必须**以「包装 `Transport` / `Connection`」的方式实现：协议层只调 `Connection.send` / `receive`，因此 TLS 包装后**不得**要求 `core` 或协议层有任何改动。
- 客户端**必须**校验证书链与主机名（`hostname` 校验）；**不得**使用 `CERT_NONE` / 跳过校验的调试开关进入生产配置。
- 服务端**应当**要求并校验客户端证书（即 mTLS），与 §2.4.2 取法一配合使用。
- 传输地址形态随之扩展：WebSocket 的 `ws://` 对应 `wss://`，裸 TCP 对应 `tls://` 或传输包装层显式开启的 TLS 模式（🔵，具体地址形态见 [transports.md](./transports.md)）。当前 `WebSocketTransport` 只接受 `ws://`（`_parse_url` 拒绝其他前缀）。

#### 2.4.2 节点认证

连接建立后**必须**校验对端身份，防未授权节点混入发现注册表或监听敏感命名空间。两种取法：

| 取法 | 机制 | 适用 | 代价 |
|---|---|---|---|
| **mTLS** | 证书 CN / SAN = `node_id`，双向校验 | 已有 PKI 的机房 | 需要证书签发与轮换流程 |
| **签名 HELLO** | Ed25519 私钥签自己的 manifest，`node_id` 绑定公钥，显式 pin / TOFU + 人工确认 | P2P、免 PKI | 需要密钥分发与首连确认 |

**默认倾向签名 HELLO**：它更贴合 P2P，免去 PKI 负担，且与 MSP「节点自述能力清单」的既有握手天然重合——签名对象就是manifest 本身，不需要额外的证书语义。

**签名 HELLO 的报文定义**（字段见 §5.2）：

1. 发起方在 `hello` 的 `payload.auth` 中携带 `scheme="ed25519"`、`nodeId`、`publicKey`、`nonce`、`timestamp`、`signature`。
2. 接受方**必须**在 `ack` 的 `payload.auth` 中**回签**自己的 manifest（同样的字段与签名规则），使认证成为**双向**的；只做单侧认证的实现在本规范中不视为符合本节。
3. **签名覆盖范围**：签名对象是下列字节串，收方**必须**用完全相同的规范化方式重建它（键排序、无多余空白、UTF-8）：

   ```text
   signing_bytes = utf8(json.dumps(
       {"manifest": <payload.manifest>, "nodeId": <payload.auth.nodeId>,
        "nonce": <payload.auth.nonce>, "timestamp": <payload.auth.timestamp>},
       sort_keys=True, separators=(",", ":"), ensure_ascii=False))
   ```

   即：签名**覆盖 manifest 全文**，防止中间人在握手后篡改能力声明；`nodeId`、`nonce`、`timestamp` 一并入签，防止字段替换与重放。
4. **防重放**：`nonce` **必须**是至少 16 字节的不可预测随机值（十六进制编码）；`timestamp` 为 Unix 秒，收方**必须**拒绝偏离本地时钟超过 **±60 s** 的报文；收方**必须**在时间窗内缓存已见 `nonce` 并拒绝重复值。超出时间窗的 `nonce` 缓存**可以**丢弃。
5. **TOFU 存储**：首次见到某 `node_id` 的公钥时，**应当**按 Trust On First Use 记录并标记为未确认，**应当**要求人工确认后才接受（或按部署策略直接拒绝，fail-closed）。记录已确认的 `node_id` 收到**不同公钥**时，**必须**拒绝连接并告警——这是密钥替换攻击（impersonation）的检出点。存储形态见 §5.3。

#### 2.4.3 身份绑定

- `hello` 中声明的 `node_id`（`Signal.source`）**必须**与 TLS 证书身份或签名密钥身份一致；不一致就断开。
- 校验**必须**发生在**登记连接之前**：未通过身份绑定的连接**不得**进入 `connections`、**不得**写入 `peer_manifests`、**不得**产生发现事件。
- 不绑定会导致两类破坏：
  1. **发现注册表污染**：声明文件按 `node_id` 命名，扫描侧以 `_known[node_id]` 为去重键。冒充者可用他人的 `node_id` 覆写声明，把对端流量引向自己的地址，或让真实节点被判定为「声明未变」而永不刷新。
  2. **去重紊乱**：重复连接去重的「规范方向」由 `node_id` 的字典序决定（`self.node_id < peer_id` 的一方为发起方）。冒充者随意挑选 `node_id`，就能让规范方向在两条连接间来回翻转，形成持续重连与状态抖动。

#### 2.4.4 授权

见 §3。


## 3. 授权

> **状态**：✅ 已实现（`src/msp/core/grants.py`）。两个执行点是 `MSPProtocol.authorized()`（入站，`_dispatch` 的第一条语句）与 `grant_sub()`（出站扇出）。本节定义授权表 `grants`。

### 3.1 授权与能力分离

能力位（`pub` / `sub` / `req` / `rep`）在 `Manifest` 里，是「**我自称会什么**」；授权在**本地策略**里（落点见 §3.2），是「**我允许对端做什么**」（[README §5.5](index.md#55-角色能力位)）。

- 授权**不得**依赖对端自报：对端把 `capabilities` 写成 `["pub","sub","req","rep"]` 不产生任何权限。
- 授权**不得**随清单交换：`grants` 是本地策略，**不得**出现在 `Manifest` 的任何字段里，也**不得**由 `manifest_update` 更新。
- 对端能力位**可以**用于本地优化（例如知道对端不支持 `msp/task` 就不必尝试），但**不得**用于授权判定。

### 3.2 授权表的声明位置

授权表是**本地策略**，在构造节点时注入，**不得**出现在 `Manifest` 的任何字段里。**规范性要求只有三条**：本地策略、不进清单、不能被对端自报影响；**落点由实现自选**——参考实现放在节点配置 `config["grants"]`（`node.py` → `MSPProtocol(grants=...)`），把它放进节点角色预设（`Preset` 式）同样合规。

解析**必须** fail-closed：配置读不懂就**应当**让节点起不来，**不得**按「读不懂就放行」处理；唯一例外是整张表缺失——那按 §3.5 的默认姿态（全拒 + `rep` 通道）处理。

```python
# 本地策略（不随 manifest 交换）
grants = {
    # 未列明的任何对端：默认只留应答通道
    "*":      {"req": [],            "pub": False, "sub": False, "rep": True},
    # 逐 peer 覆盖
    "node_b": {"req": True,          "pub": ["notify.**"], "sub": ["metric.**"], "rep": True},
    "node_c": {"req": ["read_file"], "pub": False, "sub": False, "rep": True},
}
```

查找规则：先按对端 `node_id` 精确匹配，命中则用该条；未命中则回退到 `"*"`。若 `"*"` 也不存在，**必须**按全部拒绝处理（`req=[]`、`pub=False`、`sub=False`、`rep=True`，即 §3.5 的默认姿态），**不得**按全部允许处理。逐 peer 覆盖是**整条替换**，不是逐字段合并：`node_c` 未写 `rep` 时，`rep` 取该条目自身的缺省值 `True`。

### 3.3 四个动作

| 动作 | 语义 | 授权主体 | 匹配方式 | 默认 |
|---|---|---|---|---|
| `req` | 允许它调我的工具 | 工具名列表 | 精确匹配（`True` = 全部） | `[]`：一个都不给 |
| `pub` | 允许它的 publish 触发我的 `on()` | path 模式列表 | 复用 `pattern_matches` | `False` |
| `sub` | 允许它收我的广播 | path 模式列表 | 复用 `pattern_matches` | `False` |
| `rep` | 允许它的应答（`tool_result`）进来 | 布尔 | 不分工具 | `True` |

逐条说明：

- **`req`**：`True` 表示全部工具；列表表示白名单，按工具名**精确匹配**（`[a-z0-9_-]+`，见 [README §5.3](index.md#53-命名规范)）——**不得**把工具名当路径做通配匹配。空列表表示一个都不给。`req` **不**影响本节点主动发起的 `call()`。
- **`pub`**：对端 `signal` 信号的 `path` **必须**匹配列表中至少一个模式，回调才会被触发；否则该信号被丢弃（不回 `on()`）。模式匹配**必须**复用 [publish-subscribe](./patterns/publish-subscribe.md) 定义的 `pattern_matches(pattern, path)`，**不得**另立匹配算法。注意 `"notify.**"` 同时放行路径恰为 `notify` 的信号。
- **`sub`**：本节点 `publish()` 时，按对端逐个判定：对端**可以**收到本次广播，当且仅当 `path` 匹配该对端 `sub` 列表中的至少一个模式。`False` 表示一个都不发。
- **`rep`**：布尔，不分工具、不分 `reqid` 归属之外的条件；`True` 表示对端的 `tool_result` **可以**进入本地的 `reqid` 匹配流程。

**取值域约束**：`pub` / `sub` 的取值**必须**是 `False` 或**非空字符串列表**。列表元素**不得**在中间使用通配符（仅允许精确、`前缀.*`、`前缀.**`），因为 `pattern_matches` 对中间通配符返回 `False`；实现**应当**在加载策略时校验并拒绝这类配置（fail-closed）。本修订**不**为 `pub` / `sub` 定义「单个模式全量放行」的写法：`pattern_matches` 要求通配符带前缀，裸 `*` 与裸 `**` 匹配不到任何 path，要全量放行需逐一列举域前缀（如 `["notify.**", "metric.**"]`）。

### 3.4 `rep` 为什么与前三个不是一类

**`req` / `pub` / `sub` 是对它的限制**——关掉就是不许它主动对我做什么；**`rep` 是我留给自己的通道**——由我发起、它应答的交互（`call()` 的返回值）默认放行。

所以「默认 rep-only」的准确含义是：**默认状态下对端在我面前只能当应答方——我不能靠它主动，但我随时能靠它**。

把 `rep` 显式写成 `True` 是刻意的，有两个作用：

1. 让「默认姿态」在表里**看得见**：读者一眼能看出默认不是「全拒」，而是「只留我发起的通道」；
2. 避免实现时把「应答」误当成「请求」一并拒掉——`tool_result` 与 `tool_call` 是同一交互的两半，若把默认姿态简化成「未授权即全拒」，`call()` 会永久超时，且表现为难以定位的静默失败。

### 3.5 默认值与作用域

- `"*"` 即**网络对端**的默认姿态：`req` 空白名单（什么都不暴露，显式加一个工具名才开放一个）、`pub` 拒绝、`sub` 拒绝、`rep` 放行。
- **本机（loopback / UDS 同用户）整张表绕过、全量信任**；只有跨机对端走这张表。
- **本机判定规则**（🔵）：一条入站连接**应当**被判定为本机，当且仅当其传输后端为 `uds`，或其 TCP / WebSocket 地址的 host 属于 `127.0.0.0/8`、`::1`、`localhost`。判定**必须**基于**本端已建立的连接**与其对端地址，**不得**依赖对端在 `hello` 里自报的任何字段。

### 3.6 执行点：只有两处

授权检查的执行点**只有两处**，其余路径**不得**重复实现，也**不得**绕过。`core` 仍然只认 `Signal`。

**入站**（`_dispatch(peer_id, sig)`，必须是该函数的第一条语句）：

```python
def _dispatch(self, peer_id: str, msg: Signal) -> None:
    if not self._authorized(peer_id, msg):     # 🔵 授权检查：必须是第一行
        self._reject(peer_id, msg)             # 丢弃，或回 error（见 §6）
        return
    # ... 核心信号分发 / pattern 路由照旧

def _authorized(self, peer_id: str, msg: Signal) -> bool:
    if self._is_local(peer_id):                # 本机 bypass：整张表绕过
        return True
    g = self._grants_for(peer_id)              # 逐 peer 覆盖，否则 "*"
    t = msg.type
    if t == SignalType.TOOL_CALL:              # req
        return g["req"] is True or msg.payload.get("tool") in g["req"]
    if t == SignalType.SIGNAL:                 # pub
        pats = g["pub"]
        return bool(pats) and any(pattern_matches(p, msg.path or "") for p in pats)
    if t == SignalType.TOOL_RESULT:            # rep
        return bool(g["rep"])
    return True                                # 其余信号类型不受本表管辖
```

**出站**（`publish()` 的扇出循环）：

```python
def publish(self, path: str, payload: dict) -> None:
    msg = Signal.make(type=SignalType.SIGNAL, source=self.node_id,
                      path=path, payload=payload)
    for peer_id, conn in list(self.connections.items()):
        if not self._is_local(peer_id) and not self._grant_sub(peer_id, path):
            continue                           # 🔵 sub 未授权：跳过该对端
        try:
            conn.send(self._encode(msg))
        except ConnectionClosed:
            self._handle_disconnect(peer_id, conn)
```

`sub` 只筛选**收件人**，**不改变**报文内容：实现**不得**为不同对端生成内容不同的广播副本，否则同一时刻不同观测者看到的信号不一致，「广播」语义即被破坏。

### 3.7 与广播模型的张力

广播模型下没有订阅表——`publish` 把信号发给所有已连对端，接收方用 `on()` 做本地匹配。`sub` 授权是**发送侧的扇出过滤**，于是「广播 = 全发」与「不让未授权者看」在这里冲突。

它与已删除的订阅表**形状相似但性质不同**：

- 订阅表回答「谁**想**要」，目的是带宽优化，违约后果只是多收几条无用信号；
- `sub` 授权回答「谁**能**看」，目的是安全，违约后果是信息泄露。

**故按安全需要加回 per-peer 过滤，不掺带宽优化**：`sub` 的判定依据**必须**只有授权表，**不得**因为对端「没订阅过这个 path」就跳过——那会把安全策略退化成带宽策略，也会让「广播」在观测上不可预测。

### 3.8 顺序要求

- 授权检查**必须**位于 `_dispatch` 的**第一条语句**，**先于**核心信号分发、**先于** `pattern` 路由、**先于**任何入队或起线程的动作。
- `_read_loop` **不得**在调用 `_dispatch` 之前处理任何会改变本地状态的消息（仅允许刷新 `_last_seen` 心跳时间戳）。
- 新增信号类型、新增通讯模式、新增传输后端时，**不得**绕开 `_dispatch` 直接调用模式处理器或工具表；否则授权即失效——这是本页最关键的一条实现约束。

### 3.9 模式私有信号的授权归属

授权表受管辖的只有三个**核心类型**：`tool_call`（`req`）、`signal`（`pub`）、`tool_result`（`rep`）。连接机制类（`hello` / `ack` / `ping` / `pong` / `error` / `manifest_update`）不受管辖——它们不触发任何动作。

其余信号（模式私有类型）**没有默认通道**：**必须**由注册的模式显式声明归属，**未声明即拒绝**。实现**必须**提供 `PatternHandler.authorize(entry, sig) -> bool` 作为扩展点，且其**默认实现返回 `False`**。

本节存在的全部理由：新增一个模式或一种信号类型时，忘记归类的后果**必须**是「被拒绝」而**不得**是「默认放行」。参考实现的映射：

| 模式 | 信号 | 通道 |
|---|---|---|
| `msp/task` | `task_submit` | `req`：`payload.task` 视同工具名做**精确匹配**（与 `tool_call` 同一白名单、同一匹配语义） |
| `msp/task` | `task_query` / `task_cancel` | `req`：要求该对端有**任意** `req` 权利；具体归属另由记录上的 `client_id` 判定把关 |
| `msp/task` | `task_status` / `task_artifact` / `task_result` / `input_required` / `input_response` / 各 `*_result` 回执 | `rep`：都是「我允许你把结果回给我」这条通道 |
| `msp/multi-round` | `input_required` / `input_response` | `rep` |
| `msp/multi-round` | `tool_call` / `tool_result` | 复用核心类型名，由协议层按 `req` / `rep` 直接判定，不经模式 |

模式**不得**无条件返回 `True`：那等于让任何新起的信号类型名自动获得「免授权」地位，`req` 白名单随之失效。协议层对「没有任何处理器会对其动作」的类型仍**可以**放行到核心分发（由它回 `-32600`）——放行不产生副作用，却能让「我不认识这个类型」与「你没权限」在排障上可区分。

### 3.10 写方向的来源校验

授权判定回答的是「**你是否有资格跟我说话**」，它**不能**替代「**这条消息是不是关于你自己的那件事**」。

- 事务归属**必须**按**连接身份**（握手后由本地连接确定的 `peer_id`）判定，**不得**用 `Signal.source`——后者是对端自报字段，攻击者把它填成受害者的 `node_id` 就绕过了。
- 典型反例：`task_status` / `task_artifact` / `task_result` 携带 `taskId`，而 `task.<id>.**` 旁观广播会把 `task_id` 发给**所有**已连对端（见 [task](patterns/task.md) §7）。因此「id 猜不到」不构成防线，**必须**校验发送方就是该任务的执行者。读方向（`task_query` / `task_cancel` 的 `client_id` 判定）与写方向（执行者判定）**必须**对称。
- 同理，`msp/multi-round` 的 `reqid` 在参考实现里是 `mr-<n>`（可预测），其追问与应答**必须**校验来源，**不得**只凭 `reqid` 命中就接受。`reqid` **不得**被当作安全令牌。


## 4. 消息流

### 4.1 入站 `req` 检查拦下未开放的工具（主图）

```text
node_b（已通过节点认证）              node_a（本节点；grants["node_b"].req = ["read_file"]）
        │                                      │
        │ ── tool_call {tool:"rm_rf"} ────────▶│  ① _read_loop: conn.receive() → Signal
        │    reqid="9f2c…"                     │  ② _dispatch("node_b", sig)  ← 第一行查授权
        │    pattern="msp/request-reply"       │  ③ _authorized: "rm_rf" ∉ ["read_file"]
        │                                      │     → 拒绝
        │                                      │  ④ 不入队、不起执行线程
        │                                      │     （工具函数从未被调用，无副作用）
        │ ◀── error {code:-32000, reqid:…} ────│  （可选；也可静默丢弃，见 §6）
        │                                      │
        │ ── tool_call {tool:"read_file"} ────▶│  ⑤ 白名单命中 → 通过 → _on_tool_call
        │ ◀── tool_result {content:[…]} ───────│  ⑥ 正常执行并回包
        │                                      │
    ── 认证只回答「你是 node_b」；本图里 node_b 确实是 node_b，但 rm_rf 依然被拒 ──
```

对照：若第 ③ 步被删掉，第 ④ 步就会变成「起线程执行 `rm_rf`」——**认证通过**丝毫不减这一步的必要性。

### 4.2 出站 `sub` 过滤

`node_a.publish("metric.cpu", …)` 扇出时：`node_b` 的 `sub=["metric.**"]` 命中 → 发送；`node_c` 的 `sub=False` → 跳过（`node_c` 永远看不到这条广播）；本机对端 → 绕过整张表，直接发送。

### 4.3 跨机签名 HELLO 握手（🔵）

顺序是：TLS 建立（§2.4.1）→ `hello` 携带 `payload.auth` → 接受方验签、查时间窗与 `nonce` 重用、判定身份绑定（§2.4.3）→ 查 TOFU 存储（公钥变化即拒绝）→ 全部通过后才登记连接 → `ack` 回签 → 发起方对称验签。任一步失败：**必须**关闭连接，且**不得**登记 `peer_id`、**不得**写入 `peer_manifests`、**不得**触发 `on_connected`。


## 5. 数据类型

### 5.1 授权表条目

| 字段 | 类型 | 必填 | 默认 | 语义 |
|---|---|---|---|---|
| `req` | `boolean` \| `array<string>` | 否 | `[]` | `true` = 全部工具；数组 = 工具名白名单 |
| `pub` | `boolean` \| `array<string>` | 否 | `false` | `false` = 全拒；数组 = 放行的 path 模式 |
| `sub` | `boolean` \| `array<string>` | 否 | `false` | 同上，用于出站扇出 |
| `rep` | `boolean` | 否 | `true` | 是否接受该对端的 `tool_result` |

表本身的类型是 `map<node_id, GrantEntry>`，键 `"*"` 保留为默认条目，其余键**必须**是合法 `node_id`（`[a-z0-9_-]+`）。

### 5.2 `hello` / `ack` 的 `payload.auth`（🔵）

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `scheme` | `string` | 是 | 固定 `"ed25519"`（本修订只定义这一种） |
| `nodeId` | `string` | 是 | **必须**等于 `Signal.source`，且等于证书 / 密钥绑定的身份 |
| `publicKey` | `string` | 是 | Ed25519 原始 32 字节公钥的 Base64 编码 |
| `nonce` | `string` | 是 | ≥ 16 字节随机值的十六进制编码，防重放 |
| `timestamp` | `number` | 是 | Unix 秒，用于 ±60 s 时间窗 |
| `signature` | `string` | 是 | 对 §2.4.2 定义的 `signing_bytes` 的 Ed25519 签名的 Base64 编码 |

未实现节点认证的实现**应当**忽略 `auth` 字段（[宽容读取](index.md#7-一致性)），**不得**因出现未知字段而断开连接。

### 5.3 TOFU 存储（🔵）

默认路径 `~/.msp/known_nodes.json`（与共享目录 `~/.msp/nodes/` 同级）：

```json
{
  "node_b": {
    "publicKey": "Qm9ndXNFZDI1NTE5UHVibGljS2V5MzJCeXRlc0Jhc2U2NA==",
    "firstSeen": 1791500000.0,
    "lastSeen": 1791503600.0,
    "confirmed": true
  }
}
```

`confirmed=false` 表示尚未人工确认（TOFU 首连）；`confirmed=true` 的条目遇到不同 `publicKey` **必须**拒绝连接并告警。

### 5.4 本机判定（🔵）

对端为 `uds` 后端时一律视为本机；`tcp` / `websocket` 后端的对端地址 host 属于 `127.0.0.0/8`、`::1`、`localhost` 时同样视为本机。判定**必须**基于本端已建立的连接与其对端地址。


## 6. 错误处理与边界

| 情形 | 要求 |
|---|---|
| 入站 `req` / `pub` / `rep` 未授权 | **必须**丢弃该信号（**不得**入队、**不得**起执行线程）；**可以**回一条 `error` 信号说明拒绝，**不得**回 `tool_result`——拒绝不是工具执行结果 |
| 未授权拒绝所用的 `code` | 若回 `error`，`code` **应当**取实现自定义区间 `-32000` ~ `-32099`（[README §5.4](index.md#54-错误码)），并在实现文档中说明；`message` **不得**泄露本地策略细节（如完整的工具清单或授权表内容） |
| 出站 `sub` 未授权 | 静默跳过该对端，**不得**回任何错误（发送方不应向未授权对端暴露「这里有一条你没资格看的广播」） |
| TLS 校验失败 | 连接在传输层建立失败，握手**不得**开始，**不得**登记对端 |
| 节点认证失败 / 身份不匹配 / 未认证连接的入站消息 | **必须**关闭连接；**不得**登记 `peer_id`、**不得**写入 `peer_manifests`、**不得**触发 `on_connected`、**不得**进入 `_dispatch` |
| `grants` 缺失或条目缺字段 | 按 §3.2 与 §3.5 的默认值补全；**不得**因配置缺失而放行 |
| 已知对端公钥变化 | **必须**拒绝并告警（可能的冒充）；**不得**自动接受新公钥 |
| 中间通配符的 path 模式 | `pattern_matches` 恒返回 `False`，即**静默全拒**；实现**应当**在加载时校验并报错（fail-closed） |

**边界情形**：`req: True` 是「全部工具」，包括日后新增的工具——因此**不得**用它作为临时调试的默认配置；未知 `node_id` 无对应授权条目时走 `"*"`；`"*"` 条目本身**不得**被删除后又按「无配置 = 全放行」处理。


## 7. 规范条文汇总（MUST / SHOULD 清单）

**当前位置（✅）**

1. 协议层**不得**在每条消息上做默认的加密、认证或授权校验。（§1.1）
2. 节点**应当**默认只监听 localhost；跨机暴露**必须**由部署方显式开启。（§1.2、§2.4）
3. `node_id` 冲突的解歧**必须**有确定规则（当前为字典序定规范连接方向）。（§2.4.3）

**跨机部署**：第 4–9 条（TLS / 节点认证 / 身份绑定）仍为 🔵；第 10–16 条中与**授权表**相关的部分已随 `core/grants.py` 落地（✅），与**节点认证**相关的第 16 条仍为 🔵。

4. 跨机部署**必须**同时配置 TLS、节点认证、身份绑定与授权；四者缺一即视为不符合本页。（§2.4）
5. TLS **必须**做证书链与主机名校验，**不得**在生产配置中跳过校验。（§2.4.1）
6. 节点认证**必须**双向：`hello` 与 `ack` 都**必须**携带可验证的身份证明。（§2.4.2）
7. 签名覆盖范围**必须**是包含 `manifest` 全文的规范化字节串；`nonce` **必须** ≥ 16 字节随机，`timestamp` 时间窗**必须**为 ±60 s，重复 `nonce` **必须**拒绝。（§2.4.2）
8. 已确认对端的公钥发生变化时**必须**拒绝连接并告警。（§2.4.2、§5.3）
9. `hello` / `ack` 声明的 `node_id` **必须**与证书 / 密钥身份一致；校验**必须**先于连接登记。（§2.4.3）
10. 授权**不得**依赖对端自报的能力位，`grants` **不得**随 `Manifest` 交换。（§3.1）
11. 授权检查**必须**位于 `_dispatch` 的第一条语句；任何路径**不得**绕过 `_dispatch` 直接处理对端消息。（§3.8）
12. `pub` / `sub` 的模式匹配**必须**复用 `pattern_matches`，**不得**另立算法。（§3.3）
13. `sub` 过滤**不得**改变广播报文内容，**不得**掺入带宽优化语义。（§3.6、§3.7）
14. 本机对端**应当**整张授权表绕过；本机判定**不得**依赖对端自报字段。（§3.5）
15. 未授权的 `req` **不得**进入工具执行路径；拒绝**不得**以 `tool_result` 形式返回。（§6）
16. 未实现节点认证的实现**应当**忽略 `auth` 字段而不断开连接。（§5.2）
17. 模式私有信号**必须**由注册的模式显式声明授权归属，**不得**兜底放行；扩展点的默认实现**必须**是拒绝。（§3.9）
18. 事务归属**必须**按连接身份判定，**不得**用对端自报的 `Signal.source`；读方向与写方向的来源校验**必须**对称。（§3.10）


## 8. 安全考量

- **`node_id` 冒充的连锁反应**：冒充 → 发现注册表污染（声明文件以 `node_id` 命名）→ 去重紊乱（规范连接方向由 `node_id` 序决定）→ 流量被引向攻击者。身份绑定（§2.4.3）是唯一在协议层可判定的收口点。
- **广播的信息泄露面**：`publish` 默认扇出到所有已连对端，任何一条广播都可能被第三方节点旁观。跨机部署下**应当**按敏感度拆分域前缀（如把敏感通知放在独立域），因为 `sub` 过滤只在**发送方**生效——发送方必须事先知道谁能看。
- **工具执行 = 任意代码执行入口**：注册一个工具等于对外暴露一个可被调用的函数，其内部可触达文件系统、网络与进程。授权表（`req` 白名单）是**唯一**闸门；因此 `req` 的默认值**必须**是空列表。
- **UDS 的 `0o600`**：`UDSTransport.listen` 把 socket 文件权限收紧到仅本用户可连，与「本机同用户全量信任」一致（✅）。清理残留时只删除 `stat.S_ISSOCK` 类型的文件（`_unlink_stale`），防误删普通文件——实现**不得**改成无条件 `unlink`。
- **资源路径与 URI 越权（roots）**：`resources` / `roots` 面（🔵，见 [capabilities.md](./capabilities.md)）一旦实现，URI **必须**在服务端做根目录约束（前缀规范化 + `..` 拒绝），**不得**把授权完全交给调用方声明。
- **大对象 `blob_ref` 的完整性**：`blob_ref.checksum` 是对内容的校验和，接收方**应当**在拼接完成后校验；缺失或不匹配时**应当**拒绝使用该对象，而不是降级为「信任长度字段」。`size` 与 `checksum` 均为**提示性**字段，**不得**作为内存预分配的唯一下界（[transports.md](./transports.md) 的 16 MiB 消息上限才是硬边界）。
- **~~握手无读超时（DoS 面）~~ ✅ 已修复**：`handshake_outbound` / `handshake_inbound` 的 `receive()` 现受 `handshake_timeout`（默认 10 s）约束，对端 accept 了 TCP 却永不回 `ACK` 时会超时关闭连接，不再永久占用连接线程（见 §9）。节点认证的握手前置校验**应当**沿用同一超时。
- **`rep` 的伪造面**：放行 `rep` 意味着对端**可以**发送任意 `tool_result`；本地只按 `reqid` 匹配，未在 `pending_calls` 中的结果被忽略。因此 `reqid` **应当**保持不可预测（`Signal.new_reqid()` 为 16 位十六进制）；**不应当**使用自增序号式的 `reqid`，否则已授权的对端可以按序猜中并注入伪造结果（参考实现中 `msp/multi-round` 的 `mr-<n>` 即属此列，见 §9）。
- **虚假安全的反向风险**：给出一个默认全放行、又宣称「支持授权」的实现，比明确声明「不做授权」更危险。实现若未落实本节条文，**应当**在文档中明确声明，而不是留一个可被误解的配置项。


## 9. 已知缺口

1. ~~**授权检查尚未实现**~~：✅ 已实现——`core/grants.py` 解析授权表，`MSPProtocol.authorized()` 是 `_dispatch` 的第一条语句，`grant_sub()` 在扇出时过滤，`_reject()` 丢弃未授权信号（带 `reqid` 时回 `error`，`code = -32000`）。两点仍然成立：它**不覆盖模式私有信号**（见第 6 条），且授权表的落点是节点配置而非 `Preset`——§3.2 已按实现把「落点」放宽为规范性无关项。
2. **TLS / 节点认证 / 身份绑定尚未实现**：协议层无相关代码；`WebSocketTransport` 只接受 `ws://`，无 TLS 支持。
3. **跨机监听没有配置入口**：`TransportRegistry.listen_all()` 以 `transport.listen({})` 调用后端，而 `TCPTransport.listen` / `WebSocketTransport.listen` 的 host 默认 `127.0.0.1`；节点级 `config` 只支持 `connect_backoff` / `discovery` / `presence`，**当前无法只靠配置监听 `0.0.0.0`**——需要改传输层或注册表。
4. ~~**握手无读超时**~~：✅ 已修复——`handshake_timeout`（默认 10 s）配合 `Connection.set_read_timeout()`，超时即关闭连接并计为不可达。
5. **`pub` / `sub` 无「单模式全量放行」写法**：`pattern_matches` 要求通配符带前缀，裸 `*` / `**` 匹配不到任何 path；全量放行只能逐一列举域前缀。
6. ~~**模式私有信号不在授权表管辖内**~~：✅ **已定义并实现**。协议层对「非核心类型」不再兜底放行，而是交给**注册的模式**自己声明归属（`PatternHandler.authorize`，**默认拒绝**），映射表见 §3.9。`task_submit` 走 `req`（`payload.task` 视同工具名做精确匹配）、`task_query` / `task_cancel` 要求该对端有任意 `req` 权利、其余 `task_*` 与 `input_*` 走 `rep`。**新增信号类型必须显式归类，未归类即拒绝。**
7. **`msp/multi-round` 的 `reqid` 可预测**：`_next_reqid()` 返回 `mr-<自增计数>`，配合 `rep` 放行会留下伪造 `tool_result` 的注入面。
8. **`error` 信号的 `code` 用法不统一**：参考实现目前只在两种情形发码——「未知信号类型」用 `-32600`，**授权拒绝**用 `-32000`（且仅当信号带 `reqid`；广播类没有可回的错误对象，静默丢弃）。[README §5.4](index.md#54-错误码) 中的 `-32601` / `-32602` / `-32603` 在协议核心中**从未**被发出（仅存在于 `msp/mcp/jsonrpc.py` 的 JSON-RPC 桥），工具失败一律作为字符串放进 `tool_result.payload.error`。
9. **UDS 仅 Linux / macOS**：Windows 的 Python 未暴露 `socket.AF_UNIX`，`listen()` / `connect()` 抛 `RuntimeError`；Windows 上 `0o600` 与 socket 文件语义均不可用。


## 10. 参考实现映射

| 条文 | 状态 | 源码文件与符号 |
|---|---|---|
| 信任边界 = 传输可达（无授权分支） | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._dispatch`、`_dispatch_core` |
| 连接登记与 `node_id` 去重 | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._finish_handshake` |
| 握手报文（`payload.manifest`） | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `handshake_inbound` |
| 握手读超时 | ✅ 已修复 | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `handshake_outbound` / `_receive_handshake`；[src/msp/transport/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/base.py) `Connection.set_read_timeout` |
| 默认只监听 localhost | ✅ | [src/msp/transport/tcp.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/tcp.py) `TCPTransport.listen`；[src/msp/transport/websocket.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/websocket.py) `WebSocketTransport.listen` |
| 监听地址无配置入口 | ✅（缺口） | [src/msp/transport/registry.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/registry.py) `TransportRegistry.listen_all` |
| UDS `0o600` 与 socket 误删防护 | ✅ | [src/msp/transport/uds.py](https://github.com/hxh230802/MSP/blob/master/src/msp/transport/uds.py) `UDSTransport.listen`、`UDSTransport._unlink_stale` |
| 路径模式匹配（`pub` / `sub` 复用） | ✅ | [src/msp/protocol/matcher.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/matcher.py) `pattern_matches` |
| 广播扇出（`sub` 过滤的插入点） | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.publish` |
| 本地回调匹配（`pub` 过滤的插入点） | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol._on_signal` |
| `reqid` 生成 | ✅ | [src/msp/core/signal.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/signal.py) `Signal.new_reqid`；[src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `MultiRoundHandler._next_reqid` |
| 授权表 `grants` | ✅ | [src/msp/core/grants.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/grants.py) `grants_from_json` / `grants_for` / `is_local_host`；[src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.authorized` / `grant_sub` / `_reject`；[src/msp/core/node.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/node.py) `config["grants"]` → `MSPProtocol(grants=...)`；[src/msp/core/exposure.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/exposure.py) `exposure_warning` |
| TLS / 节点认证 / 身份绑定 | 🔵 | 无（规划中；拟落于传输包装与握手前置校验） |
| 模式私有信号的授权归属 | ✅ | [src/msp/patterns/base.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/base.py) `PatternHandler.authorize`（默认拒绝）；[src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `MSPProtocol.authorized` 的 `_AUTHORIZATION_FREE_TYPES` 与模式委派；[src/msp/patterns/task.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) / [src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) 的 `authorize` |
| 写方向的来源校验 | ✅ | [src/msp/patterns/task.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/task.py) `TaskHandler._write_from_executor`（`_on_status` / `_on_artifact` / `_on_result` / `_on_input_required`）；[src/msp/patterns/multi_round.py](https://github.com/hxh230802/MSP/blob/master/src/msp/patterns/multi_round.py) `_on_tool_result` / `_on_input_required` / `_on_input_response` |
| 对端清单归一（外来输入） | ✅ | [src/msp/protocol/protocol.py](https://github.com/hxh230802/MSP/blob/master/src/msp/protocol/protocol.py) `_sanitize_peer_manifest`（握手与 `manifest_update` 两处入口）；[src/msp/core/grants.py](https://github.com/hxh230802/MSP/blob/master/src/msp/core/grants.py) `normalize_grants` |

**相关页面**：[规范索引](index.md) · [base-protocol](./base-protocol.md#4-连接生命周期) · [transports](./transports.md) · [discovery](./discovery.md) · [patterns/publish-subscribe](./patterns/publish-subscribe.md) · [capabilities](./capabilities.md) · [设计文档 §安全模型](../designs.md) · [技术白皮书 §6](https://github.com/hxh230802/MSP/blob/master/docs/whitepaper.md)
