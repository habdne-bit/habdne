import socket, sys
port = int(sys.argv[1])
head = (b"POST /webhooks/whatsapp HTTP/1.1\r\nHost: x\r\nContent-Type: application/json\r\n"
        b"Content-Length: \xb2\r\nX-Turab-Relay-Signature: sha256=" + b"0" * 64 +
        b"\r\nConnection: close\r\n\r\n{}")
s = socket.create_connection(("127.0.0.1", port), timeout=10); s.sendall(head)
data = b""
while (c := s.recv(65536)): data += c
print("  Content-Length b'\\xb2' (latin-1 '²'):", data.split(b"\r\n", 1)[0].decode(), "|",
      data.split(b"\r\n\r\n", 1)[-1][:120].decode(errors="replace"))
