from __future__ import annotations

import argparse
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog

from .app import ASIntakeApp
from .config import (
    AppConfig,
    default_config_path,
    default_oauth_token_path,
    load_config,
    save_config,
)
from .demo_gateway import DemoSheetGateway
from .service import ASIntakeService


def _service(config: AppConfig) -> ASIntakeService:
    from .feedback import LocalRecommendationFeedbackStore, default_feedback_path
    from .google_gateway import GoogleSheetsGateway
    from .google_transport import GoogleAuthTransport

    transport = GoogleAuthTransport(
        Path(config.oauth_client_file),
        default_oauth_token_path(),
    )
    return ASIntakeService(
        GoogleSheetsGateway(config.spreadsheet_id, transport),
        LocalRecommendationFeedbackStore(default_feedback_path()),
    )


def _choose_config(root: tk.Tk, current: AppConfig) -> AppConfig | None:
    selected = filedialog.askopenfilename(
        parent=root,
        title="Google OAuth 클라이언트 JSON 선택",
        filetypes=(("JSON 파일", "*.json"), ("모든 파일", "*.*")),
        initialdir=str(Path(current.oauth_client_file).parent)
        if current.oauth_client_file
        else str(Path.home()),
    )
    if not selected:
        return None
    receiver = simpledialog.askstring(
        "기본 접수자",
        "새 접수에 자동 입력할 접수자 이름을 입력하세요.",
        initialvalue=current.default_receiver,
        parent=root,
    )
    return AppConfig(
        spreadsheet_id=current.spreadsheet_id,
        oauth_client_file=selected,
        default_receiver=receiver or "",
    )


def _live_app(root: tk.Tk) -> ASIntakeApp | None:
    config_path = default_config_path()
    config = load_config(config_path)
    if not Path(config.oauth_client_file).is_file():
        root.withdraw()
        chosen = _choose_config(root, config)
        if chosen is None:
            messagebox.showinfo(
                "설정 필요",
                "실행하려면 Google OAuth 클라이언트 JSON이 필요합니다.\n"
                "데모는 --demo 옵션으로 실행할 수 있습니다.",
                parent=root,
            )
            return None
        config = chosen
        save_config(config_path, config)
    try:
        service = _service(config)
    except (OSError, ValueError) as error:
        root.withdraw()
        messagebox.showerror(
            "Google 설정 오류",
            f"저장된 Google OAuth 설정을 사용할 수 없습니다.\n{error}",
            parent=root,
        )
        chosen = _choose_config(root, config)
        if chosen is None:
            return None
        try:
            service = _service(chosen)
        except (OSError, ValueError) as retry_error:
            messagebox.showerror("Google 설정 오류", str(retry_error), parent=root)
            return None
        config = chosen
        save_config(config_path, config)
    root.deiconify()
    app: ASIntakeApp

    def change_settings() -> None:
        nonlocal config
        chosen = _choose_config(root, config)
        if chosen is None:
            return
        try:
            replacement = _service(chosen)
        except (OSError, ValueError) as error:
            messagebox.showerror("Google 설정 오류", str(error), parent=root)
            return
        config = chosen
        save_config(config_path, config)
        app.replace_service(replacement, config.default_receiver)

    app = ASIntakeApp(root, service, config.default_receiver, change_settings)
    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    if args.demo:
        from .feedback import LocalRecommendationFeedbackStore, default_feedback_path

        ASIntakeApp(
            root,
            ASIntakeService(
                DemoSheetGateway(),
                LocalRecommendationFeedbackStore(default_feedback_path()),
            ),
            "장진영",
        )
    elif _live_app(root) is None:
        root.destroy()
        return 1
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
