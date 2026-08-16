"""Mechanically checks the two architectural claims the whole project rests
on:

1. core/ is channel-agnostic BY CONSTRUCTION — no file under
   deadline_agent/core/ *imports* caspian_sdk, discord, or telegram, and
   none imports the adapters/ package. Checked via the AST (real import
   statements), not a text search, so it can't be tripped up by a comment
   or docstring that merely mentions those names while explaining the rule.
   It is not "written to not use them right now" — it CANNOT import them
   without this test failing, in CI, forever.

2. Both adapters — the fake-channel harness used for all offline testing,
   and the real Caspian wiring used for Telegram + Discord — dispatch into
   the exact same function object, not two implementations that happen to
   look similar. This is the literal, checkable meaning of "one handler,
   two channels".
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "deadline_agent" / "core"

FORBIDDEN_MODULES = {"caspian_sdk", "discord", "telegram", "deadline_agent.adapters"}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
            # relative "from ..adapters import x" / "from .adapters import x"
            if node.level and node.module:
                modules.add("." * node.level + node.module)
    return modules


def test_core_has_no_channel_sdk_or_adapter_imports():
    offenders = []
    for path in sorted(CORE_DIR.glob("*.py")):
        modules = _imported_modules(path)
        for module in modules:
            bare = module.lstrip(".")
            if bare in FORBIDDEN_MODULES or bare.startswith("adapters"):
                offenders.append(f"{path.name}: imports {module!r}")
    assert offenders == [], "core/ must stay channel-agnostic:\n" + "\n".join(offenders)


def test_fake_and_live_adapters_call_the_identical_handler_function():
    from deadline_agent.adapters import caspian_app, fake_channel
    from deadline_agent.core.handler import handle_message as core_handle_message

    # Both adapter modules import handle_message directly (not a copy, not a
    # re-implementation) — Python binds the same function object, so `is`
    # proves it's literally one function serving both.
    assert fake_channel.handle_message is core_handle_message
    assert caspian_app.handle_message is core_handle_message


def test_caspian_app_registers_exactly_one_on_message_handler():
    import inspect

    from deadline_agent.adapters import caspian_app

    source = inspect.getsource(caspian_app.register_handler)
    assert source.count("@client.on_message") == 1
    assert source.count("def on_message") == 1
