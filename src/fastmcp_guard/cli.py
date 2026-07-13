"""fastmcp-guard CLI — key management, audit tailing, rate limit status."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="fastmcp-guard",
    help="Production operations CLI for fastmcp-guard.",
    no_args_is_help=True,
)
keys_app = typer.Typer(help="API key management.")
audit_app = typer.Typer(help="Audit log operations.")
rate_app = typer.Typer(help="Rate limit status and controls.")

app.add_typer(keys_app, name="keys")
app.add_typer(audit_app, name="audit")
app.add_typer(rate_app, name="rate")

console = Console()


# ---------------------------------------------------------------------------
# Keys
# ---------------------------------------------------------------------------

@keys_app.command("create")
def keys_create(
    name: str = typer.Option(..., "--name", "-n", help="Key label"),
    scopes: str = typer.Option("", "--scopes", "-s", help="Comma-separated scopes"),
    expires_days: int = typer.Option(None, "--expires", help="Expiry in days"),
    db: str = typer.Option("fastmcp-guard-keys.db", "--db", help="SQLite DB path"),
):
    """Create a new API key."""
    from fastmcp_guard.keys.store import KeyStore

    store = KeyStore(backend="sqlite", path=db)
    scope_list = [s.strip() for s in scopes.split(",") if s.strip()]
    key = store.create(name=name, scopes=scope_list, expires_in_days=expires_days)

    console.print("\n[bold green]✓ Key created[/bold green]")
    console.print(f"  ID:     [cyan]{key.id}[/cyan]")
    console.print(f"  Name:   [cyan]{key.name}[/cyan]")
    console.print(f"  Scopes: [cyan]{', '.join(key.scopes) or 'none'}[/cyan]")
    console.print("\n  [bold yellow]Token (shown once — save it now!):[/bold yellow]")
    console.print(f"  [bold]{key.token}[/bold]\n")


@keys_app.command("list")
def keys_list(
    db: str = typer.Option("fastmcp-guard-keys.db", "--db", help="SQLite DB path"),
    all_: bool = typer.Option(False, "--all", help="Include revoked keys"),
):
    """List API keys."""
    from fastmcp_guard.keys.store import KeyStore

    store = KeyStore(backend="sqlite", path=db)
    keys = store.list(include_revoked=all_)

    table = Table(title="API Keys")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Scopes")
    table.add_column("Status")
    table.add_column("Last Used")
    table.add_column("Expires")

    for k in keys:
        status_color = {"active": "green", "rotating": "yellow", "revoked": "red"}.get(
            k.status, "white"
        )
        table.add_row(
            k.id,
            k.name,
            ", ".join(k.scopes) or "—",
            f"[{status_color}]{k.status}[/{status_color}]",
            k.last_used_at.strftime("%Y-%m-%d %H:%M") if k.last_used_at else "never",
            k.expires_at.strftime("%Y-%m-%d") if k.expires_at else "never",
        )

    console.print(table)


@keys_app.command("rotate")
def keys_rotate(
    key_id: str = typer.Argument(..., help="Key ID to rotate"),
    grace_hours: int = typer.Option(24, "--grace", help="Grace period in hours"),
    db: str = typer.Option("fastmcp-guard-keys.db", "--db"),
):
    """Rotate an API key. Old key stays valid for the grace period."""
    from fastmcp_guard.keys.store import KeyStore

    store = KeyStore(backend="sqlite", path=db)
    new_key = store.rotate(key_id, grace_period_hours=grace_hours)

    console.print("\n[bold green]✓ Key rotated[/bold green]")
    console.print(f"  New ID:      [cyan]{new_key.id}[/cyan]")
    console.print(f"  Grace period: {grace_hours}h (old key still valid until then)")
    console.print("\n  [bold yellow]New token (shown once):[/bold yellow]")
    console.print(f"  [bold]{new_key.token}[/bold]\n")


@keys_app.command("revoke")
def keys_revoke(
    key_id: str = typer.Argument(..., help="Key ID to revoke"),
    db: str = typer.Option("fastmcp-guard-keys.db", "--db"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Immediately revoke an API key."""
    from fastmcp_guard.keys.store import KeyStore

    if not force:
        typer.confirm(f"Revoke key {key_id}? This cannot be undone.", abort=True)

    store = KeyStore(backend="sqlite", path=db)
    store.revoke(key_id)
    console.print(f"[bold red]✓ Key {key_id} revoked.[/bold red]")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

@audit_app.command("tail")
def audit_tail(
    db: str = typer.Option("fastmcp-guard-audit.db", "--db"),
    n: int = typer.Option(20, "--lines", "-n", help="Number of recent records to show"),
):
    """Show recent audit log entries."""
    import asyncio

    from fastmcp_guard.audit.backends.sqlite import SQLiteAuditBackend

    backend = SQLiteAuditBackend(path=db)
    records = asyncio.run(backend.query(limit=n))

    table = Table(title="Recent Audit Log")
    table.add_column("Time", style="dim")
    table.add_column("Key")
    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("Duration")

    for r in reversed(records):
        status_color = {"ok": "green", "error": "red", "rate_limited": "yellow",
                        "unauthorized": "red"}.get(r.status, "white")
        table.add_row(
            r.ts[:19],
            r.key_name,
            r.tool,
            f"[{status_color}]{r.status}[/{status_color}]",
            f"{r.duration_ms:.0f}ms",
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Rate
# ---------------------------------------------------------------------------

@rate_app.command("status")
def rate_status():
    """Show global rate limit status."""
    console.print("[dim]Rate limit status requires a running guard instance.[/dim]")
    console.print("Use the Guard.rate_limit.status() method in your server code.")


if __name__ == "__main__":
    app()
