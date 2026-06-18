"""Unit tests for apps.common.env helpers.

Uses monkeypatch to manipulate os.environ without side effects.
No Django imports needed — these helpers are pure stdlib.
"""

import pytest
from apps.common.env import env, env_bool, env_int, env_list


class TestEnv:
    """Tests for the env() helper."""

    def test_returns_value_when_key_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY", "hello")
        assert env("TEST_KEY") == "hello"

    def test_returns_none_when_key_absent_no_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_KEY", raising=False)
        assert env("TEST_KEY") is None

    def test_returns_default_when_key_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TEST_KEY", raising=False)
        assert env("TEST_KEY", default="fallback") == "fallback"

    def test_env_var_overrides_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_KEY", "actual")
        assert env("TEST_KEY", default="fallback") == "actual"


class TestEnvBool:
    """Tests for the env_bool() helper."""

    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "Yes", "on", "ON"])
    def test_truthy_strings(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("BOOL_KEY", value)
        assert env_bool("BOOL_KEY") is True

    @pytest.mark.parametrize("value", ["0", "false", "False", "no", "off", "OFF", ""])
    def test_falsy_strings(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("BOOL_KEY", value)
        assert env_bool("BOOL_KEY") is False

    def test_returns_default_false_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BOOL_KEY", raising=False)
        assert env_bool("BOOL_KEY") is False

    def test_returns_default_true_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BOOL_KEY", raising=False)
        assert env_bool("BOOL_KEY", default=True) is True


class TestEnvInt:
    """Tests for the env_int() helper."""

    def test_parses_integer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INT_KEY", "42")
        assert env_int("INT_KEY") == 42

    def test_parses_negative_integer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INT_KEY", "-7")
        assert env_int("INT_KEY") == -7

    def test_parses_integer_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INT_KEY", "  99  ")
        assert env_int("INT_KEY") == 99

    def test_returns_default_zero_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INT_KEY", raising=False)
        assert env_int("INT_KEY") == 0

    def test_returns_custom_default_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("INT_KEY", raising=False)
        assert env_int("INT_KEY", default=5432) == 5432

    def test_returns_default_on_invalid_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("INT_KEY", "not-a-number")
        assert env_int("INT_KEY", default=9) == 9


class TestEnvList:
    """Tests for the env_list() helper."""

    def test_parses_comma_separated_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LIST_KEY", "a,b,c")
        assert env_list("LIST_KEY") == ["a", "b", "c"]

    def test_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LIST_KEY", " a , b , c ")
        assert env_list("LIST_KEY") == ["a", "b", "c"]

    def test_filters_empty_segments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LIST_KEY", "a,,b,")
        assert env_list("LIST_KEY") == ["a", "b"]

    def test_single_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LIST_KEY", "only")
        assert env_list("LIST_KEY") == ["only"]

    def test_returns_empty_list_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LIST_KEY", raising=False)
        assert env_list("LIST_KEY") == []

    def test_returns_default_list_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LIST_KEY", raising=False)
        result = env_list("LIST_KEY", default="localhost,127.0.0.1")
        assert result == ["localhost", "127.0.0.1"]
