#!/usr/bin/env python3
"""`make demo` — the whole thesis in one command.

Runs the same recon cycle against the same authorised sandbox twice.

Pass 1 has no memory to draw on, so everything it finds is new.
Pass 2 sees one genuinely new asset and an otherwise unchanged estate. A memoryless
agent would re-report all of it. MNEMOS recalls the first pass out of CockroachDB,
dedups against it, and writes only what actually changed.

Everything printed here is read back out of CockroachDB after the fact — none of it
is accumulated in process memory, because the point is that the database is the
agent's memory.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import textwrap

from mnemos_memory import Memory, migrate
from mnemos_memory.embeddings import get_embedder
from mnemos_recon import ensure_target, get_analyst, run_cycle

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
CYAN, AMBER, GREEN, RED = "\033[36m", "\033[33m", "\033[32m", "\033[31m"


def rule(title: str = "") -> None:
    if title:
        print(f"\n{CYAN}{BOLD}━━ {title} {'━' * max(0, 66 - len(title))}{RESET}")
    else:
        print(f"{DIM}{'─' * 72}{RESET}")


def main() -> int:
    ap = argparse.ArgumentParser(description="MNEMOS end-to-end demo")
    ap.add_argument("--reset", action="store_true",
                    help="drop and recreate the mnemos database first")
    ap.add_argument("--ceiling", type=float, default=5.0, help="per-run cost ceiling in USD")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    rule("0 · memory layer")
    if args.reset:
        import psycopg

        dsn = os.getenv("DATABASE_URL", "postgresql://root@localhost:26257/mnemos?sslmode=disable")
        with psycopg.connect(dsn.replace("/mnemos?", "/defaultdb?"), autocommit=True) as c:
            c.execute("DROP DATABASE IF EXISTS mnemos CASCADE")
        print(f"  {DIM}dropped existing database{RESET}")
    applied = migrate(verbose=False)
    print(f"  migrations applied : {', '.join(applied)}")

    embedder, analyst = get_embedder(), get_analyst()
    print(f"  embedder           : {embedder.model_id}")
    print(f"  analyst            : {analyst.model_id}")
    if embedder.model_id.startswith("offline"):
        print(f"  {AMBER}note{RESET} running with offline stand-ins for embed/reason.")
        print(f"       {DIM}Bedrock was probed and is not invokable on this account "
              f"(on-demand quota).{RESET}")
        print(f"       {DIM}Artifact storage below is real Amazon S3 regardless.{RESET}")

    with Memory(embedder=embedder) as mem:
        target_id = ensure_target(mem)
        print(f"  target             : {target_id}")

        rule("1 · first visit — nothing remembered yet")
        first = run_cycle(mem, target_id, 1, analyst=analyst, ceiling_usd=args.ceiling)
        report(first)

        rule("2 · second visit — same estate, one new bundle")
        second = run_cycle(mem, target_id, 2, analyst=analyst, ceiling_usd=args.ceiling)
        report(second)

        rule("what CockroachDB actually holds")
        for table, count in mem.stats().items():
            print(f"  {table:<16} {count:>6}")

        rule("artifacts — bytes in S3, addresses in CockroachDB")
        print(f"  store: {mem.artifacts.backend}")
        with mem.conn.cursor() as cur:
            cur.execute(
                "SELECT sha256, s3_bucket, s3_key, byte_len FROM artifacts ORDER BY byte_len DESC"
            )
            for row in cur.fetchall():
                where = f"s3://{row['s3_bucket']}/" if row["s3_bucket"] else f"{DIM}(not uploaded){RESET} "
                print(f"  {row['sha256'][:12]}…  {row['byte_len']:>5}B  {where}{row['s3_key']}")

        rule("recall, straight out of the vector index")
        for item in mem.recall(target_id, "leaked API key in a javascript bundle", k=4):
            print(f"  {DIM}d={item.distance:.3f}{RESET} [{item.kind:^9}] "
                  f"{item.content[:88].strip()}")

        rule("audit trail — the last 8 decisions")
        for row in mem.audit_tail(limit=8):
            colour = RED if row["decision"] == "deny" else GREEN
            print(f"  {row['at']:%H:%M:%S}  {row['actor']:<9} {row['action']:<12} "
                  f"{colour}{row['decision']:<6}{RESET} {str(row['resource'] or '')[:44]}")

        rule("the point")
        blocked = second.deduped
        print(textwrap.dedent(f"""
            Pass 1 wrote {first.written} findings from {first.observations} observations.
            Pass 2 saw {second.observations} observations and wrote {BOLD}{second.written}{RESET}.

            {BOLD}{blocked} duplicate findings never reached the findings table.{RESET}
            They were stopped by a vector-similarity check against what pass 1 had
            already written — recall from CockroachDB, not state held in this process.

            New in pass 2:
        """).strip())
        for title in second.new_titles:
            print(f"    {GREEN}+{RESET} {title}")
        if not second.new_titles:
            print(f"    {DIM}(nothing new — the estate did not change){RESET}")
        print()

    return 0


def report(result) -> None:
    status = f"{RED}HALTED{RESET}" if result.halted else f"{GREEN}complete{RESET}"
    print(f"  run {result.run_id[:8]}…  {status}")
    print(f"    observations : {result.observations}")
    print(f"    recalled     : {result.recalled}   {DIM}(prior context pulled from memory){RESET}")
    print(f"    written      : {BOLD}{result.written}{RESET}")
    print(f"    deduped      : {AMBER}{result.deduped}{RESET}  {DIM}(blocked before write){RESET}")
    print(f"    scope denied : {result.denied}")
    print(f"    cost         : ${result.cost_usd:.4f}")
    if result.halted:
        print(f"    {RED}{result.halt_reason}{RESET}")


if __name__ == "__main__":
    sys.exit(main())
