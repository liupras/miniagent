#!/usr/bin/python
# -*- coding:utf-8 -*-
# @author  : Liu Lijun
# @date    : 2026-05-29
# @description: Batch-import a directory of Chinese legal documents into a law_cn KB.

"""
运行方式：

python scripts/import_law_documents.py `
  --kb-name kb_intellectual_property_cn `
  --metadata-csv "D:\backup\知识产权法律法规\meta_data.csv" `
  --documents-dir "D:\backup\知识产权法律法规\txt_utf8"

--dry-run            只检查，不入库
--on-existing skip   已有同名文档则跳过，默认
--on-existing fail   遇到已有文档立即失败
--on-existing update 更新文件和元数据
--continue-on-error  单个文档失败后继续
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from tqdm import tqdm


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# ServiceContainer currently imports SQL Agent eagerly.  The law importer does
# not use DuckDB, so give that unrelated subsystem a dedicated path instead of
# contending with a running MiniAgent server's DuckDB connection.
os.environ.setdefault("DUCK_DB_PATH", "db/importer_duckdb")

from app.core.service_container import ServiceContainer
from app.infra.db.database import Domain, KnowledgeBase
from app.runtime.task.progress_tracker import ProgressTracker
from app.utils.hash import calculate_file_sha256
from sqlalchemy import select


DEFAULT_KB_NAME = "kb_intellectual_property_cn"
DEFAULT_CORPUS_ROOT = Path(r"D:\backup\知识产权法律法规")
REQUIRED_COLUMNS = frozenset({"title", "office", "publish", "stage"})


class CorpusValidationError(ValueError):
    """Raised when the CSV and document directory do not form a safe manifest."""


@dataclass(frozen=True)
class ImportRecord:
    title: str
    file_path: Path
    metadata: dict[str, Any]

    @property
    def filename(self) -> str:
        return self.file_path.name


@dataclass
class ImportSummary:
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0


def normalize_date(value: str) -> str | None:
    """Normalize supported CSV dates to ISO-8601 without inventing missing dates."""
    value = value.strip()
    if not value:
        return None

    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise CorpusValidationError(f"Unsupported publish date: {value!r}")


def _duplicates(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def build_manifest(metadata_csv: Path, documents_dir: Path) -> list[ImportRecord]:
    """Validate the corpus and match each CSV title to exactly one TXT file."""
    if not metadata_csv.is_file():
        raise CorpusValidationError(f"Metadata CSV does not exist: {metadata_csv}")
    if not documents_dir.is_dir():
        raise CorpusValidationError(f"Document directory does not exist: {documents_dir}")

    with metadata_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - columns)
        if missing_columns:
            raise CorpusValidationError(
                f"Metadata CSV is missing columns: {', '.join(missing_columns)}"
            )
        rows = list(reader)

    titles = [(row.get("title") or "").strip() for row in rows]
    empty_title_rows = [str(index) for index, title in enumerate(titles, start=2) if not title]
    duplicate_titles = _duplicates(title for title in titles if title)
    errors: list[str] = []
    if empty_title_rows:
        errors.append(f"Empty title at CSV row(s): {', '.join(empty_title_rows)}")
    if duplicate_titles:
        errors.append(f"Duplicate CSV title(s): {', '.join(duplicate_titles)}")

    txt_files = sorted(documents_dir.glob("*.txt"), key=lambda item: item.name)
    files_by_title = {item.stem: item for item in txt_files}
    duplicate_file_titles = _duplicates(item.stem for item in txt_files)
    if duplicate_file_titles:
        errors.append(f"Duplicate TXT title(s): {', '.join(duplicate_file_titles)}")

    csv_title_set = {title for title in titles if title}
    file_title_set = set(files_by_title)
    missing_files = sorted(csv_title_set - file_title_set)
    extra_files = sorted(file_title_set - csv_title_set)
    if missing_files:
        errors.append(f"CSV title(s) without TXT: {', '.join(missing_files)}")
    if extra_files:
        errors.append(f"TXT file(s) without CSV metadata: {', '.join(extra_files)}")

    empty_files = [item.name for item in txt_files if item.stat().st_size == 0]
    if empty_files:
        errors.append(f"Empty TXT file(s): {', '.join(empty_files)}")
    if errors:
        raise CorpusValidationError("\n".join(errors))

    records: list[ImportRecord] = []
    for row, title in zip(rows, titles):
        publish_date = normalize_date(row.get("publish") or "")
        records.append(
            ImportRecord(
                title=title,
                file_path=files_by_title[title],
                metadata={
                    "title": title,
                    "office": (row.get("office") or "").strip() or None,
                    "publish_date": publish_date,
                    "type": (row.get("stage") or "").strip() or None,
                },
            )
        )
    return records


async def resolve_law_kb(container: ServiceContainer, kb_name: str) -> KnowledgeBase:
    async with container.session_factory() as session:
        result = await session.execute(
            select(KnowledgeBase, Domain.name)
            .join(Domain, KnowledgeBase.domain_id == Domain.id)
            .where(KnowledgeBase.name == kb_name)
        )
        row = result.one_or_none()

    if row is None:
        raise RuntimeError(f"Knowledge base not found: {kb_name}")
    kb, domain_name = row
    if domain_name != "law_cn":
        raise RuntimeError(
            f"Knowledge base {kb_name!r} belongs to {domain_name!r}, expected 'law_cn'"
        )
    if not kb.is_active:
        raise RuntimeError(f"Knowledge base is inactive: {kb_name}")
    return kb


async def run_document_operation(
    operation,
    task_id: str,
    on_progress: Callable[[dict[str, Any]], None] | None,
):
    queue = ProgressTracker.create(task_id)
    task = asyncio.create_task(operation)
    try:
        while not task.done() or not queue.empty():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.2)
            except TimeoutError:
                continue
            if on_progress:
                on_progress(event)
        return await task
    finally:
        ProgressTracker.remove(task_id)


async def import_records(
    container: ServiceContainer,
    kb: KnowledgeBase,
    records: list[ImportRecord],
    *,
    on_existing: str,
    stop_on_error: bool,
) -> ImportSummary:
    service = container.document_service
    summary = ImportSummary()
    overall = tqdm(records, desc="Importing laws", unit="document", dynamic_ncols=True)
    detail = tqdm(
        total=100,
        desc="Current document",
        unit="%",
        position=1,
        leave=False,
        dynamic_ncols=True,
    )

    try:
        for record in overall:
            detail.reset(total=100)
            detail.set_description_str(record.title[:28])
            existing = await container.doc_db.find_by_filename(kb.id, record.filename)

            if existing and on_existing == "skip":
                summary.skipped += 1
                overall.set_postfix(
                    imported=summary.imported,
                    updated=summary.updated,
                    skipped=summary.skipped,
                    failed=summary.failed,
                )
                continue
            if existing and on_existing == "fail":
                raise RuntimeError(f"Document already exists: {record.filename}")

            file_hash = calculate_file_sha256(str(record.file_path))
            duplicate_hash = await container.doc_db.find_by_hash(kb.id, file_hash)
            if duplicate_hash and duplicate_hash.id != getattr(existing, "id", None):
                message = (
                    f"Content already exists as {duplicate_hash.filename!r}; "
                    f"cannot import {record.filename!r}"
                )
                if stop_on_error:
                    raise RuntimeError(message)
                tqdm.write(f"ERROR: {message}")
                summary.failed += 1
                continue

            def update_detail(event: dict[str, Any]) -> None:
                progress = max(detail.n, float(event.get("progress", 0)))
                detail.n = min(progress, 100)
                detail.set_postfix_str(
                    f"{event.get('stage', '')}: {event.get('message', '')}"[:100]
                )
                detail.refresh()

            task_id = str(uuid.uuid4())
            try:
                if existing:
                    operation = service.update_document(
                        kb_id=kb.id,
                        doc_id=existing.id,
                        source=str(record.file_path),
                        filename=record.filename,
                        task_id=task_id,
                        metadata=record.metadata,
                    )
                else:
                    operation = service.add_document(
                        kb_id=kb.id,
                        source=str(record.file_path),
                        filename=record.filename,
                        mime_type="txt",
                        task_id=task_id,
                        file_size=record.file_path.stat().st_size,
                        metadata=record.metadata,
                    )
                await run_document_operation(operation, task_id, update_detail)
                detail.n = 100
                detail.refresh()
                if existing:
                    summary.updated += 1
                else:
                    summary.imported += 1
            except Exception as exc:
                summary.failed += 1
                tqdm.write(f"ERROR: {record.filename}: {exc}")
                if stop_on_error:
                    raise
            finally:
                overall.set_postfix(
                    imported=summary.imported,
                    updated=summary.updated,
                    skipped=summary.skipped,
                    failed=summary.failed,
                )
    finally:
        detail.close()
        overall.close()
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kb-name", default=DEFAULT_KB_NAME)
    parser.add_argument(
        "--metadata-csv",
        type=Path,
        default=DEFAULT_CORPUS_ROOT / "meta_data.csv",
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=DEFAULT_CORPUS_ROOT / "txt_utf8",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not write")
    parser.add_argument(
        "--on-existing",
        choices=("skip", "fail", "update"),
        default="skip",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop at the first document import failure",
    )
    return parser.parse_args(argv)


async def async_main(args: argparse.Namespace) -> int:
    records = build_manifest(args.metadata_csv.resolve(), args.documents_dir.resolve())
    print(f"Validated corpus: {len(records)} CSV row(s), {len(records)} TXT file(s)")
    missing_dates = sum(record.metadata["publish_date"] is None for record in records)
    print(f"Metadata: {missing_dates} document(s) have no publish date")

    container = ServiceContainer()
    try:
        await container.init_plugins()
        kb = await resolve_law_kb(container, args.kb_name)
        print(f"Target KB: {kb.name} (id={kb.id}, domain=law_cn)")
        strategy = await container.kb_db.get_active_strategy_config(kb.id)
        if strategy is None:
            raise RuntimeError(f"Knowledge base has no active retrieval strategy: {kb.name}")

        if args.dry_run:
            for _ in tqdm(records, desc="Checking files", unit="document", dynamic_ncols=True):
                pass
            print("Dry run completed; no data was written.")
            return 0

        summary = await import_records(
            container,
            kb,
            records,
            on_existing=args.on_existing,
            stop_on_error=args.stop_on_error,
        )
        print(
            "Import completed: "
            f"imported={summary.imported}, updated={summary.updated}, "
            f"skipped={summary.skipped}, failed={summary.failed}"
        )
        return 1 if summary.failed else 0
    finally:
        await container.engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return asyncio.run(async_main(args))
    except (CorpusValidationError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
