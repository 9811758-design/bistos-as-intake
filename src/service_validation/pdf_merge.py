from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Final, Protocol

from pypdf import PdfWriter

REPORT_PREFIX: Final = "서비스검증결과서_"
EXCLUDED_MARKERS: Final = ("발행이력", "발행현황")
SERVICE_NUMBER_PATTERN: Final = re.compile(r"DS\d{8}", re.IGNORECASE)
ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True, slots=True)
class PdfMergeJob:
    workbooks: tuple[Path, ...]
    output: Path


@dataclass(frozen=True, slots=True)
class EmptyMergeError(Exception):
    kind: str

    def __str__(self) -> str:
        return f"병합할 {self.kind} 파일이 없습니다."


class WorkbookExporter(Protocol):
    def export_all(
        self,
        workbooks: tuple[Path, ...],
        destination: Path,
        progress: ProgressCallback,
    ) -> tuple[Path, ...]: ...


def discover_workbooks(folder: Path) -> tuple[Path, ...]:
    candidates = (
        path
        for path in folder.glob("*.xlsx")
        if path.name.startswith(REPORT_PREFIX)
        and not path.name.startswith("~$")
        and not any(marker in path.name for marker in EXCLUDED_MARKERS)
    )
    return tuple(sorted(candidates, key=_workbook_sort_key))


def default_output_path(folder: Path, created_at: datetime) -> Path:
    return folder / f"서비스검증결과서_통합_{created_at:%Y%m%d_%H%M%S}.pdf"


def service_number_from_filename(path: Path) -> str:
    match = SERVICE_NUMBER_PATTERN.search(path.name)
    return match.group(0).upper() if match else "-"


def _workbook_sort_key(path: Path) -> tuple[str, str]:
    parsed = service_number_from_filename(path)
    service_number = parsed if parsed != "-" else "ZZZZZZZZZZ"
    return service_number, path.name.casefold()


def merge_pdf_files(pdf_files: tuple[Path, ...], output: Path) -> None:
    if not pdf_files:
        raise EmptyMergeError("PDF")
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for pdf_file in pdf_files:
        writer.append(pdf_file)
    with NamedTemporaryFile(
        mode="wb",
        suffix=".pdf",
        prefix="service-validation-merge-",
        dir=output.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        writer.write(stream)
    temporary.replace(output)


def create_combined_pdf(
    job: PdfMergeJob,
    exporter: WorkbookExporter,
    progress: ProgressCallback,
) -> Path:
    if not job.workbooks:
        raise EmptyMergeError("엑셀")
    with TemporaryDirectory(prefix="service-validation-pdf-") as temporary:
        pdf_files = exporter.export_all(job.workbooks, Path(temporary), progress)
        merge_pdf_files(pdf_files, job.output)
    return job.output
