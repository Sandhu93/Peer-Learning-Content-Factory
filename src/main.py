"""
CLI entry point for the Peer Learning Content Factory.

Usage:
    # Single concept — repo from .env
    python -m src.main --concept "Circuit breaker for provider failure"

    # Single concept — repo passed explicitly (overrides .env)
    python -m src.main --concept "Circuit breaker" --repo D:/path/to/your-repo

    # Process all concepts in batch
    python -m src.main --batch --repo D:/path/to/your-repo

    # Process a specific category
    python -m src.main --category "Reliability, Failure Isolation, and Production Hardening"

    # Dry run — list what would be processed
    python -m src.main --batch --dry-run

    # Show all concepts in the backlog
    python -m src.main --list

Repo path resolution (priority order):
    1. --repo flag on the command line
    2. REPO_PATH in .env
    Fails with a clear message if neither is provided.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

console = Console()


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _resolve_repo(repo_override: str | None) -> Path:
    """
    Resolve the repo path for this run.

    Checks (in order): --repo CLI arg → REPO_PATH in .env.
    Raises SystemExit with a clear message if neither is set or path is invalid.
    """
    from src.config import settings
    try:
        return settings.effective_repo_path(repo_override)
    except ValueError as exc:
        console.print(f"\n[red]Error:[/] {exc}\n")
        sys.exit(1)


async def run_single_concept(
    concept_name: str,
    repo_path: Path,
    output_dir: Path | None = None,
) -> dict:
    """Run the full pipeline for a single concept. Returns the final state."""
    from src.config import settings
    from src.graph import build_graph
    from src.utils.markdown_parser import find_concept

    concept = find_concept(concept_name)
    if concept is None:
        console.print(f"[red]Concept not found:[/] {concept_name!r}")
        console.print("Use [bold]--list[/] to see all available concepts.")
        sys.exit(1)

    console.print(Panel(
        f"[bold]{concept.concept_name}[/]\n"
        f"[dim]{concept.category}[/]\n\n"
        f"{concept.why_it_matters}\n\n"
        f"[dim]Repo:[/] {repo_path}",
        title="Processing concept",
        border_style="blue",
    ))

    graph = build_graph()

    initial_state = {
        "concept_name": concept.concept_name,
        "category": concept.category,
        "why_it_matters": concept.why_it_matters,
        "repo_anchors": concept.repo_anchors,
        "repo_path": str(repo_path),   # travels with the run; agents read from here
        "revision_count": 0,
        "is_complete": False,
        "errors": [],
    }

    final_state = await graph.ainvoke(initial_state)

    # ── Save outputs ───────────────────────────────────────────────────────────
    out_root = output_dir or (settings.output_path / concept.slug())
    out_root.mkdir(parents=True, exist_ok=True)

    # Fact sheet — research evidence (always written)
    fact_sheet_path = out_root / "fact_sheet.json"
    fact_sheet = {
        "concept_name": final_state.get("concept_name"),
        "category": final_state.get("category"),
        "why_it_matters": final_state.get("why_it_matters"),
        "repo_path": final_state.get("repo_path"),
        "teaching_plan": final_state.get("teaching_plan", {}),
        "code_evidence": final_state.get("code_evidence", []),
        "implementation_notes": final_state.get("implementation_notes", {}),
        "doc_context": final_state.get("doc_context", {}),
        "generalized_pattern": final_state.get("generalized_pattern", {}),
    }
    fact_sheet_path.write_text(json.dumps(fact_sheet, indent=2, ensure_ascii=False))

    # guide.html — Phase 2 deliverable (written if writer produced output)
    guide_html = final_state.get("guide_html", "")
    guide_path = None
    if guide_html:
        guide_path = out_root / "guide.html"
        guide_path.write_text(guide_html, encoding="utf-8")

    # linkedin.md and reel_script.md — written if produced
    linkedin_post = final_state.get("linkedin_post", "")
    if linkedin_post:
        (out_root / "linkedin.md").write_text(linkedin_post, encoding="utf-8")

    reel_script = final_state.get("reel_script", "")
    if reel_script:
        (out_root / "reel_script.md").write_text(reel_script, encoding="utf-8")

    # ── Console summary ────────────────────────────────────────────────────────
    console.print(f"\n[green]✓[/] Fact sheet → [bold]{fact_sheet_path}[/]")
    console.print(f"  Code evidence: {len(fact_sheet['code_evidence'])} snippets")
    if guide_path:
        console.print(f"[green]✓[/] Guide       → [bold]{guide_path}[/]")
    if linkedin_post:
        console.print(f"[green]✓[/] LinkedIn    → [bold]{out_root / 'linkedin.md'}[/]")
    if reel_script:
        console.print(f"[green]✓[/] Reel script → [bold]{out_root / 'reel_script.md'}[/]")

    return final_state


async def run_batch(
    repo_path: Path,
    category: str | None = None,
    dry_run: bool = False,
    resume: bool = False,
) -> None:
    """Process multiple concepts from the backlog."""
    from src.config import settings
    from src.utils.markdown_parser import parse_concepts

    concepts = parse_concepts()
    if category:
        concepts = [c for c in concepts if category.lower() in c.category.lower()]

    if not concepts:
        console.print("[yellow]No concepts matched the filter.[/]")
        return

    console.print(f"\n[bold]Found {len(concepts)} concepts to process[/]")
    console.print(f"[dim]Repo: {repo_path}[/]\n")

    table = Table(title="Concept Backlog", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Concept", style="bold")
    table.add_column("Category", style="dim")
    table.add_column("Status", justify="center")

    for i, c in enumerate(concepts, 1):
        out_path = settings.output_path / c.slug() / "fact_sheet.json"
        status = "[green]done[/]" if out_path.exists() else "[dim]pending[/]"
        if resume and out_path.exists():
            status = "[blue]skip[/]"
        table.add_row(str(i), c.concept_name, c.category[:40], status)

    console.print(table)

    if dry_run:
        console.print("\n[dim]Dry run — no API calls made.[/]")
        return

    for concept in concepts:
        if resume:
            out_path = settings.output_path / concept.slug() / "fact_sheet.json"
            if out_path.exists():
                console.print(f"[dim]Skipping (already done):[/] {concept.concept_name}")
                continue
        try:
            await run_single_concept(concept.concept_name, repo_path)
        except Exception as exc:
            console.print(f"[red]Error processing {concept.concept_name!r}:[/] {exc}")
            logging.exception("Batch processing error")


def list_concepts() -> None:
    """Print all concepts in the backlog."""
    from src.utils.markdown_parser import parse_concepts

    concepts = parse_concepts()
    table = Table(title=f"Concept Backlog ({len(concepts)} concepts)", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Concept", style="bold")
    table.add_column("Category", style="dim")
    table.add_column("Difficulty", justify="center")

    for i, c in enumerate(concepts, 1):
        table.add_row(str(i), c.concept_name, c.category[:45], "—")

    console.print(table)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="peer-factory",
        description="Peer Learning Content Factory — generate teaching guides from a codebase",
    )
    p.add_argument("--concept", "-c", metavar="NAME", help="Process a single concept by name")
    p.add_argument("--batch", "-b", action="store_true", help="Process all concepts")
    p.add_argument("--category", metavar="CAT", help="Filter batch to a specific category")
    p.add_argument(
        "--repo", "-r", metavar="PATH",
        help="Path to the repo to analyse (overrides REPO_PATH in .env)",
    )
    p.add_argument("--dry-run", action="store_true", help="List what would be processed, no API calls")
    p.add_argument("--resume", action="store_true", help="Skip concepts with existing outputs")
    p.add_argument("--list", "-l", action="store_true", help="List all concepts in the backlog")
    p.add_argument("--output", "-o", metavar="PATH", help="Output directory for single concept")
    p.add_argument("--log-level", default="INFO", help="Logging level (default: INFO)")
    return p


def cli() -> None:
    """Entry point called by the peer-factory script and by python -m src.main."""
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.log_level)

    if args.list:
        list_concepts()
        return

    # Resolve the repo path once — used by all run paths below
    # (--list doesn't need a repo, so we resolve after that check)
    repo_path = _resolve_repo(args.repo)

    if args.concept:
        output = Path(args.output) if args.output else None
        asyncio.run(run_single_concept(args.concept, repo_path, output))
        return

    if args.batch:
        asyncio.run(run_batch(
            repo_path=repo_path,
            category=args.category,
            dry_run=args.dry_run,
            resume=args.resume,
        ))
        return

    parser.print_help()


if __name__ == "__main__":
    cli()
