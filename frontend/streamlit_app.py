from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import requests
import streamlit as st

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
GOALS = {"减脂": "fat_loss", "增肌": "muscle_gain", "维持": "maintain"}
CONTEXTS = {
    "练前": "pre_workout",
    "练后": "post_workout",
    "非训练日": "rest_day",
    "加餐": "snack",
}

st.set_page_config(page_title="PlateLens · 餐盘透镜", page_icon="🍽️", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.3rem; padding-bottom: 2rem;}
    h1 {letter-spacing: -0.04em;}
    .subtitle {color: #667085; margin-top: -0.8rem; margin-bottom: 1.4rem;}
    .note-box {background: #F7F8FA; border: 1px solid #E4E7EC; border-radius: 12px; padding: 12px 14px;}
    .status-ok {color: #067647; font-weight: 700;}
    .status-warn {color: #B54708; font-weight: 700;}
    .status-error {color: #B42318; font-weight: 700;}
    [data-testid="stMetricValue"] {font-size: 1.55rem;}
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("PlateLens 餐盘透镜")
st.markdown(
    '<div class="subtitle">单餐视觉评估与诚实反馈 · 传统视觉模型 vs 多模态大模型</div>',
    unsafe_allow_html=True,
)


@st.cache_data(ttl=30)
def fetch_health() -> dict:
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/health", timeout=3)
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # noqa: BLE001
        return {"status": "offline", "error": str(exc)}


def image_from_base64(encoded: str):
    return base64.b64decode(encoded)


def render_food_table(result: dict):
    foods = result.get("foods", [])
    if not foods:
        st.info("没有可展示的食物条目。")
        return
    rows = []
    for food in foods:
        nutrition = food["nutrition"]
        grams = food.get("estimated_grams") or [None, None]
        rows.append(
            {
                "食物": food["name"],
                "置信度": f"{food['confidence']:.2f}",
                "估算分量/g": f"{grams[0]}–{grams[1]}" if grams[0] is not None else "—",
                "热量/kcal": nutrition["calories"],
                "蛋白质/g": nutrition["protein_g"],
                "碳水/g": nutrition["carbs_g"],
                "脂肪/g": nutrition["fat_g"],
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_method(result: dict, show_overlay: bool = False):
    status = result.get("status", "ok")
    css_class = {"ok": "status-ok", "degraded": "status-warn", "error": "status-error"}.get(status, "status-warn")
    st.markdown(f"运行状态：<span class='{css_class}'>{status.upper()}</span>", unsafe_allow_html=True)
    if result.get("overlay_image_base64") and show_overlay:
        st.image(image_from_base64(result["overlay_image_base64"]), caption="边界框 + 分割掩膜", use_container_width=True)
    totals = result["totals"]
    metric_cols = st.columns(4)
    metric_cols[0].metric("热量", f"{totals['calories']} kcal")
    metric_cols[1].metric("蛋白质", f"{totals['protein_g']} g")
    metric_cols[2].metric("碳水", f"{totals['carbs_g']} g")
    metric_cols[3].metric("脂肪", f"{totals['fat_g']} g")
    verdict = result["verdict"]
    st.markdown(f"**整餐结论**：热量{verdict['calorie_status']} · 蛋白质{verdict['protein_status']} · 碳水占比{verdict['carb_ratio']}")
    st.write(verdict["summary"])
    render_food_table(result)
    st.markdown("**下一餐可执行建议**")
    for item in result.get("advice", []):
        st.markdown(f"- {item}")
    st.caption(result.get("long_term_note", ""))
    for warning in result.get("warnings", []):
        st.warning(warning)
    with st.expander("技术元数据"):
        st.json(result.get("metadata", {}))
        st.caption(f"耗时：{result.get('duration_ms', 0) / 1000:.2f} 秒")


with st.sidebar:
    st.header("用户与本餐情境")
    health = fetch_health()
    if health.get("status") == "ok":
        api_state = "在线"
    else:
        api_state = "离线"
    st.caption(f"API：{api_state} · {API_BASE_URL}")
    if health.get("status") == "ok":
        if health.get("vlm_configured"):
            st.success(f"多模态模型已配置：{health.get('vlm_model')}")
        else:
            st.warning("尚未配置 DASHSCOPE_API_KEY，大模型方案会显示为不可用。")
        if not (health.get("yolo_model_present") and health.get("sam_model_present")):
            st.info("首次运行传统方案时会下载 YOLO/SAM 权重。")

    height_cm = st.number_input("身高 / cm", min_value=100.0, max_value=250.0, value=170.0, step=1.0)
    weight_kg = st.number_input("体重 / kg", min_value=30.0, max_value=300.0, value=65.0, step=0.5)
    has_body_fat = st.checkbox("填写体脂率", value=False)
    body_fat = st.number_input("体脂率 / %", 3.0, 60.0, 20.0, 0.5) if has_body_fat else None
    goal_label = st.radio("目标", list(GOALS), horizontal=True)
    context_label = st.selectbox("本餐情境", list(CONTEXTS))
    plate_diameter = st.number_input("餐盘直径 / cm", min_value=15.0, max_value=45.0, value=26.0, step=1.0)
    st.caption("餐盘直径只用于面积换算，不会让估算变成精确称重。")

source_mode = st.radio("图片来源", ["上传图片", "使用示例图"], horizontal=True, label_visibility="collapsed")
image_name = ""
image_bytes = b""
image_mime = "image/jpeg"
if source_mode == "上传图片":
    uploaded = st.file_uploader("上传一张餐盘图片", type=["jpg", "jpeg", "png", "webp"])
    if uploaded is not None:
        image_name = uploaded.name
        image_bytes = uploaded.getvalue()
        image_mime = uploaded.type or "image/jpeg"
else:
    sample_dir = Path(__file__).resolve().parent.parent / "data" / "samples"
    samples = sorted(sample_dir.glob("*.jpg")) + sorted(sample_dir.glob("*.png")) + sorted(sample_dir.glob("*.webp"))
    if samples:
        sample_path = st.selectbox("选择示例图片", samples, format_func=lambda path: path.name)
        image_name = sample_path.name
        image_bytes = sample_path.read_bytes()
        image_mime = "image/jpeg" if sample_path.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
    else:
        st.warning("没有找到示例图片，请改用上传模式。")

if not image_bytes:
    st.markdown(
        '<div class="note-box">建议使用俯拍、光线均匀且完整包含餐盘的图片。'
        "同一张图片会同时送给两种方案，确保比较公平。</div>",
        unsafe_allow_html=True,
    )
else:
    preview_col, action_col = st.columns([2, 1])
    with preview_col:
        st.image(image_bytes, caption="本次输入", use_container_width=True)
    with action_col:
        st.markdown("### 评估设置")
        st.write(f"目标：**{goal_label}**")
        st.write(f"情境：**{context_label}**")
        run = st.button("开始并排评估", type="primary", use_container_width=True)
        if run:
            files = {"image": (image_name, image_bytes, image_mime)}
            data = {
                "height_cm": str(height_cm),
                "weight_kg": str(weight_kg),
                "goal": GOALS[goal_label],
                "context": CONTEXTS[context_label],
                "plate_diameter_cm": str(plate_diameter),
            }
            if body_fat is not None:
                data["body_fat_pct"] = str(body_fat)
            try:
                with st.spinner("正在运行两条视觉管线……首次加载模型可能需要更久。"):
                    response = requests.post(
                        f"{API_BASE_URL}/api/v1/assess",
                        files=files,
                        data=data,
                        timeout=300,
                    )
                if response.status_code >= 400:
                    detail = response.json().get("detail", response.text) if "json" in response.headers.get("content-type", "") else response.text
                    st.error(f"评估失败：{detail}")
                else:
                    st.session_state["assessment"] = response.json()
            except requests.RequestException as exc:
                st.error(f"无法连接后端 API：{exc}")

result = st.session_state.get("assessment")
if result:
    st.divider()
    st.subheader("同一输入 · 两种方案")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("## 传统视觉方案")
        st.caption("YOLO-World → MobileSAM → 营养表 → 规则引擎")
        render_method(result["traditional"], show_overlay=True)
    with right:
        st.markdown("## 多模态大模型方案")
        st.caption("Qwen-VL → JSON 校验 → 营养估算 → 诚实反馈")
        render_method(result["vlm"])
    st.divider()
    st.subheader("方案对比")
    comparison = result["comparison"]
    st.dataframe(comparison["rows"], use_container_width=True, hide_index=True)
    st.info(comparison["summary"])
    st.markdown(f"**适用场景建议**：{comparison['recommended_use']}")
    st.caption(result["traditional"]["disclaimer"])
    st.download_button(
        "下载完整 JSON",
        data=json.dumps(result, ensure_ascii=False, indent=2),
        file_name=f"plate-lens-{result['request_id'][:8]}.json",
        mime="application/json",
    )