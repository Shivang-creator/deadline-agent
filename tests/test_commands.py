from __future__ import annotations

from datetime import UTC, datetime

from deadline_agent.core.commands import (
    AddCommand,
    HelpCommand,
    ListCommand,
    RemoveCommand,
    UnknownCommand,
    parse_command,
)

NOW = datetime(2026, 8, 16, 12, 0, 0, tzinfo=UTC)  # Sun 16 Aug, 17:30 IST


def test_add_junk_word_before_date():
    # "CS Girlies 17 Aug 9pm" — the name/date boundary isn't marked; the
    # greedy longest-date-suffix-first split must land on name="CS Girlies".
    cmd = parse_command("/add CS Girlies 17 Aug 9pm", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.name == "CS Girlies"
    assert cmd.due_at is not None
    local = cmd.due_at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Kolkata"))
    assert (local.day, local.hour) == (17, 21)


def test_add_relative_phrase():
    cmd = parse_command("/add Homework in 6 hours", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.name == "Homework"
    assert cmd.due_at is not None
    assert abs((cmd.due_at - NOW).total_seconds() - 6 * 3600) < 60


def test_add_multiword_name_with_relative_days():
    cmd = parse_command("/add Impact Forge submission in 2 days", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.name == "Impact Forge submission"
    assert cmd.due_at is not None


def test_add_iso_timestamp():
    cmd = parse_command("/add OregonHacks 2026-08-18T23:59:00+05:30", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.name == "OregonHacks"
    assert cmd.due_at is not None


def test_add_missing_date_entirely():
    cmd = parse_command("/add JustAName", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.due_at is None


def test_add_no_args_at_all():
    cmd = parse_command("/add", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.name == "" and cmd.due_at is None


def test_add_unparseable_date_words():
    cmd = parse_command("/add MyThing whenever I feel like it", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.due_at is None


def test_list_command_and_aliases():
    assert isinstance(parse_command("/list", now=NOW), ListCommand)
    assert isinstance(parse_command("/ls", now=NOW), ListCommand)
    assert isinstance(parse_command("/LIST", now=NOW), ListCommand)


def test_remove_command_and_aliases():
    cmd = parse_command("/remove OregonHacks", now=NOW)
    assert isinstance(cmd, RemoveCommand)
    assert cmd.name == "OregonHacks"
    assert isinstance(parse_command("/rm Foo", now=NOW), RemoveCommand)
    assert isinstance(parse_command("/delete Foo", now=NOW), RemoveCommand)


def test_remove_with_no_name():
    cmd = parse_command("/remove", now=NOW)
    assert isinstance(cmd, RemoveCommand)
    assert cmd.name == ""


def test_help_command_and_start_alias():
    assert isinstance(parse_command("/help", now=NOW), HelpCommand)
    assert isinstance(parse_command("/start", now=NOW), HelpCommand)


def test_telegram_group_botname_suffix():
    # Telegram allows "/add@YourBotName ..." in group chats.
    cmd = parse_command("/add@DeadlineBot Homework in 6 hours", now=NOW)
    assert isinstance(cmd, AddCommand)
    assert cmd.name == "Homework"


def test_plain_text_is_unknown():
    cmd = parse_command("hey what's up", now=NOW)
    assert isinstance(cmd, UnknownCommand)
    assert cmd.raw == "hey what's up"


def test_empty_text_is_unknown():
    cmd = parse_command("", now=NOW)
    assert isinstance(cmd, UnknownCommand)


def test_unrecognized_slash_command_is_unknown():
    cmd = parse_command("/frobnicate", now=NOW)
    assert isinstance(cmd, UnknownCommand)
