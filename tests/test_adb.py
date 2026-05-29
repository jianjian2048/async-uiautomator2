import asyncio
import time

from async_uiautomator2.adb import AsyncSocketConnection, ThreadedAdbProcess


class FakeSocket:
    def __init__(self) -> None:
        self.sent = b""
        self.closed = False

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, size: int) -> bytes:
        return b"pong"[:size]

    def close(self) -> None:
        self.closed = True


def test_async_socket_connection_wraps_sync_socket() -> None:
    async def run() -> None:
        sock = FakeSocket()
        conn = AsyncSocketConnection(sock)

        await conn.sendall(b"GET /ping")
        assert await conn.recv(4) == b"pong"
        await conn.close()

        assert sock.sent == b"GET /ping"
        assert sock.closed is True

    asyncio.run(run())


class FakeRawConn:
    def __init__(self) -> None:
        self.closed = False
        self._chunks = [b"hello", b""]

    def recv(self, size: int) -> bytes:
        time.sleep(0.01)
        return self._chunks.pop(0)


class FakeStream:
    def __init__(self) -> None:
        self.conn = FakeRawConn()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_threaded_adb_process_uses_daemon_reader_and_kill_closes_stream() -> None:
    async def run() -> None:
        stream = FakeStream()
        before = len(asyncio.all_tasks())
        process = ThreadedAdbProcess(stream)
        after = len(asyncio.all_tasks())

        assert after == before
        assert process._reader_thread.daemon is True

        await process.kill()

        assert stream.closed is True
        assert process.poll() == 0
        assert bytes(process.output) == b"hello"

    asyncio.run(run())
