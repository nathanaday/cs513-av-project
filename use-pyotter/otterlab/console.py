"""What the lab prints: one console, and errors that say how to fix them."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

console = Console(highlight=False)

OK = "[green]✓[/green]"
FAIL = "[red]✗[/red]"
NOTE = "[yellow]![/yellow]"


class LabError(Exception):
    """A problem the user can act on.

    Attributes:
        hint: What to do about it, often a command to run.
    """

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


def show_error(error: LabError) -> None:
    console.print(f"{FAIL} {error}")
    if error.hint:
        console.print(f"  [dim]{error.hint}[/dim]")


def table(*columns: str) -> Table:
    grid = Table(box=None, pad_edge=False, padding=(0, 3, 0, 0), header_style="dim")
    for column in columns:
        grid.add_column(column)
    return grid


def next_steps(steps: list[tuple[str, str]]) -> None:
    """Print labelled commands, aligned, under a blank line."""
    width = max(len(label) for label, _ in steps)
    console.print()
    for label, command in steps:
        console.print(f"  [dim]{label:<{width}}[/dim]  {command}")


def size_text(size: int) -> str:
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f} MB"
    return f"{size / 1000:.0f} KB"
