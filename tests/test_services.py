
import numpy as np
from helpers import build_food

from app.catalog import load_catalog
from app.schemas import MethodResult, UserProfile
from app.services.comparison import build_comparison
from app.services.portion import estimate_portion
from app.services.traditional import Detection, TraditionalVisionService
from app.services.vlm import VLMService


def test_larger_mask_estimates_more_food():
    rice = next(item for item in load_catalog() if item.food_id == "rice")
    small, _ = estimate_portion(rice, 0.03, 26)
    large, _ = estimate_portion(rice, 0.12, 26)
    assert large[0] > small[0]


def test_vlm_parser_accepts_fenced_json():
    raw = """```json
    {"foods": [], "advice": [], "long_term_note": "", "warnings": []}
    ```"""
    payload = VLMService._parse_payload(raw)
    assert payload.foods == []
    assert payload.advice


def test_comparison_reports_missing_vlm():
    rice = next(item for item in load_catalog() if item.food_id == "rice")
    traditional = MethodResult(
        method="traditional",
        foods=[build_food(rice, 150, "米饭")],
        totals={"calories": 195, "protein_g": 4, "carbs_g": 42, "fat_g": 0.5},
        verdict={"calorie_status": "适中", "protein_status": "不足", "carb_ratio": "适中", "summary": "ok"},
        advice=["下一顿补充蛋白质。"],
        long_term_note="长期观察。",
        duration_ms=100,
    )
    vlm = MethodResult(
        method="vlm",
        status="error",
        foods=[],
        totals={"calories": 0, "protein_g": 0, "carbs_g": 0, "fat_g": 0},
        verdict={"calorie_status": "无法判断", "protein_status": "无法判断", "carb_ratio": "无法判断", "summary": "无 Key"},
        advice=["配置 Key。"],
        long_term_note="不编造。",
        duration_ms=0,
    )
    report = build_comparison(traditional, vlm)
    assert "不可用" in report.rows[0].vlm
    assert "仅完成" in report.summary

def test_traditional_pipeline_converts_rgb_to_bgr_once():
    rice = next(item for item in load_catalog() if item.food_id == "rice")
    received = {}

    class FakeDetector:
        def detect(self, image_bgr, confidence):
            received["detector"] = image_bgr
            return [
                Detection(
                    record=rice,
                    confidence=0.9,
                    bbox_xyxy=(0.0, 0.0, 4.0, 4.0),
                )
            ]

    class FakeSegmenter:
        def segment(self, image_bgr, detections):
            received["segmenter"] = image_bgr
            return True

    service = TraditionalVisionService()
    service.detector = FakeDetector()
    service.segmenter = FakeSegmenter()
    image_rgb = np.zeros((8, 8, 3), dtype=np.uint8)
    image_rgb[0, 0] = (255, 0, 0)

    service.assess(image_rgb, UserProfile())

    np.testing.assert_array_equal(received["detector"][0, 0], [0, 0, 255])
    assert received["detector"] is received["segmenter"]
    np.testing.assert_array_equal(image_rgb[0, 0], [255, 0, 0])
