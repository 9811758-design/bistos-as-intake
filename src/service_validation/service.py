from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TypedDict

from .domain import Customer, CustomerClass, ServiceRecord, ValidationError
from .report_writer import generate_workbook
from .selection import MAX_BATCH_SIZE


class RecordPayload(TypedDict):
    service_number: str
    receipt_date: str
    receiver: str
    requester: str
    hospital: str
    customer_category: str
    customer_name: str
    model: str
    defect_category: str
    service_details: str
    processing_details: str
    completion_date: str
    processor: str


@dataclass(frozen=True, slots=True)
class ReportFailure:
    record: ServiceRecord
    detail: str


@dataclass(frozen=True, slots=True)
class BatchReportResult:
    successful_records: tuple[ServiceRecord, ...]
    outputs: tuple[Path, ...]
    failures: tuple[ReportFailure, ...]


def create_report(template: Path, output_folder: Path, record: ServiceRecord) -> Path:
    return generate_workbook(template, output_folder, record)


def save_record(path: Path, record: ServiceRecord) -> None:
    payload = RecordPayload(
        service_number=record.service_number,
        receipt_date=record.receipt_date.isoformat(),
        receiver=record.receiver,
        requester=record.requester,
        hospital=record.hospital,
        customer_category=record.customer.category.value,
        customer_name=record.customer.display_name,
        model=record.model,
        defect_category=record.defect_category,
        service_details=record.service_details,
        processing_details=record.processing_details,
        completion_date=record.completion_date.isoformat(),
        processor=record.processor,
    )
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_record(path: Path) -> ServiceRecord:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidationError("일괄 생성 데이터 형식이 올바르지 않습니다.")
    try:
        payload = RecordPayload(**raw)
        customer = Customer(
            category=CustomerClass(payload["customer_category"]),
            display_name=payload["customer_name"],
        )
        return ServiceRecord(
            service_number=payload["service_number"],
            receipt_date=date.fromisoformat(payload["receipt_date"]),
            receiver=payload["receiver"],
            requester=payload["requester"],
            hospital=payload["hospital"],
            customer=customer,
            model=payload["model"],
            defect_category=payload["defect_category"],
            service_details=payload["service_details"],
            processing_details=payload["processing_details"],
            completion_date=date.fromisoformat(payload["completion_date"]),
            processor=payload["processor"],
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("일괄 생성 데이터를 읽을 수 없습니다.") from exc


def _worker_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "service_validation.main"]


def create_reports(
    template: Path,
    output_folder: Path,
    records: tuple[ServiceRecord, ...],
) -> BatchReportResult:
    if not records:
        raise ValidationError("생성할 행을 하나 이상 선택하세요.")
    if len(records) > MAX_BATCH_SIZE:
        raise ValidationError(f"한 번에 최대 {MAX_BATCH_SIZE}개까지 생성할 수 있습니다.")
    successful_records: list[ServiceRecord] = []
    outputs: list[Path] = []
    failures: list[ReportFailure] = []
    with TemporaryDirectory(prefix="service-validation-") as temporary:
        working = Path(temporary)
        for index, record in enumerate(records):
            record_file = working / f"record-{index}.json"
            result_file = working / f"result-{index}.txt"
            error_file = working / f"error-{index}.txt"
            save_record(record_file, record)
            command = [
                *_worker_command(),
                "--template",
                str(template),
                "--output",
                str(output_folder),
                "--record-file",
                str(record_file),
                "--result-file",
                str(result_file),
                "--error-file",
                str(error_file),
            ]
            completed = subprocess.run(command, check=False)
            if completed.returncode != 0 or not result_file.exists():
                detail = (
                    error_file.read_text(encoding="utf-8").strip()
                    if error_file.exists()
                    else "상세 오류를 확인할 수 없습니다."
                )
                failures.append(ReportFailure(record=record, detail=detail))
                continue
            successful_records.append(record)
            outputs.append(Path(result_file.read_text(encoding="utf-8")))
    return BatchReportResult(
        successful_records=tuple(successful_records),
        outputs=tuple(outputs),
        failures=tuple(failures),
    )
