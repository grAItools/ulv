"""Tests for `ulv serve` (src/ulv/cli.py)."""

import http.server
import threading
import urllib.request

from ulv.cli import main, serve_site


def _site(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html>hello</html>")
    return site


def test_serve_smoke(tmp_path):
    site = _site(tmp_path)
    server = serve_site(site, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        response = urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html")
        assert response.status == 200
        assert b"hello" in response.read()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_cli_serve_prints_url_and_exits_cleanly(tmp_path, capsys, monkeypatch):
    # serve_forever would block; returning immediately keeps the CLI path
    # (arg parsing, directory check, URL print) fully exercised.
    monkeypatch.setattr(
        http.server.ThreadingHTTPServer, "serve_forever", lambda self: None
    )
    site = _site(tmp_path)
    rc = main(["serve", str(site), "--port", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "http://127.0.0.1:" in out


def test_cli_serve_directory_defaults_from_config(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        http.server.ThreadingHTTPServer, "serve_forever", lambda self: None
    )
    site = _site(tmp_path)
    config = tmp_path / "ulv.toml"
    config.write_text(f'output_dir = "{site}"\n')
    rc = main(["serve", "--config", str(config), "--port", "0"])
    assert rc == 0
    assert "http://127.0.0.1:" in capsys.readouterr().out


def test_cli_serve_wildcard_bind_prints_clickable_url(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        http.server.ThreadingHTTPServer, "serve_forever", lambda self: None
    )
    site = _site(tmp_path)
    rc = main(["serve", str(site), "--host", "0.0.0.0", "--port", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "http://127.0.0.1:" in out
    assert "http://0.0.0.0:" not in out


def test_serve_no_directory_anywhere_exits_nonzero(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["serve"])
    assert rc == 1
    assert "output_dir" in capsys.readouterr().err


def test_serve_missing_site_dir_exits_nonzero(tmp_path, capsys):
    rc = main(["serve", str(tmp_path / "nope")])
    assert rc == 1
    assert "nope" in capsys.readouterr().err


def test_serve_dir_without_index_html_exits_nonzero(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    rc = main(["serve", str(empty)])
    assert rc == 1
    assert "index.html" in capsys.readouterr().err
