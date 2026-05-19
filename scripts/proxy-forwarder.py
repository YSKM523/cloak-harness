#!/usr/bin/env python3
"""Minimal HTTP CONNECT proxy forwarder with upstream Basic auth.

Listens on 127.0.0.1:<local-port>, accepts CONNECT requests from Chromium,
opens a parallel CONNECT to the upstream HTTP proxy with Proxy-Authorization,
then pipes bytes both ways. Designed for HTTPS browsing only.

Usage:
    python3 proxy-forwarder.py <session-index> [local-port]

Reads $PROXIES_FILE (default: ./proxies.txt) in the format:
    host:port:user:pass
"""
import asyncio
import base64
import os
import sys
from pathlib import Path

INDEX = int(sys.argv[1]) if len(sys.argv) > 1 else 0
LOCAL_PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 18888

PROXIES_FILE = Path(os.environ.get("PROXIES_FILE", "proxies.txt"))
lines = PROXIES_FILE.read_text().strip().splitlines()
host, port, user, pw = lines[INDEX].split(":", 3)
UP_HOST, UP_PORT = host, int(port)
AUTH = base64.b64encode(f"{user}:{pw}".encode()).decode()
print(f"[forwarder] session #{INDEX} → {UP_HOST}:{UP_PORT} as {user}", flush=True)


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def handle(client_r, client_w):
    try:
        request_lines = []
        while True:
            line = await client_r.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            request_lines.append(line)
        if not request_lines:
            client_w.close()
            return
        first = request_lines[0].decode("latin1", errors="replace").strip()
        method, target, _ = first.split(" ", 2)
        if method.upper() != "CONNECT":
            client_w.write(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            await client_w.drain()
            client_w.close()
            return

        try:
            up_r, up_w = await asyncio.open_connection(UP_HOST, UP_PORT)
        except Exception:
            client_w.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_w.drain()
            client_w.close()
            return

        connect_req = (
            f"CONNECT {target} HTTP/1.1\r\n"
            f"Host: {target}\r\n"
            f"Proxy-Authorization: Basic {AUTH}\r\n"
            f"Proxy-Connection: keep-alive\r\n"
            f"\r\n"
        ).encode()
        up_w.write(connect_req)
        await up_w.drain()

        status_line = await up_r.readline()
        if not status_line:
            client_w.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_w.drain()
            client_w.close()
            up_w.close()
            return
        while True:
            line = await up_r.readline()
            if not line or line in (b"\r\n", b"\n"):
                break

        status_text = status_line.decode("latin1", errors="replace").strip()
        if "200" not in status_text:
            print(f"[forwarder] upstream rejected: {status_text}", flush=True)
            client_w.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_w.drain()
            client_w.close()
            up_w.close()
            return

        client_w.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_w.drain()

        await asyncio.gather(pipe(client_r, up_w), pipe(up_r, client_w))
    except Exception as e:
        print(f"[forwarder] error: {e}", flush=True)
        try:
            client_w.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle, "127.0.0.1", LOCAL_PORT)
    print(f"[forwarder] listening on 127.0.0.1:{LOCAL_PORT}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
