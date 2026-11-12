"""Водительское удостоверение: генератор, отрисовка, проверки, набор, база."""
import datetime as dt
import json
import re

from oko.dataset import fingerprint, generate, load
from oko.db import Store
from oko.engines.vlm import build_prompt, json_schema
from oko.fakedata import DriverFactory, add_years, license_truth, translit
from oko.normalize import canon, checks, detect_doc_type_by_fields, same
from oko.render import render
from oko.schema import DOC_FIELDS, DOC_TYPES, DRIVER_LICENSE, FIELD_BY_KEY


def _bad(fields):
    return [c.message for c in checks(DRIVER_LICENSE, fields) if c.level in ("warn", "error")]


def test_schema_knows_the_license():
    assert DRIVER_LICENSE in DOC_TYPES
    assert all(k in FIELD_BY_KEY for k in DOC_FIELDS[DRIVER_LICENSE])


def test_factory_is_deterministic_and_consistent():
    assert DriverFactory(5).make() == DriverFactory(5).make()
    f = DriverFactory(5)
    for _ in range(100):
        p = f.make()
        issue = dt.datetime.strptime(p.issue_date, "%d.%m.%Y").date()
        until = dt.datetime.strptime(p.valid_until, "%d.%m.%Y").date()
        birth = dt.datetime.strptime(p.birth_date, "%d.%m.%Y").date()
        assert until == add_years(issue, 10)
        assert add_years(birth, 18) <= issue
        assert re.fullmatch(r"\d{2} \d{2} \d{6}", p.doc_number)
        assert re.fullmatch(r"ГИБДД \d{4}", p.issued_by)
        assert p.doc_number[:2] == p.issued_by[6:8]          # регион в номере = регион подразделения


def test_clean_truth_passes_all_checks():
    f = DriverFactory(11)
    for _ in range(100):
        t = license_truth(f.make())
        assert list(t) == DOC_FIELDS[DRIVER_LICENSE]
        assert not _bad(t), (t, _bad(t))


def test_checks_catch_errors():
    t = license_truth(DriverFactory(1).make())
    assert any("10 годам" in m for m in _bad({**t, "valid_until": "01.01.2000"}))
    assert any("категорий не бывает" in m for m in _bad({**t, "dl_categories": "B, Z"}))
    assert any("ГИБДД и 4 цифры" in m for m in _bad({**t, "issued_by": "МРЭО"}))
    assert any("10 цифр" in m for m in _bad({**t, "doc_number": "64 12 34"}))
    # 17-летний с категорией D (нужно 21)
    young = {**t, "birth_date": "01.01.2003", "issue_date": "02.01.2020", "valid_until": "02.01.2030",
             "dl_categories": "B, D"}
    assert any("нужно 21" in m for m in _bad(young))


def test_cyrillic_categories_are_fine():
    t = license_truth(DriverFactory(2).make())
    assert not _bad({**t, "dl_categories": "В, В1, М"})       # русские буквы вместо латинских
    assert same("dl_categories", "В, В1, М", "B, B1, M")


def test_detect_and_canon():
    t = license_truth(DriverFactory(3).make())
    assert detect_doc_type_by_fields(t) == DRIVER_LICENSE
    assert canon("valid_until", "1.2.2030") == "01.02.2030"
    assert translit("ЩУКИН ЮРИЙ") == "SHCHUKIN IURII"


def test_render_boxes_inside_image():
    for seed in range(3):
        img, truth, boxes = render(DriverFactory(seed).make(), DRIVER_LICENSE, seed=seed)
        assert set(boxes) == set(truth)
        for x0, y0, x1, y1 in boxes.values():
            assert 0 <= x0 < x1 <= img.width and 0 <= y0 < y1 <= img.height


def test_dataset_with_licenses(tmp_path):
    items = generate(tmp_path, n_vehicles=2, seed=7, n_licenses=3)
    lic = [it for it in items if it.doc_type == DRIVER_LICENSE]
    assert len(lic) == 3 and all((tmp_path / it.image).exists() and (tmp_path / it.photo).exists() for it in lic)
    assert len(load(tmp_path, "all")) == len(items)
    coco = json.loads((tmp_path / "coco.json").read_text(encoding="utf-8"))
    assert "dl_categories" in {c["name"] for c in coco["categories"]}
    # набор машин тот же, что и без ВУ
    cars = [it for it in items if it.doc_type != DRIVER_LICENSE]
    assert fingerprint(cars) == fingerprint(generate(tmp_path / "no_dl", n_vehicles=2, seed=7))


def test_store_keeps_license_without_vehicle_card(tmp_path):
    s = Store(tmp_path / "t.db")
    vid = s.add_document(DRIVER_LICENSE, license_truth(DriverFactory(4).make()), "d0000")
    assert vid == 0
    assert s.stats() == {"vehicles": 0, "documents": 1}


def test_vlm_prompt_mentions_license():
    assert "Водительское удостоверение" in build_prompt()
    assert DRIVER_LICENSE in json_schema()["schema"]["properties"]["doc_type"]["enum"]
