import http.server
import socketserver
import urllib.parse
import json
import sqlite3
import os
import sys
from datetime import datetime

DB_FILE = os.environ.get('DB_FILE', 'agency_qr.db')

def get_db():
    global DB_FILE
    targets = [DB_FILE] if DB_FILE != 'agency_qr.db' else ['agency_qr.db', '/tmp/agency_qr.db']
    for target in targets:
        try:
            conn = sqlite3.connect(target)
            conn.row_factory = sqlite3.Row
            conn.execute('CREATE TABLE IF NOT EXISTS _test_write (id INT)')
            DB_FILE = target
            return conn
        except sqlite3.OperationalError:
            continue
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    DB_FILE = ':memory:'
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS agencies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        industry TEXT,
        color TEXT DEFAULT '#4F46E5',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS qr_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agency_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        campaign TEXT,
        slug TEXT UNIQUE NOT NULL,
        target_url TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (agency_id) REFERENCES agencies(id)
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scan_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        qr_id INTEGER NOT NULL,
        scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        user_agent TEXT,
        ip_address TEXT,
        device_type TEXT,
        FOREIGN KEY (qr_id) REFERENCES qr_codes(id)
    )
    ''')
    conn.commit()

    cursor.execute('SELECT COUNT(*) as cnt FROM agencies')
    if cursor.fetchone()['cnt'] == 0:
        cursor.execute("INSERT INTO agencies (name, industry, color) VALUES ('Alpha Marketing Agency', 'Marketing & Quảng cáo', '#4F46E5')")
        cursor.execute("INSERT INTO agencies (name, industry, color) VALUES ('Saigon Gourmet F&B', 'Nhà hàng & Dịch vụ ẩm thực', '#059669')")
        cursor.execute("INSERT INTO agencies (name, industry, color) VALUES ('GreenLand Real Estate', 'Bất động sản & Sự kiện', '#D97706')")
        conn.commit()

        qrs = [
            (1, 'Standee Hội nghị Chuyển đổi số 2026', 'Event Tech', 'tech-summit-2026', 'https://google.com/search?q=tech+summit+2026', 1),
            (1, 'Danh thiếp thông minh - CEO Nam Trần', 'Personal Branding', 'nam-tran-card', 'https://linkedin.com', 1),
            (2, 'Menu QR Bàn 01-10 - Chi nhánh Quận 1', 'F&B In-Store', 'menu-ban-q1', 'https://example.com/menu-q1', 1),
            (2, 'Vòng quay may mắn Check-in nhận quà', 'Loyalty Campaign', 'checkin-tang-qua', 'https://example.com/vong-quay', 1),
            (3, 'Brochure Dự án EcoPark Luxury Villa', 'Project Launch', 'ecopark-villa', 'https://example.com/ecopark', 1),
            (3, 'Thư mời VIP Lễ mở bán Đợt 1', 'VIP Invitation', 'vip-moban-d1', 'https://example.com/vip-invitation', 1),
        ]
        cursor.executemany('INSERT INTO qr_codes (agency_id, title, campaign, slug, target_url, is_active) VALUES (?, ?, ?, ?, ?, ?)', qrs)
        conn.commit()

        logs = [
            (1, '2026-10-12 10:15:00', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)', '113.161.45.10', 'Mobile (iOS)'),
            (1, '2026-10-12 11:20:00', 'Mozilla/5.0 (Linux; Android 14; SM-S918B)', '14.162.88.22', 'Mobile (Android)'),
            (1, '2026-10-13 09:05:00', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)', '118.69.182.1', 'Desktop (Mac)'),
            (2, '2026-10-13 12:30:00', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_1)', '27.72.60.15', 'Mobile (iOS)'),
            (2, '2026-10-13 12:45:00', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_2)', '171.244.35.4', 'Mobile (iOS)'),
            (2, '2026-10-13 13:10:00', 'Mozilla/5.0 (Linux; Android 14)', '125.235.209.11', 'Mobile (Android)'),
            (3, '2026-10-13 14:00:00', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', '42.119.143.50', 'Desktop (Windows)'),
        ]
        cursor.executemany('INSERT INTO scan_logs (qr_id, scanned_at, user_agent, ip_address, device_type) VALUES (?, ?, ?, ?, ?)', logs)
        conn.commit()
    conn.close()

class QRRequestHandler(http.server.BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path.startswith('/r/'):
            slug = path[3:].strip('/')
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('SELECT id, target_url, is_active FROM qr_codes WHERE slug = ?', (slug,))
            row = cursor.fetchone()
            if row and row['is_active']:
                ua = self.headers.get('User-Agent', '')
                device = 'Desktop'
                if 'iPhone' in ua or 'iPad' in ua:
                    device = 'Mobile (iOS)'
                elif 'Android' in ua:
                    device = 'Mobile (Android)'
                elif 'Mobile' in ua:
                    device = 'Mobile'
                ip = self.client_address[0]
                cursor.execute('INSERT INTO scan_logs (qr_id, user_agent, ip_address, device_type) VALUES (?, ?, ?, ?)',
                               (row['id'], ua[:250], ip, device))
                conn.commit()
                target_url = row['target_url']
                conn.close()
                self.send_response(302)
                self.send_header('Location', target_url)
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.end_headers()
                return
            else:
                conn.close()
                self.send_response(404)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write('<h1>404 - Mã QR không tồn tại!</h1>'.encode('utf-8'))
                return

        if path == '/' or path == '/index.html':
            template_path = 'index.html' if os.path.exists('index.html') else os.path.join(os.path.dirname(__file__), 'templates', 'index.html')
            if os.path.exists(template_path):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                with open(template_path, 'rb') as f:
                    self.wfile.write(f.read())
                return

        if path == '/api/agencies':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT a.id, a.name, a.industry, a.color, a.created_at,
                       COUNT(DISTINCT q.id) as qr_count,
                       COUNT(s.id) as total_scans
                FROM agencies a
                LEFT JOIN qr_codes q ON a.id = q.agency_id
                LEFT JOIN scan_logs s ON q.id = s.qr_id
                GROUP BY a.id
                ORDER BY a.id ASC
            ''')
            agencies = [dict(row) for row in cursor.fetchall()]
            conn.close()
            self._send_json(agencies)
            return

        if path == '/api/qrs':
            agency_id = query.get('agency_id', [None])[0]
            conn = get_db()
            cursor = conn.cursor()
            if agency_id:
                cursor.execute('''
                    SELECT q.id, q.agency_id, q.title, q.campaign, q.slug, q.target_url, q.is_active, q.created_at,
                           COUNT(s.id) as scan_count
                    FROM qr_codes q
                    LEFT JOIN scan_logs s ON q.id = s.qr_id
                    WHERE q.agency_id = ?
                    GROUP BY q.id
                    ORDER BY q.id DESC
                ''', (agency_id,))
            else:
                cursor.execute('''
                    SELECT q.id, q.agency_id, q.title, q.campaign, q.slug, q.target_url, q.is_active, q.created_at,
                           COUNT(s.id) as scan_count
                    FROM qr_codes q
                    LEFT JOIN scan_logs s ON q.id = s.qr_id
                    GROUP BY q.id
                    ORDER BY q.id DESC
                ''')
            qrs = [dict(row) for row in cursor.fetchall()]
            conn.close()
            self._send_json(qrs)
            return

        if path == '/api/logs':
            qr_id = query.get('qr_id', [None])[0]
            conn = get_db()
            cursor = conn.cursor()
            if qr_id:
                cursor.execute('''
                    SELECT id, scanned_at, ip_address, device_type, user_agent
                    FROM scan_logs
                    WHERE qr_id = ?
                    ORDER BY id DESC LIMIT 50
                ''', (qr_id,))
            else:
                cursor.execute('''
                    SELECT s.id, s.scanned_at, s.ip_address, s.device_type, q.title, q.slug
                    FROM scan_logs s
                    JOIN qr_codes q ON s.qr_id = q.id
                    ORDER BY s.id DESC LIMIT 50
                ''')
            logs = [dict(row) for row in cursor.fetchall()]
            conn.close()
            self._send_json(logs)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = self.path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8') if length > 0 else '{}'
        data = json.loads(body) if body else {}

        if path == '/api/agencies':
            name = data.get('name', '').strip()
            industry = data.get('industry', '').strip()
            color = data.get('color', '#4F46E5')
            if not name:
                self._send_json({'error': 'Tên agency không được để trống'}, 400)
                return
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO agencies (name, industry, color) VALUES (?, ?, ?)', (name, industry, color))
            conn.commit()
            new_id = cursor.lastrowid
            conn.close()
            self._send_json({'success': True, 'id': new_id, 'name': name}, 201)
            return

        if path == '/api/qrs':
            agency_id = data.get('agency_id')
            title = data.get('title', '').strip()
            campaign = data.get('campaign', 'General').strip()
            slug = data.get('slug', '').strip().lower()
            target_url = data.get('target_url', '').strip()

            if not agency_id or not title or not target_url or not slug:
                self._send_json({'error': 'Thiếu thông tin bắt buộc'}, 400)
                return

            if not (target_url.startswith('http://') or target_url.startswith('https://')):
                target_url = 'https://' + target_url

            conn = get_db()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    'INSERT INTO qr_codes (agency_id, title, campaign, slug, target_url) VALUES (?, ?, ?, ?, ?)',
                    (agency_id, title, campaign, slug, target_url)
                )
                conn.commit()
                qr_id = cursor.lastrowid
                conn.close()
                self._send_json({'success': True, 'id': qr_id, 'slug': slug, 'redirect_url': f'/r/{slug}'}, 201)
            except sqlite3.IntegrityError:
                conn.close()
                self._send_json({'error': 'Mã Slug đã tồn tại'}, 409)
            return

        if path.startswith('/api/qrs/') and path.endswith('/update'):
            slug = path.split('/')[3]
            target_url = data.get('target_url', '').strip()
            is_active = data.get('is_active', 1)
            title = data.get('title', None)

            if not target_url:
                self._send_json({'error': 'URL đích không được để trống'}, 400)
                return

            if not (target_url.startswith('http://') or target_url.startswith('https://')):
                target_url = 'https://' + target_url

            conn = get_db()
            cursor = conn.cursor()
            if title:
                cursor.execute('UPDATE qr_codes SET target_url = ?, is_active = ?, title = ? WHERE slug = ?', (target_url, is_active, title, slug))
            else:
                cursor.execute('UPDATE qr_codes SET target_url = ?, is_active = ? WHERE slug = ?', (target_url, is_active, slug))
            conn.commit()
            conn.close()
            self._send_json({'success': True, 'slug': slug, 'new_target_url': target_url})
            return

        self.send_response(404)
        self.end_headers()

def run(port=8000):
    init_db()
    server_address = ('', port)
    httpd = socketserver.TCPServer(server_address, QRRequestHandler)
    print(f'Server running at port {port}')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()

if __name__ == '__main__':
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    elif 'PORT' in os.environ and os.environ['PORT'].isdigit():
        port = int(os.environ['PORT'])
    run(port)
