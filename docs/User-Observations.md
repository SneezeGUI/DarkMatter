root@racknerd-5c23903:/tmp/dm-trafficbot# sudo systemctl restart dm-relay
root@racknerd-5c23903:/tmp/dm-trafficbot# sudo systemctl status dm-relay
● dm-relay.service - DarkMatter Traffic Bot Relay Server
     Loaded: loaded (/etc/systemd/system/dm-relay.service; enabled; preset: enabled)
     Active: active (running) since Wed 2025-12-24 18:42:26 EST; 1s ago
       Docs: https://github.com/your-repo/dm-trafficbot
   Main PID: 1261921 (python)
      Tasks: 1 (limit: 2314)
     Memory: 22.9M
        CPU: 404ms
     CGroup: /system.slice/dm-relay.service
             └─1261921 /opt/dm-relay/.venv/bin/python /opt/dm-relay/relay.py

Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | =========>
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | DarkMatte>
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | =========>
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | Bind Addr>
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | WebSocket>
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | =========>
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | core.relay_server    | Starting >
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | Starting >
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | core.relay_server    | Relay Ser>
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | Relay Ser>
lines 1-21/21 (END)
root@racknerd-5c23903:/tmp/dm-trafficbot# journalctl -u dm-relay -f
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | ============================================================
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | DarkMatter Relay Server Starting
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | ============================================================
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | Bind Address: 0.0.0.0:8765
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | WebSocket URL: ws://0.0.0.0:8765/ws
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | ============================================================
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | core.relay_server    | Starting Relay Server on 0.0.0.0:8765
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | Starting Relay Server on 0.0.0.0:8765
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | core.relay_server    | Relay Server running on ws://0.0.0.0:8765/ws
Dec 24 18:42:26 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:26 | INFO     | dm-relay             | Relay Server running on ws://0.0.0.0:8765/ws
Dec 24 18:42:44 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:44 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: c7b5cd5a80d7fb58)
Dec 24 18:42:44 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:44 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: c7b5cd5a80d7fb58)
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:48 | ERROR    | core.relay_server    | Error handling client c7b5cd5a80d7fb58: unhashable type: 'ConnectedClient'
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:48 | INFO     | dm-relay             | Error handling client c7b5cd5a80d7fb58: unhashable type: 'ConnectedClient'
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:48 | ERROR    | aiohttp.server       | Error handling request from 50.35.69.112
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]: Traceback (most recent call last):
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_protocol.py", line 510, in _handle_request
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:     resp = await request_handler(request)
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_app.py", line 569, in _handle
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:     return await handler(request)
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 211, in _handle_websocket
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:     await self._disconnect_client(client)
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 368, in _disconnect_client
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:     if client in self.controllers:
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]:        ^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:42:48 racknerd-5c23903 dm-relay[1261921]: TypeError: unhashable type: 'ConnectedClient'
Dec 24 18:42:50 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:50 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: b8615fecdc90b283)
Dec 24 18:42:50 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:50 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: b8615fecdc90b283)
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:54 | ERROR    | core.relay_server    | Error handling client b8615fecdc90b283: unhashable type: 'ConnectedClient'
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:54 | INFO     | dm-relay             | Error handling client b8615fecdc90b283: unhashable type: 'ConnectedClient'
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:54 | ERROR    | aiohttp.server       | Error handling request from 50.35.69.112
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]: Traceback (most recent call last):
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_protocol.py", line 510, in _handle_request
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:     resp = await request_handler(request)
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_app.py", line 569, in _handle
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:     return await handler(request)
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 211, in _handle_websocket
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:     await self._disconnect_client(client)
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 368, in _disconnect_client
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:     if client in self.controllers:
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]:        ^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:42:54 racknerd-5c23903 dm-relay[1261921]: TypeError: unhashable type: 'ConnectedClient'
Dec 24 18:42:56 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:56 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: aba626627033cd4c)
Dec 24 18:42:56 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:56 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: aba626627033cd4c)
Dec 24 18:42:58 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:58 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: c8c21ab6bf29bd64)
Dec 24 18:42:58 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:42:58 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: c8c21ab6bf29bd64)
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:00 | ERROR    | core.relay_server    | Error handling client aba626627033cd4c: unhashable type: 'ConnectedClient'
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:00 | INFO     | dm-relay             | Error handling client aba626627033cd4c: unhashable type: 'ConnectedClient'
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:00 | ERROR    | aiohttp.server       | Error handling request from 50.35.69.112
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]: Traceback (most recent call last):
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_protocol.py", line 510, in _handle_request
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:     resp = await request_handler(request)
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_app.py", line 569, in _handle
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:     return await handler(request)
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 211, in _handle_websocket
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:     await self._disconnect_client(client)
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 368, in _disconnect_client
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:     if client in self.controllers:
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]:        ^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:43:00 racknerd-5c23903 dm-relay[1261921]: TypeError: unhashable type: 'ConnectedClient'
Dec 24 18:43:02 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:02 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: 620403d2b60e2af5)
Dec 24 18:43:02 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:02 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: 620403d2b60e2af5)
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:03 | ERROR    | core.relay_server    | Error handling client c8c21ab6bf29bd64: unhashable type: 'ConnectedClient'
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:03 | INFO     | dm-relay             | Error handling client c8c21ab6bf29bd64: unhashable type: 'ConnectedClient'
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:03 | ERROR    | aiohttp.server       | Error handling request from 50.35.69.112
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]: Traceback (most recent call last):
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_protocol.py", line 510, in _handle_request
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:     resp = await request_handler(request)
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_app.py", line 569, in _handle
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:     return await handler(request)
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:            ^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 211, in _handle_websocket
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:     await self._disconnect_client(client)
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:   File "/opt/dm-relay/core/relay_server.py", line 368, in _disconnect_client
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:     if client in self.controllers:
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]:        ^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:43:03 racknerd-5c23903 dm-relay[1261921]: TypeError: unhashable type: 'ConnectedClient'
Dec 24 18:43:05 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:05 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: 3889dbdfd7b6002a)
Dec 24 18:43:05 racknerd-5c23903 dm-relay[1261921]: 2025-12-24 18:43:05 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: 3889dbdfd7b6002a)