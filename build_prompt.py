from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"

MASTER_PROMPT_PATH = PROMPTS_DIR / "master_prompt.txt"
OUTPUT_PROMPT_PATH = PROMPTS_DIR / "today_prompt.txt"


TURKISH_DAYS = {
    "Monday": "Pazartesi",
    "Tuesday": "Salı",
    "Wednesday": "Çarşamba",
    "Thursday": "Perşembe",
    "Friday": "Cuma",
    "Saturday": "Cumartesi",
    "Sunday": "Pazar",
}


PROMPT_HEADER = """
# ÜRETİM MODU

Bu metin analiz edilmek, özetlenmek veya açıklanmak için verilmedi.

Bu bir üretim promptudur.

Görev:
Aşağıdaki kurallara göre 16 sayfalık Gazet+E gazetesi için doğrudan ve yalnızca geçerli issue.json üret.

Kesin kurallar:
- Promptu analiz etme.
- Promptu açıklama.
- Promptu özetleme.
- "Elbette", "İşte JSON", "Aşağıda" gibi giriş cümleleri yazma.
- Markdown kullanma.
- Kod bloğu açma.
- JSON dışında hiçbir metin üretme.

Şimdi aşağıdaki üretim talimatlarını uygula.

────────────────────────
""".strip()


PROMPT_FOOTER = """
────────────────────────
SON KOMUT
────────────────────────

Yukarıdaki tüm kuralları uygula.

Sadece geçerli issue.json üret.

JSON dışında hiçbir açıklama, not, başlık, markdown veya kod bloğu yazma.
""".strip()


def get_today_info() -> dict:
    today = datetime.now()

    issue_date = today.strftime("%d.%m.%Y")
    english_day = today.strftime("%A")
    issue_day = TURKISH_DAYS.get(english_day, english_day)
    issue_number = today.strftime("%Y%m%d")

    return {
        "issue_date": issue_date,
        "issue_day": issue_day,
        "issue_number": issue_number,
    }


def load_master_prompt() -> str:
    if not MASTER_PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Master prompt bulunamadı: {MASTER_PROMPT_PATH}"
        )

    return MASTER_PROMPT_PATH.read_text(encoding="utf-8")


def render_prompt(template: str, context: dict) -> str:
    rendered = template

    for key, value in context.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", str(value))

    return rendered


def wrap_prompt(prompt_body: str) -> str:
    return f"{PROMPT_HEADER}\n\n{prompt_body.strip()}\n\n{PROMPT_FOOTER}\n"


def save_prompt(prompt: str) -> None:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PROMPT_PATH.write_text(prompt, encoding="utf-8")


def main() -> None:
    context = get_today_info()

    master_prompt = load_master_prompt()
    rendered_prompt = render_prompt(master_prompt, context)
    final_prompt = wrap_prompt(rendered_prompt)

    save_prompt(final_prompt)

    print("Prompt başarıyla üretildi.")
    print(f"Dosya: {OUTPUT_PROMPT_PATH}")
    print(f"Tarih: {context['issue_date']} - {context['issue_day']}")
    print(f"Sayı: {context['issue_number']}")


if __name__ == "__main__":
    main()
