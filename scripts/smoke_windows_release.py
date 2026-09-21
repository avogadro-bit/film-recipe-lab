"""Start the packaged server, verify its assets/API, then stop our own process."""
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='kora-smoke-') as directory:
        app = ROOT / 'dist/windows/Kora/Kora.exe'
        process = subprocess.Popen([str(app), '--no-browser', '--port', str(port), '--root', directory])
        try:
            base = f'http://127.0.0.1:{port}'
            for attempt in range(60):
                if process.poll() is not None:
                    raise RuntimeError(f'Packaged app exited: {process.returncode}')
                try:
                    with urlopen(base, timeout=1) as response:
                        page = response.read().decode('utf-8')
                    break
                except OSError:
                    time.sleep(.5)
            else:
                raise RuntimeError('Packaged app did not start within 30 seconds')
            assert '<title>KŌRA</title>' in page
            for asset in ('app.js', 'style.css', 'kora.css', 'diagnostics.js'):
                with urlopen(base + '/' + asset, timeout=5) as response:
                    assert len(response.read()) > 100
            print(json.dumps({'packaged_server': 'ok', 'assets': 'ok'}))
        finally:
            process.terminate()
            process.wait(timeout=15)


if __name__ == '__main__':
    main()
