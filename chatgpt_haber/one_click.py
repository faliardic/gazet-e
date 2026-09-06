from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import threading
import traceback
from tkinter import Tk, Label, Button, StringVar, messagebox, ttk

from chatgpt_haber.cli import run_build


def desktop_dir() -> Path:
    return Path.home() / "Desktop"


def output_path_for_today() -> Path:
    today = date.today().isoformat()
    return desktop_dir() / "GazetE" / f"gazete-{today}.pdf"


def build_today_issue(status: StringVar, done: threading.Event, result: dict[str, object]) -> None:
    out = output_path_for_today()
    try:
        status.set("Haberler toplanıyor ve gazete oluşturuluyor...")
        run_build(
            issue_date=date.today().isoformat(),
            paper_size="A3",
            out=out,
            input_json=None,
            live=True,
            portable_html=False,
            mode="full",
        )
        result["out"] = out
    except Exception as exc:
        log_path = out.parent / "son-hata.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        result["error"] = exc
        result["log_path"] = log_path
    finally:
        done.set()


def main() -> None:
    root = Tk()
    root.title("Gazet+E")
    root.geometry("460x180")
    root.resizable(False, False)

    status = StringVar(value="Gazete oluşturuluyor...")
    done = threading.Event()
    result: dict[str, object] = {}

    Label(root, text="Gazet+E", font=("Segoe UI", 18, "bold")).pack(pady=(20, 4))
    Label(root, textvariable=status, font=("Segoe UI", 11)).pack(pady=(0, 14))

    progress = ttk.Progressbar(root, mode="indeterminate", length=360)
    progress.pack(pady=(0, 18))
    progress.start(12)

    close_button = Button(root, text="Kapat", command=root.destroy, state="disabled", width=14)
    close_button.pack()

    def poll_result() -> None:
        if not done.is_set():
            root.after(250, poll_result)
            return

        progress.stop()
        close_button.config(state="normal")
        error = result.get("error")
        if error:
            log_path = result.get("log_path")
            status.set("Gazete oluşturulamadı.")
            messagebox.showerror(
                "Gazet+E",
                f"Gazete oluşturulamadı.\n\nHata: {error}\n\nAyrıntı: {log_path}",
            )
            return

        out = result["out"]
        status.set(f"Gazete oluşturuldu:\n{out}")
        messagebox.showinfo("Gazet+E", f"Gazete oluşturuldu:\n\n{out}")

    worker = threading.Thread(target=build_today_issue, args=(status, done, result), daemon=True)
    worker.start()
    root.after(250, poll_result)
    root.mainloop()

    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
