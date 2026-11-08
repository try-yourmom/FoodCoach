# 考核要求逐条映射

| 考核点 | 本项目落实 |
|---|---|
| Transformer 基本概念 | [model_and_data_notes.md](model_and_data_notes.md) 解释 token、embedding、self-attention、位置编码，以及 VLM 中图文 token 的关系 |
| 编码器 / 解码器与多模态输入 | 文档对比传统视觉模型的检测头与 Qwen3.8-Omni-Flash 的图文编码、生成解码流程 |
| OpenCV 图像处理 | 读取、EXIF 方向修正、缩放、裁剪数据、绘制 bbox 与透明掩膜 |
| YOLO 目标检测 | YOLO-World 输出类别、置信度、边界框，并设置置信度过滤和同类去重 |
| 提示式图像分割 | 把 YOLO bbox 作为 MobileSAM 的框提示，生成每个食物的二值掩膜 |
| 开源模型使用流程 | 文档和 `scripts/download_models.py` 说明输入、输出、权重下载与降级行为 |
| 大模型 API / SDK | `VLMService` 使用 OpenAI 兼容 SDK 调用 Qwen3.8-Omni-Flash |
| 提示词与结构化输出 | 固定 JSON Schema、Pydantic 校验、修复重试和错误降级 |
| 两种方案、同一组输入 | `/api/v1/assess` 接收一次上传，并发调用两条管线 |
| 并排展示 | Streamlit 左右两列展示传统与大模型结果 |
| 方案对比 | 对比食物集合、热量差异、定位、速度、成本和可解释性 |
| 仓库与真实历史 | 独立 Git 仓库，按数据契约、服务、前端、文档等阶段提交 |
| 项目说明文档 | README、架构、比较、模型说明、个人说明与视频脚本 |
| 运行视频 | 单独录制并提交，展示上传、双方案结果和对比结论 |
| 参考与创新 | 统一双方案契约、透明分量公式、安全反馈规则和对比页面为自主实现 |
| AI 辅助开发 | `docs/personal_reflection.md` 记录 AI 使用方式、理解和需要人工修改的部分 |

## 验收时可现场演示的链路

1. 打开 Streamlit 页面
2. 上传一张固定餐盘图片
3. 选择减脂、练后、26 cm 餐盘
4. 点击“开始并排评估”
5. 左侧展示 bbox、掩膜、食物表和规则反馈
6. 右侧展示 Qwen3.8-Omni-Flash 识别、营养估算和自然语言反馈
7. 下方展示两方案对比
8. 下载完整 JSON