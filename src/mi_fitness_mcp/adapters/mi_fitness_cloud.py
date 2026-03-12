import asyncio
import base64
import hashlib
import json
import os
import struct
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from mi_fitness_mcp.adapters.base import DataAdapter
from mi_fitness_mcp.models import (
    BodyMeasurement,
    DailyActivity,
    HeartRateSample,
    SleepSession,
    Workout,
)

LOGIN_PREFIX = b"&&&START&&&"
KNOWN_REGIONS = ["ru", "cn", "de", "i2", "sg", "us"]


def _read_login_payload(text: str) -> dict:
    payload = text.encode()
    if not payload.startswith(LOGIN_PREFIX):
        raise RuntimeError("unexpected Xiaomi login response")
    return json.loads(payload[len(LOGIN_PREFIX) :].decode())


def _rc4_crypt(key: bytes, payload: bytes) -> bytes:
    s = list(range(256))
    j = 0
    key_len = len(key)
    for i in range(256):
        j = (j + s[i] + key[i % key_len]) % 256
        s[i], s[j] = s[j], s[i]
    i = 0
    j = 0

    def next_byte() -> int:
        nonlocal i, j
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        return s[(s[i] + s[j]) % 256]

    for _ in range(1024):
        next_byte()

    output = bytearray()
    for value in payload:
        output.append(value ^ next_byte())
    return bytes(output)


def _gen_nonce() -> bytes:
    raw = bytearray(os.urandom(8))
    raw.extend(struct.pack(">I", int(datetime.now().timestamp() // 60)))
    return bytes(raw)


def _gen_signed_nonce(ssecurity: bytes, nonce: bytes) -> bytes:
    return hashlib.sha256(ssecurity + nonce).digest()


def _gen_signature(method: str, path: str, values: dict[str, str], signed_nonce: bytes) -> str:
    base = method + "&" + path + "&data=" + values["data"]
    if "rc4_hash__" in values:
        base += "&rc4_hash__=" + values["rc4_hash__"]
    base += "&" + base64.b64encode(signed_nonce).decode()
    return base64.b64encode(hashlib.sha1(base.encode()).digest()).decode()


class MiFitnessCloudAdapter(DataAdapter):
    def __init__(
        self, user_id: str | None = None, pass_token: str | None = None, region: str = "ru"
    ):
        self.user_id = user_id
        self.pass_token = pass_token
        self.region = region
        self._cookies = ""
        self._ssecurity = b""
        self._client: httpx.AsyncClient | None = None
        self._connected = False
        self._available_types: list[str] = []

    async def connect(self) -> bool:
        if not self.user_id or not self.pass_token:
            return False

        self._client = httpx.AsyncClient(timeout=30.0, follow_redirects=False)

        try:
            await self._login_with_token(self.user_id, self.pass_token)
            self.region = await self._discover_region(self.region)
            self._available_types = await self._discover_data_types()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            return False

    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    def get_user_id(self) -> str | None:
        return self.user_id

    def get_available_data_types(self) -> list[str]:
        return self._available_types.copy()

    async def _close_client(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _login_with_token(self, user_id: str, pass_token: str) -> None:
        if not self._client:
            raise RuntimeError("client not initialized")

        response = await self._client.get(
            "https://account.xiaomi.com/pass/serviceLogin?_json=true&sid=miothealth",
            headers={"Cookie": f"userId={user_id}; passToken={pass_token}"},
        )
        response.raise_for_status()
        payload = _read_login_payload(response.text)
        self.pass_token = payload["passToken"]
        self.user_id = str(payload["userId"])
        self._ssecurity = base64.b64decode(payload["ssecurity"])

        redirect = await self._client.get(payload["location"])
        redirect.raise_for_status()
        cookie_parts = [value.split(";", 1)[0] for value in redirect.headers.get_list("set-cookie")]
        self._cookies = "; ".join(cookie_parts)

    async def _request(self, base_url: str, api_path: str, payload: dict) -> dict:
        if not self._client:
            raise RuntimeError("client not initialized")

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                form = {"data": json.dumps(payload, separators=(",", ":"))}
                nonce = _gen_nonce()
                signed_nonce = _gen_signed_nonce(self._ssecurity, nonce)
                form["rc4_hash__"] = _gen_signature("POST", api_path, form, signed_nonce)

                encrypted: dict[str, str] = {}
                for key, value in form.items():
                    encrypted[key] = base64.b64encode(
                        _rc4_crypt(signed_nonce, value.encode())
                    ).decode()

                encrypted["signature"] = _gen_signature("POST", api_path, encrypted, signed_nonce)
                encrypted["_nonce"] = base64.b64encode(nonce).decode()

                response = await self._client.post(
                    base_url + api_path,
                    headers={
                        "Cookie": self._cookies,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    content=urlencode(encrypted),
                )
                response.raise_for_status()
                plaintext = _rc4_crypt(signed_nonce, base64.b64decode(response.text))
                body = json.loads(plaintext)
                if body.get("code") != 0:
                    raise RuntimeError(body.get("message", "unknown mi fitness error"))
                return body.get("result", {})
            except Exception as exc:
                last_error = exc
                if attempt == 2:
                    break
                await asyncio.sleep(0.5 * (attempt + 1))
        raise RuntimeError(f"Mi Fitness request failed: {last_error}")

    async def _fetch_key(
        self, key: str, start_date: str, end_date: str, region: str | None = None
    ) -> list[dict]:
        region_name = region or self.region
        base_url = (
            "https://hlth.io.mi.com"
            if region_name in ("", "cn")
            else f"https://{region_name}.hlth.io.mi.com"
        )
        start_time = int(datetime.fromisoformat(start_date).replace(tzinfo=UTC).timestamp())
        end_time = int(
            datetime.fromisoformat(end_date + "T23:59:59").replace(tzinfo=UTC).timestamp()
        )
        next_key = None
        items: list[dict] = []

        while True:
            payload = {
                "start_time": start_time,
                "end_time": end_time,
                "key": key,
            }
            if next_key:
                payload["next_key"] = next_key

            result = await self._request(base_url, "/app/v1/data/get_fitness_data_by_time", payload)
            items.extend(result.get("data_list", []))
            if not result.get("has_more") or not result.get("next_key"):
                break
            next_key = result.get("next_key")

        return items

    async def _discover_region(self, preferred_region: str) -> str:
        candidates = [preferred_region] + [
            region for region in KNOWN_REGIONS if region != preferred_region
        ]
        for region in candidates:
            for key in ("weight", "steps", "heart_rate"):
                try:
                    result = await self._fetch_key(key, "2025-04-01", "2025-05-31", region=region)
                    if result:
                        return region
                except Exception:
                    continue
        return preferred_region

    async def _discover_data_types(self) -> list[str]:
        types: list[str] = []
        probes = {
            "daily_activity": "steps",
            "heart_rate": "heart_rate",
            "body_measurements": "weight",
        }
        for data_type, key in probes.items():
            try:
                items = await self._fetch_key(key, "2025-04-01", "2025-05-31")
                if items:
                    types.append(data_type)
            except Exception:
                continue
        return types

    def _record_datetime(self, item: dict) -> datetime:
        timestamp = int(item.get("time", 0))
        zone_offset = int(item.get("zone_offset", 0))
        return datetime.fromtimestamp(timestamp + zone_offset, tz=UTC).replace(tzinfo=None)

    def _parse_value(self, item: dict) -> dict[str, Any]:
        raw = item.get("value", "{}")
        if isinstance(raw, dict):
            return raw
        return json.loads(raw)

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        parsed = float(value)
        return None if parsed == 0 else parsed

    def _optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        parsed = int(float(value))
        return None if parsed == 0 else parsed

    async def iter_daily_activity(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> AsyncIterator[DailyActivity]:
        if not self.is_connected() or not start_date or not end_date:
            return
            yield

        records = await self._fetch_key("steps", start_date, end_date)
        daily: dict[str, dict[str, float]] = defaultdict(
            lambda: {"steps": 0, "distance_m": 0.0, "active_kcal": 0.0}
        )
        for item in records:
            payload = self._parse_value(item)
            date_str = self._record_datetime(item).strftime("%Y-%m-%d")
            daily[date_str]["steps"] += int(payload.get("steps", 0))
            daily[date_str]["distance_m"] += float(payload.get("distance", 0))
            daily[date_str]["active_kcal"] += float(payload.get("calories", 0))

        calorie_records = await self._fetch_key("calories", start_date, end_date)
        calorie_totals: dict[str, float] = defaultdict(float)
        for item in calorie_records:
            payload = self._parse_value(item)
            date_str = self._record_datetime(item).strftime("%Y-%m-%d")
            calorie_totals[date_str] += float(payload.get("calories", 0))

        for date_str, total in calorie_totals.items():
            daily[date_str]["active_kcal"] = total

        for date_str, values in sorted(daily.items()):
            yield DailyActivity(
                id=f"mi_fitness_activity_{date_str}",
                provider="mi_fitness",
                source_type="cloud_session",
                user_id=self.user_id or "unknown",
                date=date_str,
                steps=int(values["steps"]),
                distance_m=values["distance_m"],
                active_kcal=values["active_kcal"],
            )

    async def iter_sleep_sessions(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> AsyncIterator[SleepSession]:
        if False:
            yield

    async def iter_workouts(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> AsyncIterator[Workout]:
        if False:
            yield

    async def iter_body_measurements(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> AsyncIterator[BodyMeasurement]:
        if not self.is_connected() or not start_date or not end_date:
            return
            yield

        records = await self._fetch_key("weight", start_date, end_date)
        for item in records:
            payload = self._parse_value(item)
            measured_at = self._record_datetime(item)
            yield BodyMeasurement(
                id=f"mi_fitness_weight_{int(item.get('time', 0))}",
                provider="mi_fitness",
                source_type="cloud_session",
                user_id=self.user_id or "unknown",
                timestamp=measured_at,
                weight_kg=float(payload.get("weight", 0)),
                bmi=float(payload["bmi"]) if payload.get("bmi") is not None else None,
                body_fat_pct=self._optional_float(payload.get("body_fat_rate")),
                muscle_mass_kg=self._optional_float(payload.get("muscle_rate")),
                water_pct=self._optional_float(payload.get("moisture_rate")),
                bone_mass_kg=self._optional_float(payload.get("bone_mass")),
                visceral_fat_score=self._optional_int(payload.get("visceral_fat")),
                basal_metabolism_kcal=self._optional_int(payload.get("basal_metabolism")),
                metabolic_age=self._optional_int(payload.get("body_age")),
            )

    async def iter_heart_rate(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> AsyncIterator[HeartRateSample]:
        if not self.is_connected() or not start_date or not end_date:
            return
            yield

        records = await self._fetch_key("heart_rate", start_date, end_date)
        for item in records:
            payload = self._parse_value(item)
            sample_type = "passive" if int(payload.get("type", 0)) == 0 else "active"
            yield HeartRateSample(
                id=f"mi_fitness_hr_{int(item.get('time', 0))}",
                provider="mi_fitness",
                source_type="cloud_session",
                user_id=self.user_id or "unknown",
                timestamp=self._record_datetime(item),
                bpm=int(payload.get("bpm", 0)),
                sample_type=sample_type,
            )

    async def close(self) -> None:
        await self._close_client()
        self._connected = False
