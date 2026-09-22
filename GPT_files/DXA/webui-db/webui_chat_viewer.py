#!/usr/bin/env python3
"""Local, read-only browser for an Open WebUI SQLite database."""

import argparse
import base64
import binascii
import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from read_webui_chats import messages_for, parse_json


PAGE = Path(__file__).with_suffix('.html')
SCRIPT = Path(__file__).with_suffix('.js')
PAGE_SIZE = 50


def date_bound(value, end=False):
    try:
        day = datetime.strptime(value, '%Y-%m-%d')
    except ValueError as exc:
        raise ValueError('日期格式应为 YYYY-MM-DD') from exc
    if end:
        day += timedelta(days=1)
    return int(day.timestamp())


def query_chats(conn, params):
    conditions, values = [], []
    user_id = params.get('user', [''])[0]
    keyword = params.get('q', [''])[0].strip()
    if user_id:
        conditions.append('c.user_id = ?')
        values.append(user_id)
    if keyword:
        pattern = '%' + keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        escaped_keyword = json.dumps(keyword, ensure_ascii=True)[1:-1]
        escaped_pattern = '%' + escaped_keyword.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        has_messages = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_message'"
        ).fetchone()
        clause = ("(c.title LIKE ? ESCAPE '\\' OR c.chat LIKE ? ESCAPE '\\' "
                  "OR c.chat LIKE ? ESCAPE '\\'")
        values.extend([pattern, pattern, escaped_pattern])
        if has_messages:
            clause += (" OR EXISTS (SELECT 1 FROM chat_message m WHERE m.chat_id = c.id "
                       "AND (m.content LIKE ? ESCAPE '\\' OR m.content LIKE ? ESCAPE '\\'))")
            values.extend([pattern, escaped_pattern])
        conditions.append(clause + ')')
    if params.get('from', [''])[0]:
        conditions.append('c.created_at >= ?')
        values.append(date_bound(params['from'][0]))
    if params.get('to', [''])[0]:
        conditions.append('c.created_at < ?')
        values.append(date_bound(params['to'][0], end=True))
    archived = params.get('archived', ['all'])[0]
    if archived in ('yes', 'no'):
        conditions.append('COALESCE(c.archived, 0) = ?')
        values.append(1 if archived == 'yes' else 0)
    elif archived != 'all':
        raise ValueError('归档筛选值无效')
    try:
        page = int(params.get('page', ['1'])[0])
    except ValueError as exc:
        raise ValueError('页码必须是正整数') from exc
    if page < 1:
        raise ValueError('页码必须是正整数')
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    joins = ' FROM chat c LEFT JOIN "user" u ON u.id = c.user_id'
    total = conn.execute('SELECT COUNT(*)' + joins + where, values).fetchone()[0]
    rows = conn.execute(
        'SELECT c.id, c.user_id, u.email, u.name, c.title, c.created_at, '
        'c.updated_at, c.archived' + joins + where +
        ' ORDER BY c.updated_at DESC, c.id LIMIT ? OFFSET ?',
        values + [PAGE_SIZE, (page - 1) * PAGE_SIZE],
    ).fetchall()
    return {'total': total, 'page': page, 'page_size': PAGE_SIZE,
            'chats': [dict(row) for row in rows]}


def make_handler(db_path, access_key):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, data, content_type='application/json; charset=utf-8'):
            body = data.encode('utf-8') if isinstance(data, str) else json.dumps(
                data, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            authorization = self.headers.get('Authorization', '')
            try:
                scheme, encoded = authorization.split(' ', 1)
                credentials = base64.b64decode(encoded, validate=True).decode('utf-8')
                username, password = credentials.split(':', 1)
                authenticated = (scheme.lower() == 'basic' and username == 'viewer'
                                 and hmac.compare_digest(password, access_key))
            except (ValueError, UnicodeDecodeError, binascii.Error):
                authenticated = False
            if not authenticated:
                self.send_response(401)
                self.send_header('WWW-Authenticate', 'Basic realm="Open WebUI chat viewer", charset="UTF-8"')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            url = urlsplit(self.path)
            params = parse_qs(url.query, keep_blank_values=True)
            if url.path == '/':
                self.respond(200, PAGE.read_bytes().decode('utf-8'), 'text/html; charset=utf-8')
                return
            if url.path == '/viewer.js':
                self.respond(200, SCRIPT.read_bytes().decode('utf-8'), 'text/javascript; charset=utf-8')
                return
            if url.path != '/api/users' and url.path != '/api/chats' and url.path != '/api/chat':
                self.respond(404, {'error': '页面不存在'})
                return
            try:
                with sqlite3.connect(f'{db_path.as_uri()}?mode=ro', uri=True) as conn:
                    conn.row_factory = sqlite3.Row
                    if url.path == '/api/users':
                        rows = conn.execute('SELECT id, email, name, role FROM "user" ORDER BY email')
                        self.respond(200, [dict(row) for row in rows])
                    elif url.path == '/api/chats':
                        self.respond(200, query_chats(conn, params))
                    else:
                        chat_id = params.get('id', [''])[0]
                        if not chat_id:
                            raise ValueError('缺少聊天 ID')
                        row = conn.execute(
                            'SELECT c.id, c.user_id, u.email, u.name, c.title, c.chat, '
                            'c.created_at, c.updated_at FROM chat c '
                            'LEFT JOIN "user" u ON u.id = c.user_id WHERE c.id = ?',
                            (chat_id,),
                        ).fetchone()
                        if row is None:
                            self.respond(404, {'error': '聊天不存在'})
                        else:
                            data = dict(row)
                            data['chat'] = parse_json(data['chat'])
                            data['messages'] = messages_for(conn, row)
                            self.respond(200, data)
            except ValueError as exc:
                self.respond(400, {'error': str(exc)})
            except sqlite3.Error as exc:
                self.respond(500, {'error': f'数据库读取失败: {exc}'})

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True, help='webui.db 的路径')
    parser.add_argument('--access-key', default=os.getenv('WEBUI_CHAT_VIEWER_KEY'),
                        help='访问密钥；也可设置 WEBUI_CHAT_VIEWER_KEY 环境变量')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址，默认 127.0.0.1；可设为 0.0.0.0')
    parser.add_argument('--port', type=int, default=8765, help='本地端口，默认 8765')
    args = parser.parse_args()
    if not args.access_key:
        parser.error('必须通过 --access-key 或 WEBUI_CHAT_VIEWER_KEY 设置访问密钥')
    db_path = args.db.resolve()
    if not db_path.is_file():
        parser.error(f'数据库文件不存在: {db_path}')
    try:
        with sqlite3.connect(f'{db_path.as_uri()}?mode=ro', uri=True) as conn:
            conn.execute('SELECT 1 FROM "user" LIMIT 1')
            conn.execute('SELECT 1 FROM chat LIMIT 1')
    except sqlite3.Error as exc:
        parser.error(f'无法读取 Open WebUI 数据库: {exc}')
    server = ThreadingHTTPServer((args.host, args.port), make_handler(db_path, args.access_key))
    display_host = '127.0.0.1' if args.host == '0.0.0.0' else args.host
    print(f'聊天浏览器: http://{display_host}:{server.server_port}/')
    print('按 Ctrl+C 停止。数据库以只读模式打开。')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
