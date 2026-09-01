from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from service_validation.pdf_merge import (
    PdfMergeJob,
    create_combined_pdf,
    default_output_path,
    discover_workbooks,
    merge_pdf_files,
)


class FakeWorkbookExporter:
    def __init__(self) -> None:
        self.received: tuple[Path, ...] = ()

    def export_all(
        self,
        workbooks: tuple[Path, ...],
        destination: Path,
        progress: Callable[[int, int, str], None],
    ) -> tuple[Path, ...]:
        self.received = workbooks
        outputs: list[Path] = []
        for index, workbook in enumerate(workbooks, 1):
            output = destination / f"{index}.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=index * 100, height=200)
            with output.open("wb") as stream:
                writer.write(stream)
            outputs.append(output)
            progress(index, len(workbooks), workbook.name)
        return tuple(outputs)


def test_discover_workbooks_excludes_management_files_and_sorts_service_numbers(
    tmp_path: Path,
) -> None:
    (tmp_path / "서비스검증결과서_DS26071502_고객.xlsx").touch()
    (tmp_path / "서비스검증결과서_DS26070101_고객.xlsx").touch()
    (tmp_path / "서비스검증결과서_발행이력.xlsx").touch()
    (tmp_path / "서비스검증결과서_발행현황_20260720.xlsx").touch()
    (tmp_path / "~$서비스검증결과서_DS26060101_고객.xlsx").touch()
    (tmp_path / "다른문서.xlsx").touch()

    discovered = discover_workbooks(tmp_path)

    assert [path.name for path in discovered] == [
        "서비스검증결과서_DS26070101_고객.xlsx",
        "서비스검증결과서_DS26071502_고객.xlsx",
    ]


def test_merge_pdf_files_preserves_input_order_and_all_pages(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "combined.pdf"
    first_writer = PdfWriter()
    first_writer.add_blank_page(width=100, height=200)
    with first.open("wb") as stream:
        first_writer.write(stream)
    second_writer = PdfWriter()
    second_writer.add_blank_page(width=200, height=300)
    second_writer.add_blank_page(width=300, height=400)
    with second.open("wb") as stream:
        second_writer.write(stream)

    merge_pdf_files((first, second), output)

    reader = PdfReader(output)
    assert len(reader.pages) == 3
    assert float(reader.pages[0].mediabox.width) == 100
    assert float(reader.pages[1].mediabox.width) == 200
    assert float(reader.pages[2].mediabox.width) == 300


def test_create_combined_pdf_exports_each_workbook_and_reports_progress(
    tmp_path: Path,
) -> None:
    workbooks = (tmp_path / "first.xlsx", tmp_path / "second.xlsx")
    output = tmp_path / "combined.pdf"
    exporter = FakeWorkbookExporter()
    events: list[tuple[int, int, str]] = []

    result = create_combined_pdf(
        PdfMergeJob(workbooks=workbooks, output=output),
        exporter,
        lambda current, total, message: events.append((current, total, message)),
    )

    assert result == output
    assert exporter.received == workbooks
    assert events == [(1, 2, "first.xlsx"), (2, 2, "second.xlsx")]
    assert len(PdfReader(output).pages) == 2


def test_default_output_path_uses_selected_folder_and_timestamp(tmp_path: Path) -> None:
    output = default_output_path(tmp_path, datetime(2026, 7, 20, 14, 35, 12))

    assert output == tmp_path / "서비스검증결과서_통합_20260720_143512.pdf"
