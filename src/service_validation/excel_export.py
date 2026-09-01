from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pythoncom
import pywintypes
from win32com.client import DispatchEx

from .pdf_merge import ProgressCallback


@dataclass(frozen=True, slots=True)
class ExcelUnavailableError(Exception):
    detail: str

    def __str__(self) -> str:
        return f"Microsoft Excel을 실행할 수 없습니다: {self.detail}"


@dataclass(frozen=True, slots=True)
class WorkbookExportError(Exception):
    workbook: Path
    detail: str

    def __str__(self) -> str:
        return f"{self.workbook.name}: PDF 변환 실패 - {self.detail}"


class ExcelWorkbookExporter:
    def export_all(
        self,
        workbooks: tuple[Path, ...],
        destination: Path,
        progress: ProgressCallback,
    ) -> tuple[Path, ...]:
        pythoncom.CoInitialize()
        try:
            try:
                excel = DispatchEx("Excel.Application")
            except pywintypes.com_error as exc:
                raise ExcelUnavailableError(str(exc)) from exc
            try:
                excel.Visible = False
                excel.DisplayAlerts = False
                excel.ScreenUpdating = False
                excel.AutomationSecurity = 3
                return self._export_workbooks(excel, workbooks, destination, progress)
            finally:
                excel.Quit()
        finally:
            pythoncom.CoUninitialize()

    @staticmethod
    def _export_workbooks(
        excel,
        workbooks: tuple[Path, ...],
        destination: Path,
        progress: ProgressCallback,
    ) -> tuple[Path, ...]:
        outputs: list[Path] = []
        total = len(workbooks)
        for index, source in enumerate(workbooks, 1):
            output = destination / f"{index:04d}.pdf"
            try:
                workbook = excel.Workbooks.Open(
                    str(source.resolve()),
                    UpdateLinks=0,
                    ReadOnly=True,
                )
            except pywintypes.com_error as exc:
                raise WorkbookExportError(source, str(exc)) from exc
            try:
                workbook.ExportAsFixedFormat(
                    Type=0,
                    Filename=str(output.resolve()),
                    Quality=0,
                    IncludeDocProperties=True,
                    IgnorePrintAreas=False,
                    OpenAfterPublish=False,
                )
            except pywintypes.com_error as exc:
                raise WorkbookExportError(source, str(exc)) from exc
            finally:
                workbook.Close(SaveChanges=False)
            outputs.append(output)
            progress(index, total, source.name)
        return tuple(outputs)
