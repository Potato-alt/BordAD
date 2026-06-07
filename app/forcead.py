from __future__ import annotations

from typing import Any

import httpx


class ForceADClient:
    def __init__(self, base_url: str, team_token: str, timeout: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.team_token = team_token
        self.timeout = timeout

    async def get_json(self, path: str) -> Any:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(f"{self.base_url}{path}")
            response.raise_for_status()
            return response.json()

    async def get_teams(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/client/teams/")

    async def get_tasks(self) -> list[dict[str, Any]]:
        return await self.get_json("/api/client/tasks/")

    async def get_config(self) -> dict[str, Any]:
        return await self.get_json("/api/client/config/")

    async def get_team_history(self, team_id: int) -> list[dict[str, Any]]:
        return await self.get_json(f"/api/client/teams/{team_id}/")

    async def get_ctftime(self) -> dict[str, Any]:
        return await self.get_json("/api/client/ctftime/")

    async def get_attack_data(self) -> Any:
        return await self.get_json("/api/client/attack_data/")

    async def submit_flags(self, flags: list[str]) -> list[dict[str, Any]]:
        headers = {"X-Team-Token": self.team_token}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.put(f"{self.base_url}/flags", headers=headers, json=flags)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, list):
                raise ValueError("ForceAD returned non-list submit response")
            return data
