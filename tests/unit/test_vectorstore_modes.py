"""Unit tests for vectorstore dual-mode client selection (slice 07).

Asserts:
  - When settings.CHROMA_HOST is set, _client() builds an HttpClient.
  - When settings.CHROMA_HOST is absent, _client() builds a PersistentClient.

Both paths are tested by monkeypatching the chromadb constructors and
resetting the module-level singleton between assertions.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

# Import the module under test
from apps.rag import vectorstore
from django.test import override_settings


def _reset_singleton():
    """Reset the vectorstore module's cached client singleton."""
    vectorstore._chroma_client = None


class TestVectorstoreClientMode:
    """_client() selects HttpClient vs PersistentClient based on CHROMA_HOST."""

    def setup_method(self):
        _reset_singleton()

    def teardown_method(self):
        _reset_singleton()

    def test_http_client_used_when_chroma_host_set(self):
        """When CHROMA_HOST is present, HttpClient is constructed."""
        sentinel = MagicMock(name="HttpClientInstance")

        with (
            override_settings(CHROMA_HOST="chroma-service", CHROMA_PORT=8000),
            patch("chromadb.HttpClient", return_value=sentinel) as mock_http,
        ):
            _reset_singleton()
            client = vectorstore._client()

        mock_http.assert_called_once()
        call_kwargs = mock_http.call_args
        # host argument
        assert call_kwargs.kwargs.get("host") == "chroma-service" or (
            len(call_kwargs.args) > 0 and call_kwargs.args[0] == "chroma-service"
        )
        assert client is sentinel

    def test_http_client_uses_correct_port(self):
        """HttpClient is called with the port from settings.CHROMA_PORT."""
        sentinel = MagicMock(name="HttpClientInstance")

        with (
            override_settings(CHROMA_HOST="chroma-service", CHROMA_PORT=9999),
            patch("chromadb.HttpClient", return_value=sentinel) as mock_http,
        ):
            _reset_singleton()
            vectorstore._client()

        call_kwargs = mock_http.call_args
        port_arg = call_kwargs.kwargs.get("port") or (
            call_kwargs.args[1] if len(call_kwargs.args) > 1 else None
        )
        assert int(port_arg) == 9999

    def test_persistent_client_used_when_chroma_host_absent(self, tmp_path):
        """When CHROMA_HOST is not set, PersistentClient is constructed."""
        sentinel = MagicMock(name="PersistentClientInstance")

        with override_settings(CHROMA_PERSIST_DIR=str(tmp_path)):
            # Ensure CHROMA_HOST is not on settings
            from django.conf import settings as django_settings

            if hasattr(django_settings, "CHROMA_HOST"):
                # Remove it temporarily via override_settings
                with override_settings(CHROMA_HOST=None):
                    with patch("chromadb.PersistentClient", return_value=sentinel) as mock_pc:
                        _reset_singleton()
                        client = vectorstore._client()
                    mock_pc.assert_called_once()
                    assert client is sentinel
            else:
                with patch("chromadb.PersistentClient", return_value=sentinel) as mock_pc:
                    _reset_singleton()
                    client = vectorstore._client()
                mock_pc.assert_called_once()
                assert client is sentinel

    def test_singleton_is_cached(self):
        """_client() returns the same object on successive calls."""
        sentinel = MagicMock(name="PersistentClientInstance")

        with patch("chromadb.PersistentClient", return_value=sentinel):
            _reset_singleton()
            c1 = vectorstore._client()
            c2 = vectorstore._client()

        assert c1 is c2

    def test_reset_clears_singleton(self):
        """_reset_client() clears the cached singleton."""
        sentinel_a = MagicMock(name="ClientA")
        sentinel_b = MagicMock(name="ClientB")

        with patch("chromadb.PersistentClient", side_effect=[sentinel_a, sentinel_b]):
            _reset_singleton()
            c1 = vectorstore._client()
            assert c1 is sentinel_a

            _reset_singleton()
            c2 = vectorstore._client()
            assert c2 is sentinel_b

    def test_http_client_disabled_telemetry(self):
        """HttpClient must be called with anonymized_telemetry=False."""

        sentinel = MagicMock(name="HttpClientInstance")

        with (
            override_settings(CHROMA_HOST="chroma-service", CHROMA_PORT=8000),
            patch("chromadb.HttpClient", return_value=sentinel) as mock_http,
        ):
            _reset_singleton()
            vectorstore._client()

        call_kwargs = mock_http.call_args
        settings_arg = call_kwargs.kwargs.get("settings") or (
            call_kwargs.args[2] if len(call_kwargs.args) > 2 else None
        )
        if settings_arg is not None:
            assert settings_arg.anonymized_telemetry is False

    def test_thread_safety_no_duplicate_init(self):
        """Concurrent calls to _client() create the client exactly once."""
        call_count = 0
        sentinel = MagicMock(name="Client")

        def make_client(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return sentinel

        _reset_singleton()
        results = []
        errors = []

        with patch("chromadb.PersistentClient", side_effect=make_client):

            def get_client():
                try:
                    results.append(vectorstore._client())
                except Exception as exc:
                    errors.append(exc)

            threads = [threading.Thread(target=get_client) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert not errors
        assert call_count == 1
        assert all(r is sentinel for r in results)
