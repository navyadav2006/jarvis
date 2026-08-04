from __future__ import annotations

from jarvis.core.security.confirmation import (
    AutoDenyConfirmation,
    CallbackConfirmation,
    ConfirmationPort,
)


def test_auto_deny_always_returns_false() -> None:
    confirmation = AutoDenyConfirmation()
    assert confirmation.confirm("allow dangerous action?") is False
    assert isinstance(confirmation, ConfirmationPort)


def test_callback_confirmation_delegates_to_the_callback() -> None:
    prompts: list[str] = []

    def callback(prompt: str) -> bool:
        prompts.append(prompt)
        return True

    confirmation = CallbackConfirmation(callback)
    assert confirmation.confirm("allow?") is True
    assert prompts == ["allow?"]


def test_callback_confirmation_coerces_truthy_return_to_bool() -> None:
    confirmation = CallbackConfirmation(lambda prompt: "yes")
    assert confirmation.confirm("allow?") is True

    confirmation = CallbackConfirmation(lambda prompt: "")
    assert confirmation.confirm("allow?") is False
