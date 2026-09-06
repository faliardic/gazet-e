from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import shutil
import webbrowser


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[1]


def command_python() -> str:
    if not getattr(sys, "frozen", False):
        return sys.executable
    return shutil.which("python") or shutil.which("py") or "python"


PROJECT_ROOT = project_root()


class GazetteStudio:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Gazet+E Studio")
        self.root.geometry("860x560")
        self.root.minsize(720, 460)
        self.root.configure(bg="#f3f5f7")

        container = tk.Frame(self.root, bg="#f3f5f7", padx=22, pady=18)
        container.pack(fill="both", expand=True)
        tk.Label(container, text="Gazet+E Studio", font=("Segoe UI", 24, "bold"), bg="#f3f5f7").pack(anchor="w")
        tk.Label(container, text="Gazete üretimi, raporlar, Random Haber ve extension kontrol merkezi.", font=("Segoe UI", 10), bg="#f3f5f7", fg="#5f6875").pack(anchor="w", pady=(2, 16))

        actions = tk.Frame(container, bg="#f3f5f7")
        actions.pack(fill="x", pady=(0, 14))
        buttons = [
            ("Gazete Üret", self.build_issue),
            ("Hızlı Taslak", self.build_fast_issue),
            ("Son PDF'i Aç", lambda: self.open_path(PROJECT_ROOT / "dist" / "gazete.pdf")),
            ("Son HTML'i Aç", lambda: self.open_path(PROJECT_ROOT / "dist" / "gazete.html")),
            ("Random Haber", self.open_random_news),
            ("Kaynak Raporu", lambda: self.open_path(PROJECT_ROOT / "dist" / "source_report.html")),
            ("Extension Klasörü", lambda: self.open_path(PROJECT_ROOT / "chrome_extension" / "gazette_raw_reader")),
            ("Cache Temizle", self.clean_cache),
            ("Testleri Çalıştır", self.run_tests),
        ]
        for label, command in buttons:
            tk.Button(actions, text=label, command=command, padx=12, pady=8).pack(side="left", padx=(0, 8), pady=4)

        self.log = tk.Text(container, wrap="word", height=20, bg="#111827", fg="#d1d5db", insertbackground="#fff")
        self.log.pack(fill="both", expand=True)
        self.write_log("Hazır.\n")

    def write_log(self, text: str) -> None:
        self.log.insert("end", text)
        self.log.see("end")
        self.root.update_idletasks()

    def run_command(self, args: list[str]) -> None:
        self.write_log(f"\n$ {' '.join(args)}\n")
        try:
            process = subprocess.run(args, cwd=PROJECT_ROOT, text=True, capture_output=True, timeout=360)
        except Exception as exc:
            messagebox.showerror("Gazet+E Studio", str(exc))
            return
        self.write_log(process.stdout)
        if process.stderr:
            self.write_log(process.stderr)
        if process.returncode != 0:
            messagebox.showerror("Gazet+E Studio", f"Komut başarısız: {process.returncode}")

    def build_issue(self) -> None:
        self.run_command([command_python(), "-m", "chatgpt_haber.cli", "build", "--mode", "full", "--out", "dist/gazete.pdf"])

    def build_fast_issue(self) -> None:
        self.run_command([command_python(), "-m", "chatgpt_haber.cli", "build", "--mode", "fast", "--out", "dist/gazete.pdf"])

    def run_tests(self) -> None:
        self.run_command([command_python(), "-m", "pytest", "-q"])

    def open_random_news(self) -> None:
        exe = PROJECT_ROOT / "dist" / "GazetteRandomHaber.exe"
        if exe.exists():
            subprocess.Popen([str(exe)], cwd=PROJECT_ROOT)
        else:
            self.run_command([command_python(), "apps/random_news_app.py"])

    def open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showinfo("Gazet+E Studio", f"Bulunamadı: {path}")
            return
        webbrowser.open(str(path))

    def clean_cache(self) -> None:
        removed = 0
        for root in (PROJECT_ROOT / "dist" / "articles", PROJECT_ROOT / "dist" / "assets"):
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.is_file():
                    path.unlink(missing_ok=True)
                    removed += 1
        self.write_log(f"Cache temizlendi. Silinen dosya: {removed}\n")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    GazetteStudio().run()


if __name__ == "__main__":
    main()
