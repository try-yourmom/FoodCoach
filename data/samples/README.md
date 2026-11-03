# 示例图片说明

## 学校餐盘照片

- `餐01.jpg` ～ `餐06.jpg`
- `餐11.jpg`

照片用于测试学校混合菜的识别困难，不包含需要公开的人脸信息。

## 用户提供的公开适配图

- `餐07.jpg` ～ `餐09.jpg`：白底四格餐盘测试图。
- `餐10.jpg`：其他网络测试图。

## 早期开发示例

- `healthy_bowl_unsplash.jpg`
  - CDN：https://images.unsplash.com/photo-1490645935967-10de6ba17061
- `meal_bowl_unsplash.jpg`
  - CDN：https://images.unsplash.com/photo-1546069901-ba9599a7e63c
- `meal_prep_unsplash.jpg`
  - CDN：https://images.unsplash.com/photo-1547592180-85f173990554

早期示例只用于开发与界面联调，不声称是训练数据。

## 评测分组

- `school_mixed`：`餐01`～`餐06`、`餐11`
- `yolo_friendly`：`餐07`～`餐09`
- `other`：`餐10`
- `餐盘.jpg` 不纳入正式评测