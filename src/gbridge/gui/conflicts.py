"""Tkinter dialog for resolving Outlook ↔ Google conflicts.

Shown from the tray ("Resolve conflicts (N)") or launched directly via
``gbridge conflicts list`` + a future ``--gui`` flag. Lists every
unresolved conflict, lets the user pick a winner per item, and commits
the choice to the ledger's `conflicts` table.

Tk is imported lazily so importing this module is safe on headless CI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gbridge.core import conflicts as conflicts_module
from gbridge.core.ledger import SyncLedger

if TYPE_CHECKING:
    from gbridge.config.settings import Settings

logger = logging.getLogger(__name__)


def run_conflicts_dialog(settings: Settings) -> int:
    """Open the Tk dialog.  Returns 0 on success, 1 on failure."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        logger.error("Tkinter not available — cannot open conflicts dialog")
        return 1

    ledger = SyncLedger(settings.db_path)
    try:
        pending = conflicts_module.list_conflicts(ledger, unresolved_only=True)
    finally:
        ledger.close()

    root = tk.Tk()
    root.title("GBridge — pending conflicts")
    root.geometry("720x440")

    header = tk.Label(
        root,
        text=(
            "These items were modified BOTH in Google and in Outlook since the "
            "last push.\nPick a winner — the losing side will be overwritten "
            "on the next push."
        ),
        justify="left",
        anchor="w",
        pady=6,
    )
    header.pack(fill="x", padx=10)

    if not pending:
        tk.Label(root, text="(no pending conflicts)").pack(padx=10, pady=30)
        tk.Button(root, text="Close", command=root.destroy).pack(pady=5)
        root.mainloop()
        return 0

    # Scrollable frame for conflict rows.
    canvas = tk.Canvas(root, highlightthickness=0)
    scroll = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
    body = ttk.Frame(canvas)
    body.bind(
        "<Configure>",
        lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=body, anchor="nw")
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=6)
    scroll.pack(side="right", fill="y", pady=6)

    winners: dict[int, tk.StringVar] = {}
    for row in pending:
        frame = ttk.Frame(body, padding=(0, 6))
        frame.pack(fill="x", padx=4, pady=2)
        label = (
            f"#{row.id}  {row.item_type}  {row.google_id}\n"
            f"  detected {row.detected_at}"
        )
        tk.Label(frame, text=label, justify="left", anchor="w",
                 font=("TkFixedFont",)).pack(fill="x")
        var = tk.StringVar(value="")
        winners[row.id] = var
        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w")
        ttk.Radiobutton(buttons, text="Google wins", variable=var,
                        value="google").pack(side="left")
        ttk.Radiobutton(buttons, text="Outlook wins", variable=var,
                        value="outlook").pack(side="left")

    def _apply() -> None:
        resolved = 0
        ledger2 = SyncLedger(settings.db_path)
        try:
            for cid, var in winners.items():
                choice = var.get()
                if not choice:
                    continue
                if conflicts_module.resolve_conflict(ledger2, cid, choice):  # type: ignore[arg-type]
                    resolved += 1
        finally:
            ledger2.close()
        messagebox_info(root, f"Resolved {resolved} conflict(s).")
        root.destroy()

    ttk.Button(root, text="Apply selected", command=_apply).pack(pady=4)
    ttk.Button(root, text="Cancel", command=root.destroy).pack(pady=2)

    root.mainloop()
    return 0


def messagebox_info(parent: object, msg: str) -> None:
    try:
        from tkinter import messagebox
    except ImportError:
        return
    messagebox.showinfo("GBridge", msg, parent=parent)  # type: ignore[arg-type]
