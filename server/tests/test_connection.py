import asyncio
import json

from iclone_mcp import connection as connection_module
from iclone_mcp.connection import ICloneBridgeError, ICloneConnection


def run(coroutine):
    return asyncio.run(coroutine)


def test_persistent_connection_and_protocol_probe():
    async def scenario():
        connection_count = 0
        requests = []

        async def handle(reader, writer):
            nonlocal connection_count
            connection_count += 1
            while line := await reader.readline():
                request = json.loads(line)
                requests.append(request["type"])
                result = (
                    {"protocol_version": 1}
                    if request["type"] == "get_status"
                    else {"command": request["type"]}
                )
                writer.write(
                    json.dumps({"status": "success", "result": result}).encode()
                    + b"\n"
                )
                await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        bridge = ICloneConnection(port)
        try:
            assert await bridge.request("undo") == {"command": "undo"}
            assert await bridge.request("redo") == {"command": "redo"}
            assert connection_count == 1
            assert requests == ["get_status", "undo", "redo"]
        finally:
            await bridge.close()
            server.close()
            await server.wait_closed()

    run(scenario())


def test_protocol_mismatch_closes_connection():
    async def scenario():
        async def handle(reader, writer):
            await reader.readline()
            writer.write(
                b'{"status":"success","result":{"protocol_version":99}}\n'
            )
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        bridge = ICloneConnection(server.sockets[0].getsockname()[1])
        try:
            try:
                await bridge.request("undo")
            except ICloneBridgeError as error:
                assert "protocol version 99" in str(error)
            else:
                raise AssertionError("Expected protocol mismatch")
        finally:
            await bridge.close()
            server.close()
            await server.wait_closed()

    run(scenario())


def test_dropped_mutation_is_not_replayed():
    async def scenario():
        mutation_count = 0

        async def handle(reader, writer):
            nonlocal mutation_count
            await reader.readline()
            writer.write(
                b'{"status":"success","result":{"protocol_version":1}}\n'
            )
            await writer.drain()
            request = json.loads(await reader.readline())
            if request["type"] == "delete_objects":
                mutation_count += 1
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        bridge = ICloneConnection(server.sockets[0].getsockname()[1])
        try:
            try:
                await bridge.request("delete_objects", {"object_ids": ["one"]})
            except ICloneBridgeError as error:
                assert "not retried" in str(error)
            else:
                raise AssertionError("Expected dropped response")
            assert mutation_count == 1
        finally:
            await bridge.close()
            server.close()
            await server.wait_closed()

    run(scenario())


def test_timeout_reports_without_retry():
    async def scenario():
        original_timeout = connection_module.COMMAND_TIMEOUT_SECONDS
        connection_module.COMMAND_TIMEOUT_SECONDS = 0.05

        async def handle(reader, writer):
            await reader.readline()
            await asyncio.sleep(1)
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        bridge = ICloneConnection(server.sockets[0].getsockname()[1])
        try:
            try:
                await bridge.request("undo")
            except ICloneBridgeError as error:
                assert "180 seconds" in str(error)
            else:
                raise AssertionError("Expected timeout")
        finally:
            connection_module.COMMAND_TIMEOUT_SECONDS = original_timeout
            await bridge.close()
            server.close()
            await server.wait_closed()

    run(scenario())
