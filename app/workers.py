from __future__ import annotations

import asyncio
import logging

import httpx

from app.db import Database
from app.flags import classify_submit_message
from app.forcead import ForceADClient

logger = logging.getLogger(__name__)


async def submitter_loop(db: Database, client: ForceADClient, batch_size: int, interval: float) -> None:
    while True:
        rows = db.claim_queued_flags(batch_size)
        flags = [str(row["flag"]) for row in rows]
        if not flags:
            await asyncio.sleep(interval)
            continue

        try:
            response = await client.submit_flags(flags)
        except httpx.HTTPStatusError as exc:
            message = f"ForceAD submit HTTP {exc.response.status_code}"
            if exc.response.status_code in {429, 500, 502, 503, 504}:
                db.requeue_flags(flags, message)
            else:
                db.mark_submit_results([(flag, "error", message) for flag in flags])
            db.set_state("last_submit_error", message)
            logger.warning(message)
        except Exception as exc:  # noqa: BLE001 - background task must survive transient failures.
            message = f"ForceAD submit error: {exc}"
            db.requeue_flags(flags, message)
            db.set_state("last_submit_error", message)
            logger.warning(message)
        else:
            results = []
            seen = set()
            for item in response:
                flag = str(item.get("flag", ""))
                msg = str(item.get("msg", ""))
                if not flag:
                    continue
                seen.add(flag)
                results.append((flag, classify_submit_message(msg), msg))
            for flag in flags:
                if flag not in seen:
                    results.append((flag, "error", "No per-flag response from ForceAD"))
            db.mark_submit_results(results)
            db.set_state("last_submit_error", "")

        await asyncio.sleep(interval)


async def poller_loop(db: Database, client: ForceADClient, interval: float) -> None:
    while True:
        try:
            teams = await client.get_teams()
            tasks = await client.get_tasks()
            config = await client.get_config()
            db.upsert_teams(teams)
            db.upsert_tasks(tasks)
            db.set_state("forcead_config", str(config))

            snapshots = []
            for team in teams:
                team_id = int(team.get("id"))
                try:
                    history = await client.get_team_history(team_id)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("failed to poll team %s: %s", team_id, exc)
                    continue
                snapshots.extend(history)
            db.insert_snapshots(snapshots)
            db.set_state("last_poll_error", "")
        except Exception as exc:  # noqa: BLE001 - background task must keep trying.
            message = f"ForceAD poll error: {exc}"
            db.set_state("last_poll_error", message)
            logger.warning(message)

        await asyncio.sleep(interval)
