from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import sys
from typing import Optional

import typer

import services.news_quality_filters as nqf
from services.gazette_reports import archive_outputs, write_reports
from services.random_news_service import appdata_news_cache_path, copy_gazette_outputs_to_desktop

from .builder import issue_from_rss
from .build_timing import BuildTimer
from .issue import BASE_DIR, normalize_issue, read_json, validate_issue_data, write_json
from .render import render_html, render_pdf
from .sources import enrich_article_details, enrich_issue_images, sanitize_issue_articles
from .technology_page import ensure_technology_third_page


app = typer.Typer(help="Tek komutla 3 sayfalık baskıya hazır gazete üretir.")


def is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker and checker())


def remove_generated_file(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_dir() and not path.is_symlink():
        return False
    try:
        path.unlink()
    except OSError as exc:
        raise RuntimeError(f"[GAZETTE CLEANUP] generated dosya silinemedi: {path}") from exc
    return True


def cleanup_current_build_outputs(
    *,
    dist_dir: Path,
    pdf_path: Path,
    html_path: Path,
    json_path: Path,
) -> dict[str, int]:
    generated_files = [
        pdf_path,
        html_path,
        json_path,
        dist_dir / "build_timing.json",
        dist_dir / "source_report.json",
        dist_dir / "quality_report.json",
        dist_dir / "earthquake_report.json",
        dist_dir / "image_report.json",
        dist_dir / "source_report.html",
    ]
    removed_files = sum(1 for path in generated_files if remove_generated_file(path))

    removed_detail_files = 0
    articles_dir = dist_dir / "articles"
    if articles_dir.exists():
        if articles_dir.is_symlink() or is_junction(articles_dir):
            print(f"[GAZETTE CLEANUP] skipped generated articles link = {articles_dir}")
        elif articles_dir.is_dir():
            for path in articles_dir.iterdir():
                if path.is_file() and path.suffix.lower() == ".html":
                    if remove_generated_file(path):
                        removed_detail_files += 1

    result = {"removed_files": removed_files, "removed_detail_files": removed_detail_files}
    print(
        "[GAZETTE CLEANUP] "
        f"removed_files={result['removed_files']} removed_detail_files={result['removed_detail_files']}"
    )
    return result


def write_random_news_cache(issue_data: dict) -> Path:
    path = appdata_news_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, issue_data)
    return path


def normalize_build_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in {"fast", "full"}:
        raise typer.BadParameter("mode fast veya full olmalı.")
    return mode


def should_enrich_article_details(mode: str) -> bool:
    return mode == "full"


def should_render_portable_html(mode: str, portable_html: bool) -> bool:
    return mode == "full" and portable_html


def should_archive(mode: str) -> bool:
    return mode == "full"


def should_copy_to_desktop(mode: str) -> bool:
    return mode == "full"


@app.callback()
def callback() -> None:
    """Gazet+E komutları."""


def run_build(
    *,
    issue_date: str | None = None,
    paper_size: str = "A3",
    out: Path = Path("dist/gazete.pdf"),
    input_json: Optional[Path] = None,
    live: bool = True,
    portable_html: bool = True,
    mode: str = "fast",
) -> dict[str, object]:
    mode = normalize_build_mode(mode)
    if issue_date is None:
        issue_date = date.today().isoformat()

    paper_size = paper_size.upper()
    if paper_size not in {"A3", "A4"}:
        raise typer.BadParameter("paper-size A3 veya A4 olmalı.")

    dist_dir = out.parent
    html_path = dist_dir / f"{out.stem}.html"
    json_path = dist_dir / "issue.json"
    image_dir = dist_dir / "assets"
    timing_path = dist_dir / "build_timing.json"
    timer = BuildTimer(mode)
    with timer.stage("cleanup"):
        cleanup_current_build_outputs(
            dist_dir=dist_dir,
            pdf_path=out,
            html_path=html_path,
            json_path=json_path,
        )
    print("[GAZETTE DEBUG] cwd =", os.getcwd())
    print("[GAZETTE DEBUG] main file =", __file__)
    print("[GAZETTE DEBUG] sys.path[0] =", sys.path[0])
    print("[GAZETTE DEBUG] news_quality_filters =", nqf.__file__)

    with timer.stage("collect_issue"):
        issue_data = issue_from_rss(issue_date, paper_size, image_dir=image_dir) if live else None
        if issue_data is None:
            source = input_json or BASE_DIR / "data" / "issue.json"
            raw_issue = read_json(source)
            issue_data = normalize_issue(raw_issue, issue_date=issue_date, paper_size=paper_size)
            ensure_technology_third_page(issue_data, raw_issue=raw_issue)
    with timer.stage("sanitize"):
        sanitize_issue_articles(issue_data)
    if should_enrich_article_details(mode):
        with timer.stage("enrich_article_details"):
            enrich_article_details(issue_data)
    else:
        timer.skip("enrich_article_details")
    with timer.stage("enrich_images"):
        enrich_issue_images(issue_data, image_dir)

    with timer.stage("validate"):
        validate_issue_data(issue_data)

    with timer.stage("write_issue_json"):
        write_json(json_path, issue_data)
    with timer.stage("write_random_cache"):
        random_cache_path = write_random_news_cache(issue_data)
    with timer.stage("write_reports"):
        report_paths = write_reports(issue_data, dist_dir)
    with timer.stage("render_pdf_html"):
        render_html(
            issue_data,
            html_path,
            portable_pdf_links=True,
            portable_assets=False,
            include_brief_details=True,
        )
    with timer.stage("render_pdf"):
        render_pdf(html_path, out)
    if should_render_portable_html(mode, portable_html):
        with timer.stage("render_portable_html"):
            render_html(
                issue_data,
                html_path,
                portable_pdf_links=True,
                portable_assets=True,
                include_brief_details=True,
            )
    else:
        timer.skip("render_portable_html")
    if should_archive(mode):
        with timer.stage("archive"):
            archive_path = archive_outputs(
                issue_data,
                {
                    "pdf": out,
                    "html": html_path,
                    "json": json_path,
                    **report_paths,
                },
            )
    else:
        archive_path = None
        timer.skip("archive")
    if should_copy_to_desktop(mode):
        with timer.stage("desktop_copy"):
            desktop_copy_path = copy_gazette_outputs_to_desktop([out, html_path, json_path])
    else:
        desktop_copy_path = None
        timer.skip("desktop_copy")
    timing_data = timer.write(timing_path)
    timer.print_summary(timing_data)

    return {
        "issue_json": json_path,
        "random_cache": random_cache_path,
        "source_report": report_paths["source_report"],
        "archive": archive_path,
        "desktop_copy": desktop_copy_path,
        "timing": timing_path,
        "html": html_path,
        "pdf": out,
        "issue_data": issue_data,
    }


def echo_build_result(result: dict[str, object]) -> None:
    typer.echo(f"OK: issue JSON: {result['issue_json']}")
    typer.echo(f"OK: random news cache: {result['random_cache']}")
    typer.echo(f"OK: source report: {result['source_report']}")
    if result["archive"] is not None:
        typer.echo(f"OK: archive: {result['archive']}")
    if result["desktop_copy"] is not None:
        typer.echo(f"OK: desktop copy: {result['desktop_copy']}")
    typer.echo(f"OK: timing: {result['timing']}")
    typer.echo(f"OK: HTML: {result['html']}")
    typer.echo(f"OK: PDF: {result['pdf']}")


@app.command()
def build(
    issue_date: str | None = typer.Option(None, "--date", help="Baskı tarihi, YYYY-MM-DD."),
    paper_size: str = typer.Option("A3", "--paper-size", help="A3 veya A4."),
    out: Path = typer.Option(Path("dist/gazete.pdf"), "--out", help="Üretilecek PDF yolu."),
    input_json: Optional[Path] = typer.Option(None, "--input-json", help="Var olan issue JSON dosyası."),
    live: bool = typer.Option(True, "--live/--no-live", help="Resmi RSS akışlarını dene; olmazsa yerel veriye düş."),
    portable_html: bool = typer.Option(True, "--portable-html/--linked-html", help="HTML'i tek başına paylaşılabilir üret."),
    mode: str = typer.Option("fast", "--mode", help="Build modu: fast veya full."),
) -> None:
    result = run_build(
        issue_date=issue_date,
        paper_size=paper_size,
        out=out,
        input_json=input_json,
        live=live,
        portable_html=portable_html,
        mode=mode,
    )
    echo_build_result(result)


@app.command("publish-pages")
def publish_pages(
    issue_date: str | None = typer.Option(None, "--date", help="Yayın tarihi, YYYY-MM-DD."),
    live: bool = typer.Option(True, "--live/--no-live", help="Resmi RSS akışlarını dene; olmazsa yerel veriye düş."),
    input_json: Optional[Path] = typer.Option(None, "--input-json", help="Var olan issue JSON dosyası."),
    docs_dir: Path = typer.Option(Path("docs"), "--docs-dir", help="GitHub Pages yayın klasörü."),
) -> None:
    from .pages_publish import publish_pages_site

    result = publish_pages_site(
        docs_dir=docs_dir,
        staging_dir=Path("dist/pages-publish-staging"),
        issue_date=issue_date,
        live=live,
        input_json=input_json,
    )
    typer.echo(f"OK: Pages index: {result['index_html']}")
    typer.echo(f"OK: Pages PDF: {result['pdf']}")
    typer.echo(f"OK: Pages issue JSON: {result['issue_json']}")
    typer.echo(f"OK: Pages archive index: {result['archive_index']}")
    typer.echo(f"OK: Pages archive issue: {result['archive_issue_dir']}")


if __name__ == "__main__":
    app()
