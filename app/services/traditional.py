from __future__ import annotations

import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from app.catalog import FoodRecord, catalog_by_prompt, supported_prompts
from app.config import settings
from app.nutrition import calculate_nutrition, provisional_verdict, total_nutrition
from app.rule_engine import DISCLAIMER, enrich_food_verdicts, evaluate_meal
from app.schemas import FoodItem, MethodResult, UserProfile
from app.services.image_utils import image_to_base64_png
from app.services.portion import estimate_portion

_MODEL_LOCK = threading.Lock()


@dataclass
class Detection:
    record: FoodRecord
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    mask: np.ndarray | None = None
    mask_area_ratio: float | None = None


class YoloWorldDetector:
    def __init__(self) -> None:
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        from ultralytics import YOLO

        settings.yolo_model_path.parent.mkdir(parents=True, exist_ok=True)
        model = YOLO(str(settings.yolo_model_path))
        model.set_classes(supported_prompts())
        self._model = model
        return model

    def detect(self, image_rgb: np.ndarray, confidence: float) -> list[Detection]:
        prompts = supported_prompts()
        records = catalog_by_prompt()
        with _MODEL_LOCK:
            model = self._load()
            results = model.predict(
                source=image_rgb,
                conf=confidence,
                imgsz=settings.detection_image_size,
                device=settings.resolved_device(),
                verbose=False,
            )
        if not results or results[0].boxes is None:
            return []
        boxes = results[0].boxes
        detections: list[Detection] = []
        for row in boxes:
            cls_id = int(row.cls.item())
            prompt = prompts[cls_id] if 0 <= cls_id < len(prompts) else str(model.names.get(cls_id, ""))
            record = records.get(prompt.lower())
            if record is None:
                continue
            coords = row.xyxy[0].detach().cpu().numpy().tolist()
            detections.append(
                Detection(
                    record=record,
                    confidence=float(row.conf.item()),
                    bbox_xyxy=tuple(float(value) for value in coords),
                )
            )
        # A single ingredient pile should not appear many times just because
        # open-vocabulary detection fires on several texture patches.
        per_food: dict[str, int] = {}
        limited: list[Detection] = []
        for detection in sorted(detections, key=lambda item: item.confidence, reverse=True):
            count = per_food.get(detection.record.food_id, 0)
            if count >= 2:
                continue
            per_food[detection.record.food_id] = count + 1
            limited.append(detection)
        return limited


class MobileSamSegmenter:
    def __init__(self) -> None:
        self._model = None

    def _load(self):
        if self._model is not None:
            return self._model
        from ultralytics import SAM

        settings.sam_model_path.parent.mkdir(parents=True, exist_ok=True)
        self._model = SAM(str(settings.sam_model_path))
        return self._model

    def segment(self, image_rgb: np.ndarray, detections: Sequence[Detection]) -> bool:
        if not detections:
            return True
        boxes = [list(detection.bbox_xyxy) for detection in detections]
        with _MODEL_LOCK:
            model = self._load()
            results = model.predict(source=image_rgb, bboxes=boxes, verbose=False, device=settings.resolved_device())
        if not results or results[0].masks is None:
            return False
        masks = results[0].masks.data.detach().cpu().numpy()
        if len(masks) != len(detections):
            return False
        for detection, mask in zip(detections, masks):
            binary = mask.astype(bool)
            detection.mask = binary
            detection.mask_area_ratio = float(binary.sum() / max(1, binary.size))
        return True


class TraditionalVisionService:
    def __init__(self) -> None:
        self.detector = YoloWorldDetector()
        self.segmenter = MobileSamSegmenter()

    @property
    def models_available(self) -> bool:
        return settings.yolo_model_path.exists() and settings.sam_model_path.exists()

    def assess(self, image_rgb: np.ndarray, profile: UserProfile) -> MethodResult:
        started = time.perf_counter()
        warnings: list[str] = []
        detections = self.detector.detect(image_rgb, settings.detection_confidence)
        segmented = self.segmenter.segment(image_rgb, detections) if detections else True
        if detections and not segmented:
            warnings.append("SAM 未返回可对齐的掩膜，已降级为边界框面积估算。")

        image_height, image_width = image_rgb.shape[:2]
        foods: list[FoodItem] = []
        for detection in detections:
            x1, y1, x2, y2 = detection.bbox_xyxy
            bbox_area_ratio = max(0.0, (x2 - x1) * (y2 - y1)) / max(1, image_width * image_height)
            mask_ratio = detection.mask_area_ratio
            if mask_ratio is None:
                mask_ratio = bbox_area_ratio * 0.68
            grams_range, grams_mid = estimate_portion(
                detection.record,
                mask_ratio,
                profile.plate_diameter_cm,
            )
            nutrition = calculate_nutrition(detection.record, grams_mid)
            foods.append(
                FoodItem(
                    name=detection.record.name,
                    confidence=round(detection.confidence, 3),
                    bbox=[
                        round(x1, 1),
                        round(y1, 1),
                        round(max(0.0, x2 - x1), 1),
                        round(max(0.0, y2 - y1), 1),
                    ],
                    mask_area_ratio=round(float(mask_ratio), 4),
                    estimated_grams=grams_range,
                    nutrition=nutrition,
                    verdict=provisional_verdict(detection.record.name, nutrition),
                    source_id=detection.record.food_id,
                )
            )

        totals = total_nutrition(foods)
        verdict, advice, long_term_note, target_metadata = evaluate_meal(totals, profile, foods)
        enrich_food_verdicts(foods, verdict, profile)
        if not detections:
            warnings.append("未检测到支持范围内的食物；可换用俯拍、光线更好的图片。")

        overlay = render_overlay(image_rgb, detections)
        metadata = {
            **target_metadata,
            "pipeline": "YOLO-World -> MobileSAM -> nutrition CSV -> rules",
            "detection_count": len(detections),
            "segmentation_used": segmented and bool(detections),
            "models_available": self.models_available,
            "device": str(settings.resolved_device()),
        }
        return MethodResult(
            method="traditional",
            status="degraded" if warnings else "ok",
            foods=foods,
            totals=totals,
            verdict=verdict,
            advice=advice,
            long_term_note=long_term_note,
            disclaimer=DISCLAIMER,
            warnings=warnings,
            duration_ms=round((time.perf_counter() - started) * 1000),
            overlay_image_base64=image_to_base64_png(overlay),
            metadata=metadata,
        )


def render_overlay(image_rgb: np.ndarray, detections: Sequence[Detection]) -> np.ndarray:
    canvas = image_rgb.copy()
    colors = [(43, 172, 95), (30, 111, 200), (205, 135, 30), (164, 70, 170), (200, 80, 80)]
    for index, detection in enumerate(detections):
        color = colors[index % len(colors)]
        if detection.mask is not None:
            mask = detection.mask.astype(bool)
            overlay = np.zeros_like(canvas)
            overlay[mask] = color
            canvas[mask] = cv2.addWeighted(canvas[mask], 0.55, overlay[mask], 0.45, 0)
        x1, y1, x2, y2 = (round(value) for value in detection.bbox_xyxy)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)
        label = f"{detection.record.prompt_en} {detection.confidence:.2f}"
        cv2.putText(canvas, label, (x1, max(18, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(canvas, label, (x1, max(18, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    return canvas