from __future__ import annotations

from app.catalog import load_catalog
from app.schemas import Goal, MealContext, UserProfile

GOAL_LABELS = {
    Goal.FAT_LOSS: "减脂",
    Goal.MUSCLE_GAIN: "增肌",
    Goal.MAINTAIN: "维持",
}
CONTEXT_LABELS = {
    MealContext.PRE_WORKOUT: "练前",
    MealContext.POST_WORKOUT: "练后",
    MealContext.REST_DAY: "非训练日",
    MealContext.SNACK: "加餐",
}


def build_meal_prompt(profile: UserProfile) -> str:
    supported = "、".join(record.name for record in load_catalog())
    return f"""
你是一名严谨、诚实的健身饮食助手。请观察这张单餐餐盘图片，结合用户信息给出结构化评估。

用户信息：
- 身高：{profile.height_cm:.0f} cm
- 体重：{profile.weight_kg:.1f} kg
- 体脂率：{f"{profile.body_fat_pct:.1f}%" if profile.body_fat_pct is not None else "未提供"}
- 目标：{GOAL_LABELS[profile.goal]}
- 本餐情境：{CONTEXT_LABELS[profile.context]}
- 餐盘直径参考：{profile.plate_diameter_cm:.0f} cm

项目支持的常见食材：{supported}。

反馈原则：
1. 只描述图片中能够合理观察到的食物，不要凭空补充。
2. 分量和营养均为估算；必须使用区间或“约”，不能假装精确。
3. 热量超标、蛋白质不足或碳水占比偏高必须直接指出，但不得羞辱用户。
4. 不使用“失败”“白练”“超标可耻”等表达。
5. 至少给一个下一餐可以立即执行的最小调整，不鼓励补偿性节食。
6. 强调单顿不决定长期结果，同时不软化当前事实。
7. 不构成医疗或营养建议。

只返回一个合法 JSON 对象，不要使用 Markdown 代码块，不要附加解释。结构必须为：
{{
  "foods": [
    {{
      "name": "食物中文名",
      "confidence": 0.0,
      "bbox": [x, y, width, height],
      "estimated_grams": [最小值, 最大值],
      "nutrition": {{"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0}},
      "note": "该食物分量的估算依据与不确定性"
    }}
  ],
  "advice": ["一条或多个最小可执行建议"],
  "long_term_note": "长期视角提醒",
  "disclaimer": "仅供学习参考，不构成医疗或营养建议。",
  "warnings": ["识别不确定项"]
}}

字段要求：
- confidence 取 0 到 1。
- bbox 使用归一化 [x, y, width, height]，无法定位时为 null。
- estimated_grams 使用 [最小克数, 最大克数]，无法估算时仍给合理区间。
- nutrition 是该食物上述估算分量对应的数值，不是每 100 克数值。
- 最多列出 12 种主要食物；不要把同一食物重复计数。
""".strip()


def build_repair_prompt(raw_response: str, error: str) -> str:
    return f"""
上一次输出无法通过 JSON 结构校验。请只修复格式和缺失字段，不改变图片观察结论。
校验错误：{error}

需要修复的内容：
{raw_response[:6000]}

请返回完整、合法的单个 JSON 对象，不要使用 Markdown 代码块或附加文字。
""".strip()