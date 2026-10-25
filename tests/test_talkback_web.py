"""Exercise the authenticated talk socket with a local fake NetSDK process."""

import importlib.util
import os
import re
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

try:
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect
except ImportError:
    TestClient = None


@unittest.skipIf(TestClient is None, "web dependencies are not installed")
class TalkWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.frames = root / "frame.bin"
        password = root / "camera-password"
        password.write_bytes(b"local-test-password")
        bridge = root / "fake-bridge"
        bridge.write_text(
            "#!/usr/bin/env python3\n"
            "import os, sys\n"
            "size = int.from_bytes(sys.stdin.buffer.read(2), 'little')\n"
            "secret = sys.stdin.buffer.read(size)\n"
            "if secret != b'local-test-password': sys.exit(2)\n"
            "print('READY', flush=True)\n"
            "frame = sys.stdin.buffer.read(640)\n"
            "if len(frame) == 640:\n"
            "    open(os.environ['TEST_TALK_FRAME'], 'wb').write(frame)\n",
            encoding="utf-8",
        )
        bridge.chmod(0o755)
        cls.old_env = {key: os.environ.get(key) for key in (
            "CAMERAS_USERS_DB", "CAMERAS_SESSION_SECRET_FILE", "CAMERAS_TALK_ENABLED",
            "CAMERAS_TALK_BRIDGE", "CAMERAS_TALK_CAMERA_IP", "CAMERAS_TALK_CAMERA_USER",
            "CAMERAS_TALK_PASSWORD_FILE", "TEST_TALK_FRAME",
        )}
        secret = root / "session-secret"
        secret.write_text("a" * 48, encoding="utf-8")
        os.environ.update({
            "CAMERAS_USERS_DB": str(root / "users.sqlite3"),
            "CAMERAS_SESSION_SECRET_FILE": str(secret),
            "CAMERAS_TALK_ENABLED": "1",
            "CAMERAS_TALK_BRIDGE": str(bridge),
            "CAMERAS_TALK_CAMERA_IP": "192.0.2.9",
            "CAMERAS_TALK_CAMERA_USER": "admin",
            "CAMERAS_TALK_PASSWORD_FILE": str(password),
            "TEST_TALK_FRAME": str(cls.frames),
        })
        spec = importlib.util.spec_from_file_location(
            "camera_web_test_app", Path(__file__).resolve().parents[1] / "web/app.py"
        )
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        with cls.module.db() as connection:
            connection.execute(
                "INSERT INTO users(username,password_hash) VALUES(?,?)",
                ("tester", cls.module.password_hasher.hash("test-password")),
            )

    @classmethod
    def tearDownClass(cls):
        for key, value in cls.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls.temp.cleanup()

    def test_talk_requires_login_origin_and_csrf_then_passes_audio(self):
        with closing(TestClient(self.module.app, base_url="https://testserver")) as client:
            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("wss://testserver/talk/ws", headers={"origin": "https://testserver"}):
                    pass

            page = client.get("/login")
            csrf = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
            response = client.post(
                "/login",
                data={"username": "tester", "password": "test-password", "csrf": csrf},
                follow_redirects=False,
            )
            self.assertEqual(response.status_code, 303)
            dashboard = client.get("/")
            self.assertIn("Segure para falar", dashboard.text)
            self.assertNotIn('id="talkButton" type="button" disabled', dashboard.text)
            csrf = re.search(r'name="csrf" value="([^"]+)"', dashboard.text).group(1)

            with self.assertRaises(WebSocketDisconnect):
                with client.websocket_connect("wss://testserver/talk/ws", headers={"origin": "https://evil.example"}):
                    pass

            with client.websocket_connect("wss://testserver/talk/ws", headers={"origin": "https://testserver"}) as socket:
                socket.send_text("wrong-csrf")
                with self.assertRaises(WebSocketDisconnect):
                    socket.receive_json()

            with client.websocket_connect("wss://testserver/talk/ws", headers={"origin": "https://testserver"}) as socket:
                socket.send_text(csrf)
                self.assertEqual(socket.receive_json(), {"ready": True})
                with client.websocket_connect("wss://testserver/talk/ws", headers={"origin": "https://testserver"}) as second:
                    second.send_text(csrf)
                    self.assertIn("já está em uso", second.receive_json()["error"])
                socket.send_bytes(bytes(range(256)) * 2 + bytes(128))
                for _ in range(20):
                    if self.frames.exists():
                        break
                    time.sleep(0.02)
                socket.send_text("stop")
            self.assertEqual(self.frames.read_bytes(), bytes(range(256)) * 2 + bytes(128))


if __name__ == "__main__":
    unittest.main()
