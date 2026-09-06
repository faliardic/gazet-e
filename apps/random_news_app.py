from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import webbrowser

from services.random_news_service import NewsItem, RandomNewsService


def extension_reader_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["gazette_raw"] = "1"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class RandomNewsApp:
    def __init__(self) -> None:
        self.service = RandomNewsService()
        self.current: NewsItem | None = None
        self.root = tk.Tk()
        self.root.title("Gazet+E Random Haber")
        self.root.geometry("820x620")
        self.root.minsize(620, 440)
        self.root.configure(bg="#f3f5f7")

        self.title_var = tk.StringVar()
        self.meta_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Random Haber tuşuna basınca temiz haber havuzundan bir haber gelir.")
        self.link_var = tk.StringVar()

        container = tk.Frame(self.root, padx=24, pady=22, bg="#f3f5f7")
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg="#f3f5f7")
        header.pack(fill="x", pady=(0, 16))
        tk.Label(header, text="Gazet+E Random Haber", font=("Segoe UI", 22, "bold"), bg="#f3f5f7", fg="#15181c").pack(
            anchor="w"
        )
        tk.Label(header, textvariable=self.status_var, font=("Segoe UI", 10), bg="#f3f5f7", fg="#5f6875").pack(
            anchor="w", pady=(4, 0)
        )

        top_actions = tk.Frame(container, bg="#f3f5f7")
        top_actions.pack(fill="x", pady=(0, 14))
        self.random_button = tk.Button(
            top_actions,
            text="Random Haber",
            command=self.show_random_news,
            font=("Segoe UI", 13, "bold"),
            padx=18,
            pady=10,
            bg="#1f4f8f",
            fg="white",
            activebackground="#173c6e",
            activeforeground="white",
            relief="flat",
        )
        self.random_button.pack(side="left")

        self.card = tk.Frame(container, bg="white", highlightbackground="#d7dde5", highlightthickness=1, padx=20, pady=18)
        self.card.pack(fill="both", expand=True)

        tk.Label(self.card, textvariable=self.title_var, font=("Segoe UI", 20, "bold"), bg="white", fg="#111827", wraplength=680, justify="left").pack(
            anchor="w", fill="x"
        )
        tk.Label(self.card, textvariable=self.meta_var, font=("Segoe UI", 10), bg="white", fg="#667085", wraplength=680, justify="left").pack(
            anchor="w", pady=(8, 12), fill="x"
        )
        self.summary = tk.Text(self.card, height=14, wrap="word", padx=10, pady=8, relief="flat", bg="#f8fafc", fg="#1f2937")
        self.summary.pack(fill="both", expand=True)
        self.summary.configure(state="disabled")
        tk.Label(self.card, textvariable=self.link_var, font=("Segoe UI", 9), bg="white", fg="#1f4f8f", wraplength=680, justify="left").pack(
            anchor="w", pady=(8, 12), fill="x"
        )

        buttons = tk.Frame(self.card, bg="white")
        buttons.pack(fill="x")
        self.open_button = tk.Button(buttons, text="Haberi Aç", command=self.open_news, state="disabled", padx=12, pady=7)
        self.open_button.pack(side="left", padx=(0, 8))
        self.copy_button = tk.Button(buttons, text="Linki Kopyala", command=self.copy_link, state="disabled", padx=12, pady=7)
        self.copy_button.pack(side="left", padx=(0, 8))
        self.like_button = tk.Button(buttons, text="Beğendim", command=lambda: self.feedback("like"), state="disabled", padx=12, pady=7)
        self.like_button.pack(side="left", padx=(0, 8))
        self.dislike_button = tk.Button(buttons, text="Beğenmedim", command=lambda: self.feedback("dislike"), state="disabled", padx=12, pady=7)
        self.dislike_button.pack(side="left", padx=(0, 8))
        self.save_button = tk.Button(buttons, text="Notlara Kaydet", command=self.save_news, state="disabled", padx=12, pady=7)
        self.save_button.pack(side="left", padx=(0, 8))
        self.desktop_button = tk.Button(buttons, text="Gazeteyi Masaüstüne Kopyala", command=self.copy_gazette_to_desktop, padx=12, pady=7)
        self.desktop_button.pack(side="left", padx=(0, 8))
        tk.Button(buttons, text="Kapat", command=self.root.destroy, padx=12, pady=7).pack(side="right")

        self.show_empty_state()

    def show_random_news(self) -> None:
        self.status_var.set("Haber seçiliyor...")
        self.root.update_idletasks()
        try:
            item = self.service.pick_random_news()
        except Exception as exc:
            messagebox.showerror("Gazet+E Random Haber", f"Haber yüklenemedi: {exc}")
            item = None
        if item is None:
            self.current = None
            self.title_var.set("Şu anda gösterilecek güncel haber bulunamadı.")
            self.meta_var.set("")
            self.link_var.set("")
            self.set_summary("Cache dosyası bulunamadı veya uygun haber havuzu boş.")
            self.status_var.set("Gösterilecek haber bulunamadı.")
            self.open_button.configure(state="disabled")
            self.copy_button.configure(state="disabled")
            self.like_button.configure(state="disabled")
            self.dislike_button.configure(state="disabled")
            self.save_button.configure(state="disabled")
            return
        self.current = item
        self.title_var.set(item.title)
        meta = " | ".join(part for part in (item.source, item.published_at, item.category) if part)
        self.meta_var.set(meta)
        self.link_var.set(item.url)
        self.set_summary(item.full_text or "Haber metni bulunamadı.")
        self.status_var.set("Yeni random haber hazır.")
        self.open_button.configure(state="normal")
        self.copy_button.configure(state="normal")
        self.like_button.configure(state="normal")
        self.dislike_button.configure(state="normal")
        self.save_button.configure(state="normal")

    def show_empty_state(self) -> None:
        self.current = None
        self.title_var.set("Henüz haber seçilmedi")
        self.meta_var.set("")
        self.link_var.set("")
        self.set_summary("Random Haber tuşuna bas. Uygulama mevcut temizlenmiş Gazet+E haber havuzundan rastgele bir haber seçecek ve tam haber metnini gösterecek.")
        self.open_button.configure(state="disabled")
        self.copy_button.configure(state="disabled")
        self.like_button.configure(state="disabled")
        self.dislike_button.configure(state="disabled")
        self.save_button.configure(state="disabled")

    def set_summary(self, text: str) -> None:
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text)
        self.summary.configure(state="disabled")

    def open_news(self) -> None:
        if self.current and self.current.url:
            webbrowser.open(extension_reader_url(self.current.url))

    def copy_link(self) -> None:
        if self.current and self.current.url:
            self.root.clipboard_clear()
            self.root.clipboard_append(self.current.url)
            self.status_var.set("Link kopyalandı.")

    def feedback(self, action: str) -> None:
        if self.current:
            self.service.save_feedback(self.current, action)
            self.status_var.set("Geri bildirim kaydedildi.")

    def save_news(self) -> None:
        if self.current:
            self.service.save_news(self.current)
            self.status_var.set("Haber notlara kaydedildi.")

    def copy_gazette_to_desktop(self) -> None:
        try:
            target = self.service.copy_latest_gazette_to_desktop()
        except Exception as exc:
            messagebox.showerror("Gazet+E Random Haber", f"Gazete kopyalanamadı: {exc}")
            return
        self.status_var.set(f"Gazete masaüstüne kopyalandı: {target}")

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    RandomNewsApp().run()


if __name__ == "__main__":
    main()
