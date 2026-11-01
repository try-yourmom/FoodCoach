from __future__ import annotations

from app.schemas import ComparisonReport, ComparisonRow, MethodResult


def _names(result: MethodResult) -> set[str]:
    return {food.name for food in result.foods}


def build_comparison(traditional: MethodResult, vlm: MethodResult) -> ComparisonReport:
    trad_names, vlm_names = _names(traditional), _names(vlm)
    common = trad_names & vlm_names
    union = trad_names | vlm_names
    jaccard = len(common) / len(union) if union else 1.0
    calorie_delta = vlm.totals.calories - traditional.totals.calories
    calorie_delta_pct = abs(calorie_delta) / max(1, traditional.totals.calories) * 100
    trad_conf = sum(food.confidence for food in traditional.foods) / max(1, len(traditional.foods))
    vlm_conf = sum(food.confidence for food in vlm.foods) / max(1, len(vlm.foods))

    rows = [
        ComparisonRow(
            dimension="识别食物",
            traditional="、".join(sorted(trad_names)) or "未识别",
            vlm="、".join(sorted(vlm_names)) or "不可用",
            conclusion=f"名称重合 {len(common)} 项，集合重合度约 {jaccard:.0%}。",
        ),
        ComparisonRow(
            dimension="定位与分割",
            traditional="提供边界框与 SAM 掩膜面积。",
            vlm="可能提供粗略归一化边界框，无像素级掩膜。",
            conclusion="传统方案的视觉证据更可复核。",
        ),
        ComparisonRow(
            dimension="营养估算",
            traditional=f"约 {traditional.totals.calories} kcal。",
            vlm=f"约 {vlm.totals.calories} kcal。",
            conclusion=f"热量差约 {abs(calorie_delta)} kcal（{calorie_delta_pct:.0f}%），两者都只是估算。",
        ),
        ComparisonRow(
            dimension="情境反馈",
            traditional="规则覆盖固定，结论稳定。",
            vlm="自然语言更灵活，可理解混合菜名与上下文。",
            conclusion="传统方案可复现，大模型方案表达更自然。",
        ),
        ComparisonRow(
            dimension="速度",
            traditional=f"{traditional.duration_ms / 1000:.2f} 秒。",
            vlm=f"{vlm.duration_ms / 1000:.2f} 秒。",
            conclusion="传统模型通常本地推理更快，首次加载除外。",
        ),
        ComparisonRow(
            dimension="成本",
            traditional="本地推理，无单次 API 费用。",
            vlm="按图片与模型计费，受免费额度和供应商价格影响。",
            conclusion="固定高频场景更适合传统方案。",
        ),
        ComparisonRow(
            dimension="可解释性",
            traditional=f"平均检测置信度 {trad_conf:.2f}；每个数值可追溯到食物表和公式。",
            vlm=f"模型自报平均置信度 {vlm_conf:.2f}；置信度不能等同于事实校准。",
            conclusion="传统管线更容易定位错误来源。",
        ),
    ]
    if vlm.status == "error":
        summary = "多模态模型当前不可用，本次对比仅完成了传统方案。配置 API Key 后应重新执行同一张图片的对照。"
    elif not trad_names and not vlm_names:
        summary = "两种方案都没有识别出明确食物，应先检查图片质量和支持范围，而不是直接比较营养数值。"
    elif not common:
        summary = (
            "两种方案在这张图片上的识别结果没有重合，说明至少一条管线存在明显偏差。"
            "此时不应直接采用任一营养数值，应回看边界框、掩膜和模型警告定位原因。"
        )
    elif jaccard < 0.5:
        summary = (
            "两种方案只识别出少量共同食物，结果差异较大。传统方案更便于复核定位，"
            "大模型可能补充了未知菜品，但其新增营养数值仍需人工确认。"
        )
    else:
        summary = (
            "两种方案的主要识别结果较为一致，可以优先参考传统方案的可追溯定位与计算，"
            "并利用大模型补充自然语言解释；营养数值仍应视为估算。"
        )
    return ComparisonReport(
        rows=rows,
        summary=summary,
        recommended_use=(
            "稳定菜单、需要可解释定位和批量处理时用传统方案；"
            "开放菜品、需要自然语言解释时用多模态大模型；最终产品可让传统模型负责数值、大模型负责情境反馈。"
        ),
    )