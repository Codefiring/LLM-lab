#!/usr/bin/env python3
"""Read users and chats from an Open WebUI SQLite database (read only)."""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def timestamp(value):
    if value is None:
        return ""
    return datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def user_id_for(conn, args):
    if args.user_id:
        row = conn.execute('SELECT id FROM "user" WHERE id = ?', (args.user_id,)).fetchone()
    else:
        row = conn.execute('SELECT id FROM "user" WHERE email = ?', (args.email,)).fetchone()
    if row is None:
        raise ValueError("用户不存在")
    return row["id"]


def load_chat(conn, chat_id, owner_id):
    row = conn.execute(
        "SELECT id, user_id, title, chat, created_at, updated_at "
        "FROM chat WHERE id = ? AND user_id = ?",
        (chat_id, owner_id),
    ).fetchone()
    if row is None:
        raise ValueError("该用户没有此聊天")
    return row


def messages_for(conn, row):
    # Recent versions also store messages in chat_message. The chat JSON remains
    # useful for older databases and for preserving the complete conversation.
    table_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_message'"
    ).fetchone()
    if table_exists:
        messages = conn.execute(
            "SELECT id, role, content, created_at FROM chat_message "
            "WHERE chat_id = ? ORDER BY created_at, rowid",
            (row["id"],),
        ).fetchall()
        if messages:
            return [dict(message) | {"content": parse_json(message["content"])} for message in messages]

    data = parse_json(row["chat"]) or {}
    history = data.get("history") or {}
    message_map = history.get("messages") or {}
    if isinstance(message_map, dict) and message_map:
        return list(message_map.values())
    return data.get("messages") or []


def parse_json(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            part.get("text", json.dumps(part, ensure_ascii=False)) if isinstance(part, dict)
            else str(part)
            for part in content
        )
    return json.dumps(content, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True, help="webui.db 的路径")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("users", help="列出用户")
    for name, help_text in (
        ("chats", "列出某用户的聊天"),
        ("show", "显示一段聊天的消息"),
        ("export", "将某用户的聊天导出为 JSON"),
    ):
        command = sub.add_parser(name, help=help_text)
        identity = command.add_mutually_exclusive_group(required=True)
        identity.add_argument("--email", help="用户邮箱")
        identity.add_argument("--user-id", help="用户 ID")
        if name == "chats":
            command.add_argument("--limit", type=int, default=50, help="最多显示条数，默认 50")
        elif name == "show":
            command.add_argument("chat_id", help="聊天 ID")
        else:
            command.add_argument("--output", type=Path, required=True, help="输出 JSON 文件")
    args = parser.parse_args()

    if not args.db.is_file():
        parser.error(f"数据库文件不存在: {args.db}")
    if args.command == "chats" and args.limit < 1:
        parser.error("--limit 必须大于 0")

    try:
        with sqlite3.connect(f"{args.db.resolve().as_uri()}?mode=ro", uri=True) as conn:
            conn.row_factory = sqlite3.Row
            if args.command == "users":
                for row in conn.execute('SELECT id, email, name, role FROM "user" ORDER BY created_at'):
                    print(f'{row["id"]}\t{row["email"]}\t{row["name"]}\t{row["role"]}')
                return

            owner_id = user_id_for(conn, args)
            if args.command == "chats":
                rows = conn.execute(
                    "SELECT id, title, created_at FROM chat WHERE user_id = ? "
                    "ORDER BY created_at DESC LIMIT ?", (owner_id, args.limit)
                )
                for row in rows:
                    print(f'{row["id"]}\t{timestamp(row["created_at"])}\t{row["title"]}')
            elif args.command == "show":
                row = load_chat(conn, args.chat_id, owner_id)
                print(f'{row["title"]} ({row["id"]})')
                for message in messages_for(conn, row):
                    print(f'\n[{message.get("role", "unknown")}] {content_text(message.get("content"))}')
            else:
                chats = []
                for item in conn.execute(
                    "SELECT id, user_id, title, chat, created_at, updated_at "
                    "FROM chat WHERE user_id = ? ORDER BY created_at", (owner_id,)
                ):
                    row = dict(item)
                    row["chat"] = parse_json(row["chat"])
                    row["messages"] = messages_for(conn, item)
                    chats.append(row)
                args.output.write_text(json.dumps(chats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"已导出 {len(chats)} 段聊天到 {args.output}")
    except (sqlite3.Error, ValueError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
