#!/usr/bin/env python3
"""Track Google Scholar citation metrics over time.

Usage examples:
  python scholar_tracker.py fetch --author-id YOUR_AUTHOR_ID
  python scholar_tracker.py plot-total
  python scholar_tracker.py plot-publications --top 10
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import matplotlib.pyplot as plt
from scholarly import scholarly

DB_PATH = Path("scholar_history.db")


@dataclass
class PublicationSnapshot:
    title: str
    citation_count: int


@dataclass
class AuthorSnapshot:
    author_id: str
    author_name: str
    total_citations: int
    hindex: int
    i10index: int
    captured_at: datetime
    publications: list[PublicationSnapshot]


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author_id TEXT NOT NULL,
            author_name TEXT,
            captured_at TEXT NOT NULL,
            total_citations INTEGER NOT NULL,
            hindex INTEGER,
            i10index INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS publication_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            citation_count INTEGER NOT NULL,
            FOREIGN KEY(snapshot_id) REFERENCES snapshots(id)
        )
        """
    )
    conn.commit()


def fetch_author_snapshot(author_id: str) -> AuthorSnapshot:
    author = scholarly.search_author_id(author_id)
    author = scholarly.fill(author, sections=["basics", "indices", "counts", "publications"])

    publications: list[PublicationSnapshot] = []
    for pub in author.get("publications", []):
        filled_pub = scholarly.fill(pub)
        bib = filled_pub.get("bib", {})
        title = (bib.get("title") or "Untitled").strip()
        citations = int(filled_pub.get("num_citations", 0) or 0)
        publications.append(PublicationSnapshot(title=title, citation_count=citations))

    return AuthorSnapshot(
        author_id=author_id,
        author_name=author.get("name", "Unknown"),
        total_citations=int(author.get("citedby", 0) or 0),
        hindex=int(author.get("hindex", 0) or 0),
        i10index=int(author.get("i10index", 0) or 0),
        captured_at=datetime.now(timezone.utc),
        publications=publications,
    )


def save_snapshot(conn: sqlite3.Connection, snapshot: AuthorSnapshot) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO snapshots (author_id, author_name, captured_at, total_citations, hindex, i10index)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot.author_id,
            snapshot.author_name,
            snapshot.captured_at.isoformat(),
            snapshot.total_citations,
            snapshot.hindex,
            snapshot.i10index,
        ),
    )
    snapshot_id = int(cur.lastrowid)
    cur.executemany(
        """
        INSERT INTO publication_snapshots (snapshot_id, title, citation_count)
        VALUES (?, ?, ?)
        """,
        [(snapshot_id, p.title, p.citation_count) for p in snapshot.publications],
    )
    conn.commit()
    return snapshot_id


def fetch_command(args: argparse.Namespace) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        ensure_schema(conn)
        snapshot = fetch_author_snapshot(args.author_id)
        snapshot_id = save_snapshot(conn, snapshot)
        print(
            json.dumps(
                {
                    "snapshot_id": snapshot_id,
                    "author": snapshot.author_name,
                    "captured_at": snapshot.captured_at.isoformat(),
                    "total_citations": snapshot.total_citations,
                    "publication_count": len(snapshot.publications),
                },
                indent=2,
            )
        )


def load_total_history(conn: sqlite3.Connection) -> Iterable[tuple[datetime, int]]:
    rows = conn.execute(
        """
        SELECT captured_at, total_citations
        FROM snapshots
        ORDER BY datetime(captured_at)
        """
    ).fetchall()
    for captured_at, total_citations in rows:
        yield datetime.fromisoformat(captured_at), int(total_citations)


def plot_total_command(args: argparse.Namespace) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        ensure_schema(conn)
        points = list(load_total_history(conn))

    if not points:
        raise SystemExit("No snapshots found. Run `fetch` first.")

    dates = [p[0] for p in points]
    totals = [p[1] for p in points]

    plt.figure(figsize=(10, 5))
    plt.plot(dates, totals, marker="o")
    plt.title("Total Google Scholar Citations Over Time")
    plt.xlabel("Date")
    plt.ylabel("Total citations")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    output = Path(args.output)
    plt.savefig(output, dpi=160)
    print(f"Saved: {output}")


def load_publication_history(
    conn: sqlite3.Connection, top: Optional[int]
) -> tuple[list[datetime], dict[str, list[int]]]:
    snapshots = conn.execute(
        """
        SELECT id, captured_at
        FROM snapshots
        ORDER BY datetime(captured_at)
        """
    ).fetchall()
    if not snapshots:
        return [], {}

    top_titles = None
    if top:
        top_titles = {
            row[0]
            for row in conn.execute(
                """
                SELECT title
                FROM publication_snapshots
                GROUP BY title
                ORDER BY MAX(citation_count) DESC
                LIMIT ?
                """,
                (top,),
            ).fetchall()
        }

    timeline = [datetime.fromisoformat(row[1]) for row in snapshots]
    series: dict[str, list[int]] = {}

    for snap_idx, (snapshot_id, _) in enumerate(snapshots):
        pubs = conn.execute(
            """
            SELECT title, citation_count
            FROM publication_snapshots
            WHERE snapshot_id = ?
            """,
            (snapshot_id,),
        ).fetchall()

        for title, _ in pubs:
            if top_titles and title not in top_titles:
                continue
            series.setdefault(title, [0] * len(snapshots))

        for title, citation_count in pubs:
            if title in series:
                series[title][snap_idx] = int(citation_count)

    return timeline, series


def plot_publications_command(args: argparse.Namespace) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        ensure_schema(conn)
        timeline, series = load_publication_history(conn, args.top)

    if not timeline or not series:
        raise SystemExit("No publication data found. Run `fetch` first.")

    plt.figure(figsize=(12, 7))
    for title, values in series.items():
        plt.plot(timeline, values, marker="o", linewidth=1.5, label=title)

    plt.title("Citation Trend Per Publication")
    plt.xlabel("Date")
    plt.ylabel("Citations")
    plt.grid(True, alpha=0.3)
    if len(series) <= 12:
        plt.legend(fontsize=8)
    plt.tight_layout()
    output = Path(args.output)
    plt.savefig(output, dpi=160)
    print(f"Saved: {output}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track Google Scholar citations daily.")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Fetch and save a new snapshot")
    fetch.add_argument("--author-id", required=True, help="Google Scholar author ID")
    fetch.set_defaults(func=fetch_command)

    total = sub.add_parser("plot-total", help="Plot total citations over time")
    total.add_argument("--output", default="total_citations.png", help="Output PNG file")
    total.set_defaults(func=plot_total_command)

    pubs = sub.add_parser("plot-publications", help="Plot citations per publication")
    pubs.add_argument("--top", type=int, default=10, help="Top N publications by max citations")
    pubs.add_argument("--output", default="publication_citations.png", help="Output PNG file")
    pubs.set_defaults(func=plot_publications_command)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
