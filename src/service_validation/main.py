from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path

from .domain import ValidationError
from .enhanced_app import EnhancedGeneratorApp
from .report_writer import generate_workbook
from .service import create_report, load_record
from .workbook import load_overrides, read_source


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="서비스 검증결과서 생성기")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--service-number")
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--record-file", type=Path)
    parser.add_argument("--result-file", type=Path)
    parser.add_argument("--error-file", type=Path)
    return parser


def run_automation(
    source: Path,
    template: Path,
    output: Path,
    service_number: str,
    overrides: Path | None,
) -> Path:
    rows = read_source(source, load_overrides(overrides) if overrides else None)
    matches = [record for record in rows.records if record.service_number == service_number]
    if len(matches) != 1:
        raise ValidationError(f"서비스번호 행을 정확히 하나 찾을 수 없습니다: {service_number}")
    return generate_workbook(template, output, matches[0])


def main() -> int:
    args = _parser().parse_args()
    record_automation = all((args.template, args.output, args.record_file, args.result_file))
    if record_automation:
        try:
            result = create_report(args.template, args.output, load_record(args.record_file))
            args.result_file.write_text(str(result), encoding="utf-8")
        except (OSError, ValidationError) as exc:
            if args.error_file is not None:
                args.error_file.write_text(str(exc), encoding="utf-8")
            print(f"오류: {exc}", file=sys.stderr)
            return 1
        return 0
    automation = all((args.source, args.template, args.output, args.service_number))
    if automation:
        try:
            result = run_automation(
                args.source, args.template, args.output, args.service_number, args.overrides
            )
        except (OSError, ValidationError) as exc:
            print(f"오류: {exc}", file=sys.stderr)
            return 1
        print(result)
        return 0
    root = tk.Tk()
    EnhancedGeneratorApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
