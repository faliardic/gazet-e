from __future__ import annotations

from copy import deepcopy
from datetime import date
from html import escape
from pathlib import Path
import shutil
from typing import Optional

from .cli import run_build
from .issue import read_json, write_json
from .render import render_html


GITHUB_URL = "https://github.com/faliardic/chatgpt-haber"
MONTHS_TR = {
    "01": "Ocak",
    "02": "Şubat",
    "03": "Mart",
    "04": "Nisan",
    "05": "Mayıs",
    "06": "Haziran",
    "07": "Temmuz",
    "08": "Ağustos",
    "09": "Eylul",
    "10": "Ekim",
    "11": "Kasım",
    "12": "Aralik",
}


def publish_pages_site(
    *,
    docs_dir: Path,
    staging_dir: Path,
    issue_date: str | None = None,
    live: bool = True,
    input_json: Optional[Path] = None,
) -> dict[str, Path]:
    if issue_date is None:
        issue_date = date.today().isoformat()

    staging_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / ".nojekyll").write_text("", encoding="utf-8")

    build_result = run_build(
        issue_date=issue_date,
        paper_size="A3",
        out=staging_dir / "gazete.pdf",
        input_json=input_json,
        live=live,
        portable_html=False,
        mode="full",
    )
    issue_data = read_json(Path(build_result["issue_json"]))
    archive_date = str(issue_data.get("issue", {}).get("issue_date") or issue_date)

    pdf_path = docs_dir / "gazete.pdf"
    issue_json_path = docs_dir / "issue.json"
    index_html_path = docs_dir / "index.html"
    shutil.copy2(Path(build_result["pdf"]), pdf_path)
    write_json(issue_json_path, issue_data)
    render_site_html(
        issue_data,
        index_html_path,
        pdf_href="gazete.pdf",
        archive_href="archive/",
    )

    archive_issue_dir = docs_dir / "archive" / archive_date
    archive_issue_dir.mkdir(parents=True, exist_ok=True)
    archive_pdf_path = archive_issue_dir / "gazete.pdf"
    archive_json_path = archive_issue_dir / "issue.json"
    archive_html_path = archive_issue_dir / "index.html"
    shutil.copy2(pdf_path, archive_pdf_path)
    write_json(archive_json_path, issue_data)
    render_site_html(
        issue_data,
        archive_html_path,
        pdf_href="gazete.pdf",
        archive_href="../",
    )

    archive_index = write_archive_index(docs_dir / "archive")
    return {
        "index_html": index_html_path,
        "pdf": pdf_path,
        "issue_json": issue_json_path,
        "nojekyll": docs_dir / ".nojekyll",
        "archive_index": archive_index,
        "archive_issue_dir": archive_issue_dir,
        "archive_issue_html": archive_html_path,
        "archive_issue_pdf": archive_pdf_path,
        "archive_issue_json": archive_json_path,
    }


def render_site_html(issue_data: dict, html_path: Path, *, pdf_href: str, archive_href: str) -> None:
    render_html(
        deepcopy(issue_data),
        html_path,
        portable_pdf_links=True,
        portable_assets=True,
        include_brief_details=True,
        web_publish=True,
        web_toolbar={
            "pdf_href": pdf_href,
            "archive_href": archive_href,
            "github_href": GITHUB_URL,
        },
    )
    strip_trailing_whitespace(html_path)


def strip_trailing_whitespace(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(line.rstrip() for line in lines) + "\n", encoding="utf-8")


def write_archive_index(archive_dir: Path) -> Path:
    archive_dir.mkdir(parents=True, exist_ok=True)
    entries = archive_entries(archive_dir)
    rows = "\n".join(
        f"""      <li class="archive-item">
        <span>{escape(format_archive_date(entry.name))}</span>
        <a href="{escape(entry.name)}/">Gazeteyi Aç</a>
        <a href="{escape(entry.name)}/gazete.pdf">PDF İndir</a>
      </li>"""
        for entry in entries
    )
    html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gazet+E Arşiv</title>
  <style>
    body {{
      background: #f3f5f7;
      color: #111;
      font-family: Arial, Helvetica, sans-serif;
      margin: 0;
    }}
    main {{
      margin: 0 auto;
      max-width: 860px;
      padding: 32px 18px;
    }}
    h1 {{
      font-size: clamp(28px, 6vw, 48px);
      margin: 0 0 24px;
    }}
    .archive-list {{
      display: grid;
      gap: 10px;
      list-style: none;
      margin: 0;
      padding: 0;
    }}
    .archive-item {{
      align-items: center;
      background: #fff;
      border: 1px solid #d8dde5;
      display: grid;
      gap: 10px 16px;
      grid-template-columns: minmax(0, 1fr) auto auto;
      padding: 14px 16px;
    }}
    .archive-item span {{
      font-weight: 800;
    }}
    .archive-item a {{
      color: #111;
      font-weight: 800;
      text-decoration: none;
      text-transform: uppercase;
    }}
    .archive-item a:hover {{
      text-decoration: underline;
    }}
    @media (max-width: 560px) {{
      .archive-item {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <h1>Gazet+E Arşiv</h1>
    <ol class="archive-list">
{rows}
    </ol>
  </main>
</body>
</html>
"""
    path = archive_dir / "index.html"
    path.write_text(html, encoding="utf-8")
    return path


def archive_entries(archive_dir: Path) -> list[Path]:
    entries = [
        path
        for path in archive_dir.iterdir()
        if path.is_dir() and (path / "index.html").exists() and (path / "gazete.pdf").exists()
    ]
    return sorted(entries, key=lambda path: path.name, reverse=True)


def format_archive_date(value: str) -> str:
    try:
        year, month, day = value.split("-")
        return f"{int(day)} {MONTHS_TR.get(month, month)} {year}"
    except ValueError:
        return value
