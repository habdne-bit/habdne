"""Measure: does a Content-Length too long for int() reach the webhook route,
through uvicorn's two HTTP parsers? Raw socket requests, real server.

    measure_content_length.py <port> <label>
"""
import socket
import sys

port, label = int(sys.argv[1]), sys.argv[2]
BODY = b"{}"
CASES = [
    ("9 x 5000 digits", "9" * 5000),
    ("0 x 5000 then 2", "0" * 5000 + "2"),
    ("0 x 4299 then 2", "0" * 4299 + "2"),
    ("65537", "65537"),
    ("2 (true length)", "2"),
]


def send(value):
    head = (f"POST /webhooks/whatsapp HTTP/1.1\r\nHost: x\r\n"
            f"Content-Type: application/json\r\nContent-Length: {value}\r\n"
            f"X-Turab-Relay-Signature: sha256={'0' * 64}\r\nConnection: close\r\n\r\n")
    s = socket.create_connection(("127.0.0.1", port), timeout=10)
    try:
        s.sendall(head.encode() + BODY)
        data = b""
        try:
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            return "TIMEOUT (no answer in 10 s)"
    finally:
        s.close()
    if not data:
        return "connection closed, no answer"
    first = data.split(b"\r\n", 1)[0].decode(errors="replace")
    body = data.split(b"\r\n\r\n", 1)[-1][:160].decode(errors="replace")
    return f"{first} | {body}"


print(f"== {label}")
for name, value in CASES:
    print(f"  Content-Length {name:18}: {send(value)}")
