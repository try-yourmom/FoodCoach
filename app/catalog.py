from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.config import settings


@dataclass(frozen=True)
class FoodRecord:
    food_id: str
    name: str
    prompt_en: str
    prompt_variants: tuple[str, ...]
    aliases: tuple[str, ...]
    calories_per_100g: float
    protein_g_per_100g: float
    carbs_g_per_100g: float
    fat_g_per_100g: float
    default_grams: float
    min_grams: float
    max_grams: float
    density_g_per_cm3: float
    thickness_cm: float


def _split_aliases(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split("|") if item.strip())


@lru_cache(maxsize=1)
def load_catalog(path: Path | None = None) -> tuple[FoodRecord, ...]:
    catalog_path = path or settings.nutrition_path
    with catalog_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise RuntimeError(f"Nutrition catalog is empty: {catalog_path}")
    records: list[FoodRecord] = []
    for row in rows:
        records.append(
            FoodRecord(
                food_id=row["food_id"].strip(),
                name=row["name"].strip(),
                prompt_en=row["prompt_en"].strip(),
                prompt_variants=_split_aliases(row["prompt_variants"]),
                aliases=_split_aliases(row["aliases"]),
                calories_per_100g=float(row["calories_per_100g"]),
                protein_g_per_100g=float(row["protein_g_per_100g"]),
                carbs_g_per_100g=float(row["carbs_g_per_100g"]),
                fat_g_per_100g=float(row["fat_g_per_100g"]),
                default_grams=float(row["default_grams"]),
                min_grams=float(row["min_grams"]),
                max_grams=float(row["max_grams"]),
                density_g_per_cm3=float(row["density_g_per_cm3"]),
                thickness_cm=float(row["thickness_cm"]),
            )
        )
    return tuple(records)


@lru_cache(maxsize=1)
def catalog_by_id() -> dict[str, FoodRecord]:
    return {record.food_id: record for record in load_catalog()}


@lru_cache(maxsize=1)
def catalog_by_prompt() -> dict[str, FoodRecord]:
    mapping: dict[str, FoodRecord] = {}
    for record in load_catalog():
        for prompt in (record.prompt_en, *record.prompt_variants):
            mapping[prompt.lower()] = record
    return mapping


def find_food(name: str) -> FoodRecord | None:
    needle = name.strip().lower()
    for record in load_catalog():
        candidates = (
            record.name,
            record.prompt_en,
            record.food_id,
            *record.prompt_variants,
            *record.aliases,
        )
        if any(needle == candidate.strip().lower() for candidate in candidates):
            return record
    return None


def supported_prompts() -> list[str]:
    prompts: list[str] = []
    seen: set[str] = set()
    for record in load_catalog():
        for prompt in (record.prompt_en, *record.prompt_variants):
            normalized = prompt.strip().lower()
            if normalized and normalized not in seen:
                prompts.append(prompt.strip())
                seen.add(normalized)
    return prompts


def catalog_payload() -> list[dict]:
    return [
        {
            "id": record.food_id,
            "name": record.name,
            "prompt": record.prompt_en,
            "prompt_variants": list(record.prompt_variants),
            "aliases": list(record.aliases),
            "nutrition_per_100g": {
                "calories": record.calories_per_100g,
                "protein_g": record.protein_g_per_100g,
                "carbs_g": record.carbs_g_per_100g,
                "fat_g": record.fat_g_per_100g,
            },
            "default_portion_g": record.default_grams,
        }
        for record in load_catalog()
    ]