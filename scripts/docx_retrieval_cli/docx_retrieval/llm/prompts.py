from __future__ import annotations

EXPAND_PROMPT_VERSION = "docx_expand_v2"
SUMMARY_PROMPT_VERSION = "docx_summary_v2"


def expand_prompt(node_id: str, title: str, start_anchor: str, end_anchor: str, items_text: str) -> str:
    return f"""你正在把一个过长的 DOCX 合同 node 拆成更小的子 node。

当前 node:
- node_id: {node_id}
- title: {title}
- anchor range: {start_anchor} - {end_anchor}

下面是当前 node 范围内的段落和表格。每一项前面的方括号是 anchor:
{items_text}

任务：
找出这些内容中真实出现、可以作为子 node 起点的标题。

判断规则：
- 只能使用原文中实际出现的标题，不得改写、概括或编造。
- 标题可以是“第一条”“一、”“（一）”“1、”“1.”“1.1”“附件：”“其他。”等形式。
- 表格列名、表格行名、正文交叉引用、普通句子不能作为标题。
- 不要返回当前 node 自己的标题。
- 如果没有可拆分的子标题，返回空数组。
- anchor 必须来自上面方括号中的 anchor。
- level_hint 表示相对层级：1 是本 node 下的最高子层级，2/3 表示更低层级；不确定时填 null。

输出规范：
- 必须只返回一个合法 JSON object。
- 不要返回 Markdown。
- 不要返回解释。
- 不要返回纯文本。
- 不要添加 schema 以外的字段。
- JSON 必须严格符合：
{{
  "subsections": [
    {{"anchor": "p_0001", "title": "标题原文", "level_hint": 1}}
  ]
}}"""


def summary_prompt(title: str, node_type: str, content: str) -> str:
    return f"""你正在为合同结构树中的一个 node 生成检索摘要。

node 标题：{title}
node 类型：{node_type}

内容：
{content}

摘要要求：
- 使用中文。
- 只概括本 node 的主要内容，不添加原文没有的信息。
- 重点保留合同审查相关信息，例如主体、金额、期限、付款、发票、验收、违约、附件等。
- 摘要长度控制在 80 到 160 个中文字符。

输出规范：
- 必须只返回一个合法 JSON object。
- 不要返回 Markdown。
- 不要返回解释。
- 不要返回纯文本。
- 不要添加 schema 以外的字段。
- JSON 必须严格符合：
{{"summary": "摘要内容"}}"""
