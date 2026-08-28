import csv
from pathlib import Path

import pytest

from scripts.import_law_documents import (
    CorpusValidationError,
    build_manifest,
    normalize_date,
    parse_args,
)


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["title", "office", "publish", "stage"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_build_manifest_matches_title_and_normalizes_metadata(tmp_path: Path):
    documents_dir = tmp_path / "txt_utf8"
    documents_dir.mkdir()
    (documents_dir / "中华人民共和国著作权法.txt").write_text(
        "第一条 测试内容。", encoding="utf-8"
    )
    metadata_csv = tmp_path / "meta_data.csv"
    _write_csv(
        metadata_csv,
        [
            {
                "title": "中华人民共和国著作权法",
                "office": "全国人民代表大会常务委员会",
                "publish": "2020/11/11",
                "stage": "法律",
            }
        ],
    )

    records = build_manifest(metadata_csv, documents_dir)

    assert len(records) == 1
    assert records[0].filename == "中华人民共和国著作权法.txt"
    assert records[0].metadata == {
        "title": "中华人民共和国著作权法",
        "office": "全国人民代表大会常务委员会",
        "publish_date": "2020-11-11",
        "type": "法律",
    }


def test_build_manifest_keeps_missing_publish_date_as_none(tmp_path: Path):
    documents_dir = tmp_path / "txt_utf8"
    documents_dir.mkdir()
    (documents_dir / "地方条例.txt").write_text("第一条 测试。", encoding="utf-8")
    metadata_csv = tmp_path / "meta_data.csv"
    _write_csv(
        metadata_csv,
        [{"title": "地方条例", "office": "人大常委会", "publish": "", "stage": "地方性法规"}],
    )

    records = build_manifest(metadata_csv, documents_dir)

    assert records[0].metadata["publish_date"] is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2026/8/28", "2026-08-28"), ("2026-08-28", "2026-08-28"), ("", None)],
)
def test_normalize_date(raw: str, expected: str | None):
    assert normalize_date(raw) == expected


def test_build_manifest_rejects_unmatched_files(tmp_path: Path):
    documents_dir = tmp_path / "txt_utf8"
    documents_dir.mkdir()
    (documents_dir / "甲法.txt").write_text("第一条 测试。", encoding="utf-8")
    (documents_dir / "孤立文件.txt").write_text("第一条 测试。", encoding="utf-8")
    metadata_csv = tmp_path / "meta_data.csv"
    _write_csv(
        metadata_csv,
        [{"title": "乙法", "office": "国务院", "publish": "2026/1/1", "stage": "行政法规"}],
    )

    with pytest.raises(CorpusValidationError) as exc_info:
        build_manifest(metadata_csv, documents_dir)

    message = str(exc_info.value)
    assert "乙法" in message
    assert "甲法" in message
    assert "孤立文件" in message


def test_parse_args_uses_safe_existing_document_default():
    args = parse_args([])

    assert args.on_existing == "skip"
    assert args.dry_run is False
