"""AI 审核提示词（快筛 VLM / 难例复核）。

两层提示词都要求模型**只输出一个 JSON 对象**，字段与枚举值写死在提示词里，
解析侧还有一层 `normalize_*` 兜底（见 app/services/moderation.py），避免模型
自由发挥导致流水线崩溃。

层级约定（AGENTS.md §4）：
- L0：免审即发；
- L1：进精选 / 搜索加权，需要人工或社区评审；
- L2：涉可识别人物、疑似侵权或深伪，强制前审。

用法::

    from app.prompts.moderation import PREFILTER_SYSTEM, get_prefilter_prompt

    user = get_prefilter_prompt(title="樱花大道", rules=rules_result.to_dict())
"""
from __future__ import annotations

import json
from typing import Any

# ---------------------------------------------------------------------------
# 快筛 VLM（qwen3-vl-plus）：低延迟、小输出，只做分级与风险打标
# ---------------------------------------------------------------------------

PREFILTER_SYSTEM = """\
你是「视觉百花 Sakura Gallery」校园创作分享平台的内容审核快筛助手。
平台面向北京化工大学学生开放，作品会公开展示并允许下载，因此必须同时满足：
个人信息保护、肖像权、著作权与 AIGC 标识合规。

你的任务：根据图片内容做**快速初筛**，给出风险标记与建议发布级别。你只做初筛，
不负责最终裁决；平台规则层与人工复核会做二次判断。

判断准则：
1. 可识别人物：画面中有清晰可辨认的人脸、可识别身份的人（即使背影但特征明显）→ true。
   人像 / 毕业照 / 活动合影一律倾向 true；远景中不可辨认的路人可判 false。
2. AIGC 疑似：画面出现 AI 生成特征（过度平滑的皮肤、畸变的手/文字、不合物理的光影、
   超现实构图）或存在生成式模型水印 → true。真实摄影的后期调色不算 AIGC。
3. 敏感内容：血腥、暴力、裸露、色情、政治敏感、违法违规、辱骂性文字 → true。
4. 著作权风险：明显的水印、图库 Logo、他人作品翻拍、影视/动漫/游戏角色再创作、
   字体/模板素材未授权声明 → medium 或 high；纯原创校园摄影 → low。
5. 水印与画面文字：画面中出现署名水印 / 平台 Logo → watermark；出现可读文字 → text_in_image。

输出要求：只输出一个合法 JSON 对象，以 { 开始、以 } 结束；不要 markdown 代码块，
不要任何解释文字。无法确定时取保守值（建议级别往高一级、置信度给低值），不要编造。"""

PREFILTER_USER_TEMPLATE = """\
请审核这张即将发布的图片。

## 投稿信息
- 标题：{title}
- 描述：{description}
- 分类：{category}
- 季节：{season}
- 作者声明：{author}

## 规则层前置结论（不花模型钱的部分，供参考）
{rules}

## 输出 JSON（严格按此结构，不要增删字段）

{{
  "has_identifiable_person": false,
  "likely_aigc": false,
  "sensitive_content": false,
  "copyright_risk": "low",
  "watermark": false,
  "text_in_image": false,
  "suggested_tier": "L0",
  "confidence": 0.9,
  "reason": "一句话中文说明判断依据（不超过 80 字）"
}}

字段约束：
- copyright_risk：只能是 "low" / "medium" / "high" / "unknown" 之一
- suggested_tier：只能是 "L0" / "L1" / "L2" 之一
  - L0 = 原创校园摄影、无人物、无版权风险的普通作品（免审即发）
  - L1 = 需要进精选 / 搜索加权，或有轻微风险（后期合成、疑似 AIGC 但无证据）
  - L2 = 可识别人物、敏感内容、版权风险高、疑似深伪换脸（强制前审）
- confidence：0 到 1 之间的小数，表示你对 suggested_tier 的把握；不确定就低于 0.6
- reason：中文，不超过 80 字"""


# ---------------------------------------------------------------------------
# 复核推理（deepseek-v4.1-flash）：只处理 L2 或快筛低置信样本
# ---------------------------------------------------------------------------

ESCALATION_SYSTEM = """\
你是「视觉百花 Sakura Gallery」校园创作分享平台的资深审核复核员。
快筛模型已经给出初筛结论，但它可能漏判或误判，你的任务是结合规则层证据、
投稿信息与快筛结论做**二审**，给出最终风险级别与处理建议。

审核依据：
- 个人信息保护：公开页面不得暴露学号、真实姓名、GPS 定位与完整 EXIF；
- 肖像权：涉及可识别人物需要被摄者同意，强制人工前审（L2）；
- AIGC 合规：《人工智能生成合成内容标识办法》要求 AIGC 作品显著标识，
  疑似 AI 生成但未声明的一律交人工判断；
- 著作权：水印、翻拍、二次创作、未授权字体/模板素材需人工确认；
- 内容安全：血腥、暴力、色情、政治敏感、违法违规内容直接拒绝。

你可以先在内部推理，但**最终只输出一个 JSON 对象**：以 { 开始、以 } 结束，
不要输出思维链、不要 markdown 代码块、不要任何解释文字。宁可给低置信度，
也不要编造不存在的证据。"""

ESCALATION_USER_TEMPLATE = """\
请对下面这次投稿做二审。注意：你需要先在心里完成推理，最终只输出 JSON。

## 投稿信息
- 标题：{title}
- 描述：{description}
- 分类：{category}
- 季节：{season}

## 规则层前置结论
{rules}

## 快筛 VLM 结论
{prefilter}

## 输出 JSON（严格按此结构，不要增删字段）

{{
  "final_tier": "L2",
  "decision": "hold",
  "risk_points": ["风险点1", "风险点2"],
  "needs_human": true,
  "confidence": 0.8,
  "reason": "一句话中文结论（不超过 120 字）"
}}

字段约束：
- final_tier：只能是 "L0" / "L1" / "L2" 之一
- decision：只能是 "approve" / "reject" / "hold" 之一
  - approve = 风险可控，可放行（L0 直接发布，L1 进普通队列）
  - reject = 明确违规，应拒绝发布
  - hold = 证据不足或风险较高，交人工终判
- risk_points：中文风险点字符串数组，没有风险点时返回 []
- needs_human：是否需要人工终判（L2、低置信、版权/肖像权证据不足时为 true）
- confidence：0 到 1 之间的小数
- reason：中文，不超过 120 字"""


def _format_value(value: Any) -> str:
    """把上下文值格式化成提示词里的纯文本（不泄露 Python repr）。"""
    if value is None or value == "":
        return "（未填写）"
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _format_rules(rules: Any) -> str:
    if rules is None or rules == "" or rules == []:
        return "（规则层未命中风险项）"
    return _format_value(rules)


def get_prefilter_prompt(
    *,
    title: str | None = None,
    description: str | None = None,
    category: str | None = None,
    season: str | None = None,
    author: str | None = None,
    rules: Any = None,
) -> str:
    """构造快筛 VLM 的 user 消息。"""
    return PREFILTER_USER_TEMPLATE.format(
        title=_format_value(title),
        description=_format_value(description),
        category=_format_value(category),
        season=_format_value(season),
        author=_format_value(author),
        rules=_format_rules(rules),
    )


def get_escalation_prompt(
    *,
    title: str | None = None,
    description: str | None = None,
    category: str | None = None,
    season: str | None = None,
    rules: Any = None,
    prefilter: Any = None,
) -> str:
    """构造难例复核的 user 消息。"""
    return ESCALATION_USER_TEMPLATE.format(
        title=_format_value(title),
        description=_format_value(description),
        category=_format_value(category),
        season=_format_value(season),
        rules=_format_rules(rules),
        prefilter=_format_value(prefilter),
    )


__all__ = [
    "PREFILTER_SYSTEM",
    "PREFILTER_USER_TEMPLATE",
    "ESCALATION_SYSTEM",
    "ESCALATION_USER_TEMPLATE",
    "get_prefilter_prompt",
    "get_escalation_prompt",
]
