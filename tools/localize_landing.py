"""由英文 landing 生成中文版 landing/zh/index.html。

     python tools/localize_landing.py

为什么不做成运行时的 JS 换词：静态两页各有独立 URL、可被搜索引擎与分享链接区分，
也不用担心脚本没加载导致页面半英半中。代价是改英文页时要同步跑一次这个脚本。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EN = ROOT / "landing" / "index.html"
ZH = ROOT / "landing" / "zh" / "index.html"

# (英文原文, 中文)
PAIRS = [
    # 顶栏
    (">What is MSP<", ">MSP 是什么<"),
    (">Capabilities<", ">能力<"),
    (">Philosophy<", ">设计哲学<"),
    (">Start building<", ">开始构建<"),
    (">Documentation<", ">文档<"),
    (">Implementations<", ">实现<"),
    # Hero
    ("Open protocol · MIT · alpha", "开放协议 · MIT · alpha"),
    (
        "      Local software should be a <strong>neighbour</strong>, not a socket.\n"
        "      MSP gives every process a lease so its presence is a fact you can read,\n"
        "      a way to speak up when something changes, and the ability to serve its\n"
        "      peers directly instead of routing every step through a model.",
        "      本地软件应该是一个<strong>邻居</strong>，而不是一个插座。\n"
        "      MSP 给每个进程一份租约，让「它还在」变成随时可读的事实；让有变化时它自己能开口；\n"
        "      也让节点之间直接互相服务，而不是每一步都绕着模型走一圈。",
    ),
    (">Read the docs<", ">读文档<"),
    (
        "solid blue = our own connection · green = reported by a peer ·\n"
        "        dashed = inferred · hollow = known, not connected",
        "蓝色实线 = 我们自己的连接 · 绿色 = 对端自报 · 虚线 = 推断 · 空心 = 已知但未连",
    ),
    # What is MSP
    ("<h2>What is MSP?</h2>", "<h2>MSP 是什么？</h2>"),
    (
        "      MSP is a small wire protocol (8 fixed top-level fields, 4-byte length framing) that lets\n"
        "      processes on a machine — or across a LAN — discover each other, call each other's tools, and\n"
        "      broadcast events. A node announces itself with a <em>lease</em>; a crashed node simply\n"
        "      disappears when the lease goes stale. There is no central broker and no configuration file to\n"
        "      maintain: presence is observed, not declared.",
        "      MSP 是一个很小的线协议（8 个固定顶层字段 + 4 字节长度前缀），让同一台机器——或同一个\n"
        "      局域网——上的进程互相发现、互相调用工具、互相广播事件。节点用<em>租约</em>宣告自己；\n"
        "      进程崩了，租约过期它自己就消失。没有中心 broker，也没有需要维护的配置文件：\n"
        "      存在是观测出来的，不是声明出来的。",
    ),
    ("<h3>Presence, not config</h3>", "<h3>存在，不是配置</h3>"),
    (
        '<p>A node writes a declaration and renews it. Anything not renewed within 30 s is\n'
        '        ignored, so "what is running right now" is a fact you can read at any moment.</p>',
        "<p>节点写一份声明并持续续租。超过 30 秒没续租就视为失效，"
        "所以「现在有什么在跑」是随时可读的事实。</p>",
    ),
    ("<h3>Push, not poll</h3>", "<h3>推送，不是轮询</h3>"),
    (
        "<p>Events happen inside the app, not inside the model's question. Nodes broadcast on a\n"
        "        path; subscribers are woken instead of polling for changes.</p>",
        "<p>事件发生在应用里，而不是发生在模型的提问里。节点按路径广播，"
        "订阅者被唤醒，而不是反复去问。</p>",
    ),
    ("<h3>Peers, not a hub</h3>", "<h3>对等，不是总机</h3>"),
    (
        "<p>Nodes can serve each other directly. The agent is one participant in the mesh, not the\n"
        "        switchboard every message has to cross.</p>",
        "<p>节点可以直接互相服务。agent 只是网里的一个参与者，"
        "不是每条消息都必须经过的总机。</p>",
    ),
    # Capabilities
    ("<h2>What can it enable?</h2>", "<h2>它能带来什么？</h2>"),
    ("<h3>Long tasks that finish themselves</h3>", "<h3>会自己完成的长任务</h3>"),
    (
        "<p>Start a download, wait on a completion signal with polling as a fallback, and get\n"
        "        called back when it lands — the call blocks briefly, then becomes a card you can walk\n"
        "        away from.</p>",
        "<p>发起一个下载，以完成信号为主、轮询兜底；落地时被回调。"
        "调用先短暂阻塞，然后变成一张可以走开的卡片。</p>",
    ),
    ("<h3>Apps that know each other exist</h3>", "<h3>应用知道彼此存在</h3>"),
    (
        "<p>A downloader hands a finished file to an editor without the model relaying the\n"
        "        handoff, because both are nodes in the same mesh.</p>",
        "<p>下载器把完成的文件交给编辑器，不需要模型在中间转手——"
        "因为两者本来就是同一张网里的节点。</p>",
    ),
    ("<h3>Devices on the same footing</h3>", "<h3>设备与软件同等</h3>"),
    (
        "<p>An ESP32 with six tools and a desktop app are the same kind of thing: a node with a\n"
        "        manifest.</p>",
        "<p>一块带六个工具的 ESP32，和一个桌面应用是同一种东西：一个带 manifest 的节点。</p>",
    ),
    ("<h3>Attention routing</h3>", "<h3>注意力路由</h3>"),
    (
        "<p>When something needs a human — approval, a question, a finished job — the network can\n"
        "        say so, and the agent decides whether to notify or stay quiet.</p>",
        "<p>需要人时——等确认、在提问、任务完成——网络能说出来，由 agent 决定提醒还是安静。</p>",
    ),
    # Philosophy
    ("<h2>Design philosophy</h2>", "<h2>设计哲学</h2>"),
    (
        "      Three sentences. Everything else in the protocol is a consequence of them — and so is every\n"
        "      limitation we admit to.",
        "      三句话。协议里的其它一切由它们推出——我们承认的每条局限也是。",
    ),
    ("<h3>Everything is a node.</h3>", "<h3>万物皆节点。</h3>"),
    (
        "          A downloader, an editor, an ESP32 with six tools, the agent itself — the same kind of\n"
        "          thing: a lease, a manifest, tools, signals. There is no privileged participant and no\n"
        "          broker to configure, so two applications can serve each other without asking the model\n"
        "          for permission.",
        "          下载器、编辑器、带六个工具的 ESP32、agent 自己——都是同一种东西："
        "租约、清单、工具、信号。没有特权参与者，也没有要配置的总线，"
        "所以两个应用可以直接互相服务，不必向模型请示。",
    ),
    ("<h3>Everything is a signal.</h3>", "<h3>万物皆信号。</h3>"),
    (
        "          One packet shape carries tool calls, results, broadcasts and heartbeats alike. That is\n"
        '          why an event can be pushed instead of polled: nothing in the wire format privileges\n'
        '          "request". It is also why nothing is retained — a signal that nobody was listening for is\n'
        "          gone, and we say so instead of pretending otherwise.",
        "          一种报文形状同时承载工具调用、结果、广播、心跳。正因为线格式不把「请求」当特权，"
        "事件才能推而不必轮询；也正因为如此什么都不留存——没人听的信号就是丢了，"
        "我们明说，而不是假装没有。",
    ),
    ("<h3>Every layer is extensible.</h3>", "<h3>每层皆可扩展。</h3>"),
    (
        "          Eight fixed fields and a four-byte length prefix; discovery, presence, transports,\n"
        "          patterns and authorisation all plug in behind that. A small core is the only way a\n"
        "          protocol can survive use cases it did not anticipate — including yours.",
        "          8 个固定字段 + 4 字节长度前缀；发现、存在、传输、模式、授权全部挂在后面。"
        "小内核是唯一能让协议活过它没预想到的用法的办法——包括你的用法。",
    ),
    (
        "      What the three sentences cost: no retention, no gossip, and trust equal to reachability.\n"
        "      That is written down, not discovered later — see",
        "      三句话的代价：没有留存、没有 gossip、可达即信任。"
        "这些是写下来的，不是以后才发现的——见",
    ),
    (">the positioning document<", ">定位文档<"),
    # Start building
    ("<h2>Start building</h2>", "<h2>开始构建</h2>"),
    ("<h3>Run a node that offers a tool</h3>", "<h3>起一个提供工具的节点</h3>"),
    ("<h3>Discover it and call it</h3>", "<h3>发现它并调用</h3>"),
    (
        "<h3>Publish a signal — and receive it elsewhere</h3>",
        "<h3>发布一个信号，在别处收到</h3>",
    ),
    (
        '        Signals are fire-and-forget: nothing is retained and a subscriber that was offline missed\n'
        '        it. Treat a signal as <em>"something changed"</em> and fetch the state with a tool.',
        "        信号是发完即忘的：没有留存，订阅者离线期间发的那条就永远丢了。"
        '把信号当成 <em>「有东西变了」</em>，状态用工具回查。',
    ),
    (
        "      Install: <code>pip install --pre msp-py</code> · the same protocol is implemented in\n"
        "      TypeScript, C++ and .NET.",
        "      安装：<code>pip install --pre msp-py</code> · 同一协议也有 TypeScript、C++、.NET 实现。",
    ),
    # Implementations
    ("<h2>Implementations</h2>", "<h2>实现</h2>"),
    ("<h3>Python · reference</h3>", "<h3>Python · 参考实现</h3>"),
    (
        "<p><code>msp-py</code> on PyPI, 0.1.0a1. The semantics every other implementation is\n"
        "        measured against.</p>",
        "<p>PyPI 上的 <code>msp-py</code>，0.1.0a1。其它实现都以它的语义为准。</p>",
    ),
    (
        "<p>Zero dependencies, Node ≥ 22.6, byte-level interop with <code>msp-py</code>.</p>",
        "<p>零依赖，Node ≥ 22.6，与 <code>msp-py</code> 逐字节互通。</p>",
    ),
    (
        "<p>Every MSP node's tools become agent tools, long tasks and notifications included.</p>",
        "<p>把每个 MSP 节点的工具变成 agent 工具，含长任务与通知。</p>",
    ),
    (
        "C++ and .NET live in the same organisation; both are private for now.",
        "C++ 与 .NET 也在同一个组织下，暂时是私有仓库。",
    ),
    (
        "Full guide, versioned by protocol revision (2026-10-10 · latest): ",
        "完整文档，按协议修订号分版本（2026-10-10 · latest）：",
    ),
    (">documentation<", ">文档<"),
    # 对比表
    ("<h2>MSP is not MCP</h2>", "<h2>MSP 不是 MCP</h2>"),
    (
        "<td>Topology</td><td>hub-and-spoke: the model is the centre</td><td>mesh: nodes are peers</td>",
        "<td>拓扑</td><td>hub-and-spoke：模型是中心</td><td>网状：节点对等</td>",
    ),
    (
        "<td>Direction</td><td>pull</td><td>pull and push</td>",
        "<td>方向</td><td>拉</td><td>拉与推</td>",
    ),
    (
        "<td>Presence</td><td>an entry in a config file</td><td>a lease you can read</td>",
        "<td>存在</td><td>配置文件里的一条记录</td><td>一份可读的租约</td>",
    ),
    (
        "<td>Lifetime</td><td>one call, one session</td><td>long-lived, with heartbeat</td>",
        "<td>生命周期</td><td>一次调用一个会话</td><td>长驻，带心跳</td>",
    ),
    (
        "<td>App to app</td><td>through the model</td><td>directly</td>",
        "<td>应用之间</td><td>经过模型</td><td>直接</td>",
    ),
    (
        '      <a href="docs/latest/why-not-mcp/">The long version</a>\n'
        "      explains the trade-off, including what choosing MSP costs us.",
        '      <a href="docs/latest/why-not-mcp/">完整论述</a>解释了这些取舍，'
        "包括选择 MSP 要付什么代价。",
    ),
    # 页脚
    (
        "<p>Copyright © MSP — Model Sensing Protocol. MIT licensed.</p>",
        "<p>Copyright © MSP — Model Sensing Protocol，MIT 许可。</p>",
    ),
    (
        "<p>Site content is documentation, not a specification; the normative text lives in the repository.\n"
        '      Terms, trademark and project policies: <a href="https://github.com/ModelSensingProtocol/msp-site/blob/main/LICENSE">LICENSE</a>.</p>',
        "<p>本站内容是文档，不是规范；规范性文本在仓库里。条款与项目政策见\n"
        '      <a href="https://github.com/ModelSensingProtocol/msp-site/blob/main/LICENSE">LICENSE</a>。</p>',
    ),
]

HEAD_PAIRS = [
    ('<html lang="en">', '<html lang="zh-CN">'),
    (
        "<title>Model Sensing Protocol — every local app is a neighbour</title>",
        "<title>Model Sensing Protocol — 本地软件是邻居，不是插座</title>",
    ),
    (
        'content="MSP is an open protocol where local software becomes a neighbour, not a socket: '
        'leases for presence, push for change, and nodes that serve each other directly."',
        'content="MSP 是一个开放协议：让本地软件成为邻居而不是插座——'
        '用租约表达存在、用推送表达变化、让节点之间直接互相服务。"',
    ),
    ('href="style.css"', 'href="../style.css"'),
    ('href="assets/', 'href="../assets/'),
    ('src="assets/', 'src="../assets/'),
    (
        '<a class="gh" href="https://github.com/ModelSensingProtocol/msp-site" target="_blank" rel="noreferrer">GitHub</a>',
        '<a class="lang" href="../" hreflang="en">EN</a>\n'
        '    <a class="gh" href="https://github.com/ModelSensingProtocol/msp-site" target="_blank" rel="noreferrer">GitHub</a>',
    ),
    ('href="docs/latest/', 'href="../docs/latest/'),
]


def main() -> None:
    source = EN.read_text(encoding="utf-8")
    zh = source
    missing: list[str] = []

    # 前缀类替换要全量（href="docs/latest/ 出现多次），其余只替换一次
    BULK = ('href="assets/', 'src="assets/', 'href="docs/latest/',
            '>Start building<', '>Documentation<', '>What is MSP<', '>Capabilities<')
    for old, new in HEAD_PAIRS + PAIRS:
        if old not in zh:
            missing.append(old[:60])
            continue
        zh = zh.replace(old, new) if old in BULK else zh.replace(old, new, 1)

    # 语言切换：英文页那个「中文」链接要翻成指回英文站的 EN 链接，且只留一个
    zh = zh.replace(
        '    <a class="lang" href="zh/" hreflang="zh-CN">中文</a>\n'
        '    <a class="lang" href="../" hreflang="en">EN</a>',
        '    <a class="lang" href="../" hreflang="en">EN</a>',
        1,
    )
    zh = zh.replace(
        '<link rel="alternate" hreflang="zh-CN" href="zh/">',
        '<link rel="alternate" hreflang="en" href="../">',
        1,
    )

    # 前缀批量替换会先改掉 href，导致上面那条整句匹配不上，这里按改后的形态再补一次
    POST_PAIRS = [
        (
            '      <a href="../docs/latest/why-not-mcp/">The long version</a>\n'
            "      explains the trade-off, including what choosing MSP costs us.",
            '      <a href="../docs/latest/why-not-mcp/">完整论述</a>解释了这些取舍，'
            "包括选择 MSP 要付什么代价。",
        ),
    ]
    for old, new in POST_PAIRS:
        if old in zh:
            zh = zh.replace(old, new, 1)
        else:
            missing.append("[post] " + old[:50])

    ZH.parent.mkdir(parents=True, exist_ok=True)
    ZH.write_text(zh, encoding="utf-8")

    if missing:
        print(f"  {len(missing)} 条没匹配上（英文页可能改过）：")
        for item in missing:
            print("   -", item)
    else:
        print("  全部替换成功")


if __name__ == "__main__":
    main()
