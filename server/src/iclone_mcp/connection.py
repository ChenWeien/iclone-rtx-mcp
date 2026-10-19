from __future__ import annotations

import asyncio
import json
import os
from typing import Any


HOST = "127.0.0.1"
DEFAULT_PORT = 9880
PROTOCOL_VERSION = 1
MAX_FRAME_SIZE = 1024 * 1024
COMMAND_TIMEOUT_SECONDS = 180.0


class ICloneBridgeError(RuntimeError):
    """A connection or command failure reported to an MCP tool caller."""


class ICloneConnection:
    def __init__(self, port: int | None = None) -> None:
        self.port = port if port is not None else self._port_from_environment()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @staticmethod
    def _port_from_environment() -> int:
        value = os.environ.get("ICLONE_MCP_PORT", str(DEFAULT_PORT))
        try:
            port = int(value)
        except ValueError as error:
            raise ICloneBridgeError("ICLONE_MCP_PORT must be an integer.") from error
        if port < 1024 or port > 65535:
            raise ICloneBridgeError("ICLONE_MCP_PORT must be between 1024 and 65535.")
        return port

    async def close(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def request(
        self, command_type: str, params: dict[str, Any] | None = None
    ) -> Any:
        request = {"type": command_type, "params": params or {}}
        async with self._lock:
            await self._ensure_connected()
            return await self._exchange(request)

    async def _ensure_connected(self) -> None:
        if self._writer is not None and not self._writer.is_closing():
            return

        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(
                    HOST,
                    self.port,
                    limit=MAX_FRAME_SIZE + 1,
                ),
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
            status = await self._exchange({"type": "get_status", "params": {}})
        except ICloneBridgeError:
            await self.close()
            raise
        except (ConnectionError, OSError, asyncio.TimeoutError) as error:
            await self.close()
            raise ICloneBridgeError(
                "Could not connect to iClone at {0}:{1}. "
                "Open iClone and enable Plugins > iClone MCP > Enable Listener.".format(
                    HOST, self.port
                )
            ) from error

        version = status.get("protocol_version") if isinstance(status, dict) else None
        if version != PROTOCOL_VERSION:
            await self.close()
            raise ICloneBridgeError(
                "Unsupported iClone bridge protocol version {0}; expected {1}.".format(
                    version, PROTOCOL_VERSION
                )
            )

    async def _exchange(self, request: dict[str, Any]) -> Any:
        if self._reader is None or self._writer is None:
            raise ICloneBridgeError("The iClone bridge is not connected.")

        encoded = (
            json.dumps(request, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            + b"\n"
        )
        if len(encoded) - 1 > MAX_FRAME_SIZE:
            raise ICloneBridgeError("Request exceeds the 1 MiB bridge limit.")

        try:
            self._writer.write(encoded)
            await asyncio.wait_for(
                self._writer.drain(),
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
            response_line = await asyncio.wait_for(
                self._reader.readline(),
                timeout=COMMAND_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as error:
            await self.close()
            raise ICloneBridgeError(
                "iClone did not respond within 180 seconds. The command was not retried."
            ) from error
        except (ConnectionError, OSError, ValueError) as error:
            await self.close()
            raise ICloneBridgeError(
                "The iClone connection closed during the command. "
                "The command was not retried because it may already have changed the scene."
            ) from error

        if not response_line:
            await self.close()
            raise ICloneBridgeError(
                "The iClone connection closed without a response. "
                "The command was not retried because it may already have changed the scene."
            )
        if len(response_line) - 1 > MAX_FRAME_SIZE:
            await self.close()
            raise ICloneBridgeError("iClone returned a response larger than 1 MiB.")

        try:
            response = json.loads(response_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            await self.close()
            raise ICloneBridgeError("iClone returned invalid UTF-8 JSON.") from error
        if not isinstance(response, dict):
            raise ICloneBridgeError("iClone returned a non-object response.")
        if response.get("status") == "error":
            message = response.get("message")
            raise ICloneBridgeError(
                str(message) if message else "iClone rejected the command."
            )
        if response.get("status") != "success" or "result" not in response:
            raise ICloneBridgeError("iClone returned an invalid response envelope.")
        return response["result"]
