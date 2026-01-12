root@racknerd-5c23903:/tmp/dm-trafficbot# journalctl -u dm-relay -f
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | dm-relay             | ============================================================
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | dm-relay             | Bind Address: 0.0.0.0:8765
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | dm-relay             | WebSocket URL: ws://0.0.0.0:8765/ws
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | dm-relay             | ============================================================
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | core.relay_server    | Starting Relay Server on 0.0.0.0:8765
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | dm-relay             | Starting Relay Server on 0.0.0.0:8765
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | core.relay_server    | Relay Server running on ws://0.0.0.0:8765/ws
Dec 24 18:38:52 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:38:52 | INFO     | dm-relay             | Relay Server running on ws://0.0.0.0:8765/ws
Dec 24 18:39:06 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:06 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: 86ce5bf90d4d4e01)
Dec 24 18:39:06 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:06 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: 86ce5bf90d4d4e01)
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:12 | ERROR    | core.relay_server    | Error handling client 86ce5bf90d4d4e01: unhashable type: 'ConnectedClient'
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:12 | INFO     | dm-relay             | Error handling client 86ce5bf90d4d4e01: unhashable type: 'ConnectedClient'
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:12 | ERROR    | aiohttp.server       | Error handling request from 50.35.69.112
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]: Traceback (most recent call last):
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_protocol.py", line 510, in _handle_request
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:     resp = await request_handler(request)
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_app.py", line 569, in _handle
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:     return await handler(request)
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:            ^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/core/relay_server.py", line 211, in _handle_websocket
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:     await self._disconnect_client(client)
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/core/relay_server.py", line 368, in _disconnect_client
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:     if client in self.controllers:
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]:        ^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:39:12 racknerd-5c23903 dm-relay[1261796]: TypeError: unhashable type: 'ConnectedClient'
Dec 24 18:39:14 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:14 | INFO     | core.relay_server    | New connection from 50.35.69.112 (id: 730e1f46d6c86a75)
Dec 24 18:39:14 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:14 | INFO     | dm-relay             | New connection from 50.35.69.112 (id: 730e1f46d6c86a75)
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:18 | ERROR    | core.relay_server    | Error handling client 730e1f46d6c86a75: unhashable type: 'ConnectedClient'
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:18 | INFO     | dm-relay             | Error handling client 730e1f46d6c86a75: unhashable type: 'ConnectedClient'
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]: 2025-12-24 18:39:18 | ERROR    | aiohttp.server       | Error handling request from 50.35.69.112
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]: Traceback (most recent call last):
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_protocol.py", line 510, in _handle_request
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:     resp = await request_handler(request)
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/.venv/lib/python3.11/site-packages/aiohttp/web_app.py", line 569, in _handle
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:     return await handler(request)
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:            ^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/core/relay_server.py", line 211, in _handle_websocket
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:     await self._disconnect_client(client)
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:   File "/opt/dm-relay/core/relay_server.py", line 368, in _disconnect_client
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:     if client in self.controllers:
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]:        ^^^^^^^^^^^^^^^^^^^^^^^^^^
Dec 24 18:39:18 racknerd-5c23903 dm-relay[1261796]: TypeError: unhashable type: 'ConnectedClient'