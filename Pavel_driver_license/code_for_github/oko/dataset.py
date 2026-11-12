"""Сборка набора данных: картинки документов + разметка.

Структура папки набора:
    images/<id>.jpg   — чистый скан
    photos/<id>.jpg   — тот же документ «сфотографированный телефоном»
    labels.jsonl      — по строке на документ: вид, правильные значения, рамки полей
    coco.json         — та же разметка в формате COCO (открывается в CVAT)

Один автомобиль даёт три документа: две стороны СТС и ПТС (бумажный или ЭПТС).
Разделение на dev/test идёт по автомобилям, чтобы одна машина не попала в обе части.

По желанию (--licenses N) в набор добавляются водительские удостоверения: у каждого
своя «папка» d0000, d0001… По умолчанию их нет, и набор машин не меняется.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .distort import phone_photo
from .fakedata import DriverFactory, VehicleFactory
from .render import render
from .schema import DOC_FIELDS, DRIVER_LICENSE, EPTS, PTS, STS_BACK, STS_FRONT, VEHICLE_DOC_TYPES


@dataclass
class Item:
    id: str
    vehicle_id: str
    doc_type: str
    split: str
    image: str
    photo: str
    width: int
    height: int
    fields: dict
    boxes: dict

    @staticmethod
    def from_json(d: dict) -> "Item":
        return Item(**d)


def generate(out_dir: str | Path, n_vehicles: int = 300, seed: int = 42, test_share: float = 0.3,
             quality: int = 90, progress=None, n_licenses: int = 0) -> list[Item]:
    out = Path(out_dir)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "photos").mkdir(parents=True, exist_ok=True)
    factory = VehicleFactory(seed)
    rng = random.Random(seed + 1)
    items: list[Item] = []
    for vi in range(n_vehicles):
        v = factory.make()
        vid = f"v{vi:04d}"
        split = "test" if rng.random() < test_share else "dev"
        docs = [STS_FRONT, STS_BACK, EPTS if v.pts_kind == "epts" else PTS]
        for dtype in docs:
            doc_id = f"{vid}_{dtype}"
            doc_seed = seed * 100_000 + vi * 10 + docs.index(dtype)
            img, truth, boxes = render(v, dtype, doc_seed)
            img_path = out / "images" / f"{doc_id}.jpg"
            photo_path = out / "photos" / f"{doc_id}.jpg"
            img.save(img_path, quality=quality)
            phone_photo(img, seed=doc_seed).save(photo_path, quality=quality - 6)
            items.append(Item(doc_id, vid, dtype, split, f"images/{doc_id}.jpg", f"photos/{doc_id}.jpg",
                              img.width, img.height, truth, {k: list(b) for k, b in boxes.items()}))
        if progress:
            progress(vi + 1, n_vehicles)
    # Водительские удостоверения — отдельным генератором, чтобы не сдвинуть набор машин
    drivers = DriverFactory(seed + 7)
    drng = random.Random(seed + 8)
    for di in range(n_licenses):
        p = drivers.make()
        pid = f"d{di:04d}"
        split = "test" if drng.random() < test_share else "dev"
        doc_id = f"{pid}_{DRIVER_LICENSE}"
        doc_seed = seed * 100_000 + 50_000_000 + di
        img, truth, boxes = render(p, DRIVER_LICENSE, doc_seed)
        img.save(out / "images" / f"{doc_id}.jpg", quality=quality)
        phone_photo(img, seed=doc_seed).save(out / "photos" / f"{doc_id}.jpg", quality=quality - 6)
        items.append(Item(doc_id, pid, DRIVER_LICENSE, split, f"images/{doc_id}.jpg", f"photos/{doc_id}.jpg",
                          img.width, img.height, truth, {k: list(b) for k, b in boxes.items()}))
    with open(out / "labels.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it.__dict__, ensure_ascii=False) + "\n")
    export_coco(items, out / "coco.json")
    (out / "README.txt").write_text(
        "Синтетический набор OKO. Все данные выдуманы, все документы помечены «ОБРАЗЕЦ».\n"
        f"Автомобилей: {n_vehicles}, водительских удостоверений: {n_licenses}, документов: {len(items)}, "
        f"seed: {seed}, отпечаток: {fingerprint(items)}.\n"
        "Пересоздать точно такой же набор: python -m oko generate "
        f"--vehicles {n_vehicles} --licenses {n_licenses} --seed {seed} --out <папка>\n", encoding="utf-8")
    return items


def fingerprint(items: list[Item]) -> str:
    """Отпечаток разметки: одинаковый у одинаковых наборов на любом компьютере.
    Нужен, чтобы не сравнить результаты, посчитанные на разных наборах."""
    h = hashlib.sha256()
    for it in sorted(items, key=lambda i: i.id):
        h.update(json.dumps([it.id, it.doc_type, it.split, it.fields], ensure_ascii=False, sort_keys=True).encode())
    return h.hexdigest()[:12]


def load(data_dir: str | Path, split: str | None = None) -> list[Item]:
    items = []
    with open(Path(data_dir) / "labels.jsonl", encoding="utf-8") as f:
        for line in f:
            it = Item.from_json(json.loads(line))
            if split in (None, "all") or it.split == split:
                items.append(it)
    return items


def export_coco(items: list[Item], path: Path) -> None:
    """Разметка в формате COCO: каждая рамка — объект с категорией-полем.
    Значение поля лежит в attributes.value — так его покажет CVAT."""
    # категории ВУ добавляются, только если в наборе есть ВУ: так номера категорий у набора машин не меняются
    types = VEHICLE_DOC_TYPES + ([DRIVER_LICENSE] if any(it.doc_type == DRIVER_LICENSE for it in items) else [])
    keys = sorted({k for dt in types for k in DOC_FIELDS[dt]})
    cat_id = {k: i + 1 for i, k in enumerate(keys)}
    images, anns = [], []
    ann_id = 1
    for img_id, it in enumerate(items, 1):
        images.append({"id": img_id, "file_name": it.image, "width": it.width, "height": it.height,
                       "doc_type": it.doc_type, "split": it.split})
        for key, (x0, y0, x1, y1) in it.boxes.items():
            anns.append({"id": ann_id, "image_id": img_id, "category_id": cat_id[key],
                         "bbox": [x0, y0, x1 - x0, y1 - y0], "area": (x1 - x0) * (y1 - y0), "iscrowd": 0,
                         "attributes": {"value": it.fields.get(key, "")}})
            ann_id += 1
    coco = {"info": {"description": "OKO synthetic vehicle documents", "version": "1.0"},
            "images": images, "annotations": anns,
            "categories": [{"id": i, "name": k, "supercategory": "field"} for k, i in cat_id.items()]}
    path.write_text(json.dumps(coco, ensure_ascii=False), encoding="utf-8")


def open_image(data_dir: str | Path, rel: str) -> Image.Image:
    return Image.open(Path(data_dir) / rel).convert("RGB")
