import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os
import hashlib
from datetime import datetime

URL = "https://onemileatatime.com/deals/buy-avianca-lifemiles/"
STATE_FILE = "last_state.json"

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", GMAIL_USER)


def fetch_deal_table():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    res = requests.get(URL, headers=headers, timeout=15)
    res.raise_for_status()

    soup = BeautifulSoup(res.text, "html.parser")

    # col-lg-6 main-deal-content pt-4 pb-4 안의 표 찾기
    container = soup.find("div", class_=lambda c: c and all(
        x in c.split() for x in ["col-lg-6", "main-deal-content"]
    ))

    if not container:
        # fallback: 페이지 내 모든 표에서 Deal History 찾기
        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if rows:
                container = table.parent
                break

    if not container:
        raise ValueError("딜 테이블을 찾을 수 없습니다.")

    table = container.find("table") if container.name != "table" else container
    if not table:
        raise ValueError("테이블 요소를 찾을 수 없습니다.")

    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)

    return rows


def rows_to_text(rows):
    lines = []
    for row in rows:
        lines.append(" | ".join(row))
    return "\n".join(lines)


def get_hash(text):
    return hashlib.md5(text.encode()).hexdigest()


def load_last_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def send_email(subject, body):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL

    html = f"""
    <html><body>
    <h2 style="color:#1a73e8;">✈️ LifeMiles 딜 변경 감지!</h2>
    <p style="color:#555;">변경 시각: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</p>
    <hr>
    <h3>📋 현재 딜 테이블</h3>
    <pre style="background:#f4f4f4;padding:12px;border-radius:6px;font-size:14px;">{body}</pre>
    <hr>
    <p><a href="{URL}">👉 원문 보러 가기</a></p>
    </body></html>
    """

    msg.attach(MIMEText(body, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"✅ 이메일 발송 완료 → {NOTIFY_EMAIL}")


def main():
    print(f"🔍 페이지 확인 중... {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

    rows = fetch_deal_table()
    current_text = rows_to_text(rows)
    current_hash = get_hash(current_text)

    print(f"현재 테이블:\n{current_text}\n")

    last_state = load_last_state()
    last_hash = last_state.get("hash", "")

    if current_hash != last_hash:
        print("🚨 변경 감지! 이메일 발송 중...")
        subject = "✈️ [LifeMiles] 딜 테이블 업데이트됨!"
        send_email(subject, current_text)
        save_state({"hash": current_hash, "last_seen": current_text,
                    "updated_at": datetime.utcnow().isoformat()})
    else:
        print("✅ 변경 없음.")


if __name__ == "__main__":
    main()
