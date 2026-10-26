# 模型、数据与 Transformer 说明

## 1. token、embedding、attention 与位置编码

- **token**：模型处理文本时的基本单位。中文可能是一个字或词片段，图片则会被切成图像 patch。
- **embedding**：把 token 或图像 patch 映射成向量，使语义相近的内容在向量空间中更接近。
- **self-attention**：每个 token 根据其他 token 的信息调整自己的表示。例如判断“苹果”是水果还是手机品牌时，会关注上下文词。
- **位置编码**：Transformer 本身不知道顺序，位置编码把“第几个 token / 哪个图像区域”加入表示。

多模态模型会把图片 patch 和文字 token 放进同一套 Transformer 表征中，因此可以回答“图中有什么”“这份食物蛋白质够不够”等问题。

## 2. 传统检测与 VLM 的区别

YOLO 是判别式视觉模型：固定类别集合，直接回归边界框和类别概率。它不会自动生成自然语言，也不会理解“练后餐”这类情境。

Qwen-VL 是生成式多模态模型：视觉编码器把图片编码成 patch 表示，语言解码器根据图片表示和提示词逐步生成答案。它擅长开放语义和自然语言，但数值估算不一定可靠。

## 3. 为什么选择 YOLO-World

普通 YOLOv8 的 COCO 预训练权重食物类别很少。自行训练一个可靠的 20 类中餐检测器需要大量 bbox 标注，不适合本次切片的时间范围。

YOLO-World 支持文本提示类别，可直接检测：

```text
chicken breast, egg, cooked white rice, broccoli, beef, salmon,
oats, banana, milk, tofu, sweet potato, lettuce, tomato, shrimp,
whole wheat bread, potato, corn, plain yogurt, pork, green bell pepper
```

代价是对中餐混合菜、遮挡和非常规摆盘可能漏检。这是项目明确记录的局限，而不是隐藏误差。

## 4. 为什么选择 MobileSAM

SAM 是提示式分割模型，本身不识别食物。YOLO 给出 bbox 后，SAM 根据框提示输出像素掩膜。MobileSAM 比完整 SAM 轻，适合 8 GB 显存的笔记本 GPU，也足以生成餐盘区域轮廓。

## 5. 数据来源与责任边界

- 营养数据为常见食物每 100 克参考值，属于教学用近似表。
- 食材厚度、密度和餐盘覆盖比例是显式假设，用来生成可复现的克数区间。
- 示例图片来自 Unsplash CDN，仅用于开发测试；正式演示优先使用本人拍摄图片。
- 模型权重和 CLIP 文本编码器不提交 Git，运行脚本可重新下载。
- 项目不提供医疗、疾病饮食或专业营养处方。

## 6. 后续升级路线

1. 收集学校食堂固定菜品图片，人工标注 bbox
2. 在 YOLOv8/YOLO11 上微调固定菜单检测器
3. 对固定餐盘增加自动餐盘分割和尺寸标定
4. 用称重数据校准“掩膜面积→克数”回归模型
5. 保留 Qwen-VL 作为未知菜品兜底与自然语言反馈层