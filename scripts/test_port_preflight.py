#!/usr/bin/env python3
"""Linux regression: live listener rejected; server-side TIME_WAIT accepted."""
import errno
import socket
import sys
import unittest

from instances import check_ports


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux socket semantics required")
class PortPreflightTest(unittest.TestCase):
    def test_listener_and_time_wait(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
            listener.listen(1)
            listener.settimeout(3)
            with self.assertRaises(RuntimeError):
                check_ports([port])
            with socket.create_connection(("127.0.0.1", port), timeout=3) as client:
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(3)
                    # Server sends FIN first, so TIME_WAIT belongs to its port.
                    conn.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b"")
                    client.shutdown(socket.SHUT_WR)
                    self.assertEqual(conn.recv(1), b"")
        # Reproduce the old preflight failure, rather than merely testing mocks.
        with socket.socket() as plain:
            with self.assertRaises(OSError) as caught:
                plain.bind(("127.0.0.1", port))
            self.assertEqual(caught.exception.errno, errno.EADDRINUSE)
        check_ports([port])


if __name__ == "__main__":
    unittest.main(verbosity=2)
