import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os
import hashlib
from datetime import datetime

# ── 모니터링 대상 딜 페이지 ──────────────────────────────────────
DEAL_PAGES = [
    ("Avianca LifeMiles",               "https://onemileatatime.com/deals/buy-avianca-lifemiles/"),
    ("American AAdvantage",             "https://onemileatatime.com/deals/buy-american-aadvantage-miles/"),
    ("Qatar Airways Privilege Club",    "https://onemileatatime.com/deals/buy-qatar-airways-privilege-club-avios/"),
    ("Finnair Plus",                    "https://onemileatatime.com/deals/buy-finnair-plus-avios/"),
    ("Copa ConnectMiles",               "https://onemileatatime.com/buy-copa-miles/"),
    ("AirFrance/KLM Flying Blue",       "https://onemileatatime.com/deals/buy-air-france-klm-flying-blue-miles/"),
    ("JetBlue TrueBlue",               "https://onemileatatime.com/deals/buy-jetblue-trueblue-points/"),
    ("British Airways Club",            "https://onemileatatime.com/deals/buy-british-airways-club-avios/"),
    ("United MileagePlus",              "https://onemileatatime.com/deals/buy-united-mileageplus-miles/"),
    ("Etihad Guest",                    "https://onemileatatime.com/deals/buy-etihad-guest-miles/"),
    ("Emirates Skywards",               "https://onemileatatime.com/deals/buy-emirates-skywards-miles/"),
    ("Iberia Plus",                     "https://onemileatatime.com/deals/buy-iberia-plus-avios/"),
    ("Air Canada Aeroplan",             "https://onemileatatime.com/deals/buy-air-canada-aeroplan-points/"),
    ("Alaska Atmos Rewards",            "https://onemileatatime.com/deals/buy-alaska-atmos-rewards-points/"),
    ("Virgin Atlantic Flying Club",     "https://onemileatatime.com/deals/buy-virgin-atlantic-flying-club-points/"),
]

STATE_FILE = "last_state.json"

GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL      = os.environ.get("NOTIFY_EMAIL", GMAIL_USER)

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ── 테이블 크롤링 ─────────────────────────────────────────────────
def fetch_deal_table(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")

    # main-deal-content 컨테이너 안의 테이블 우선 탐색
    container = soup.find("div", class_=lambda c: c and all(
        x in c.split() for x in ["col-lg-6", "main-deal-content"]
    ))

    table = None
    if container:
        table = container.find("table")

    # fallback: 페이지 내 첫 번째 테이블
    if not table:
        table = soup.find("table")

    if not table:
        return None

    rows = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows


def rows_to_text(rows):
    return "\n".join(" | ".join(row) for row in rows)


def get_hash(text):
    return hashlib.md5(text.encode()).hexdigest()


# ── 상태 파일 ─────────────────────────────────────────────────────
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── 이메일 발송 ───────────────────────────────────────────────────
def send_email(changed_items):
    """changed_items: [(title, url, table_text), ...]"""

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    count = len(changed_items)

    subject = f"✈️ [마일리지 딜 알림] {count}개 페이지 업데이트 감지 ({now_str})"

    # ── Plain text ──
    plain_lines = [f"마일리지 딜 변경 감지 — {now_str}\n"]
    for title, url, text in changed_items:
        plain_lines.append(f"{'='*50}")
        plain_lines.append(f"▶ {title}")
        plain_lines.append(url)
        plain_lines.append("")
        plain_lines.append(text)
        plain_lines.append("")
    plain_body = "\n".join(plain_lines)

    # ── HTML ──
    cards_html = ""
    for title, url, text in changed_items:
        cards_html += f"""
        <div style="margin-bottom:28px;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
          <div style="background:#1a73e8;padding:12px 16px;">
            <span style="color:#fff;font-size:16px;font-weight:bold;">✈️ {title}</span>
          </div>
          <div style="padding:16px;">
            <pre style="background:#f8f8f8;padding:12px;border-radius:6px;
                        font-size:13px;line-height:1.6;overflow-x:auto;
                        white-space:pre-wrap;word-break:break-word;">{text}</pre>
            <a href="{url}" style="display:inline-block;margin-top:10px;
               padding:8px 16px;background:#1a73e8;color:#fff;
               text-decoration:none;border-radius:4px;font-size:13px;">
              👉 원문 보러 가기
            </a>
          </div>
        </div>
        """

    html_body = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;">
      <h2 style="color:#1a73e8;">✈️ 마일리지 딜 업데이트 알림</h2>
      <p style="color:#555;">확인 시각: <strong>{now_str}</strong> &nbsp;|&nbsp;
         변경된 페이지: <strong>{count}개</strong></p>
      <hr style="margin:16px 0;">
      {cards_html}
      <p style="color:#aaa;font-size:12px;margin-top:32px;">
        이 메일은 GitHub Actions 자동 모니터링 스크립트가 발송했습니다.
      </p>
    </body></html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body,  "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"✅ 이메일 발송 완료 ({count}개 변경) → {NOTIFY_EMAIL}")


# ── 메인 ─────────────────────────────────────────────────────────
def main():
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"🔍 점검 시작: {now_str}\n")

    state = load_state()
    changed_items = []

    for title, url in DEAL_PAGES:
        print(f"  ▶ {title} ...", end=" ")
        try:
            rows = fetch_deal_table(url)
            if not rows:
                print("⚠️  테이블 없음, 건너뜀")
                continue

            current_text = rows_to_text(rows)
            current_hash = get_hash(current_text)
            last_hash    = state.get(url, {}).get("hash", "")

            if current_hash != last_hash:
                print("🚨 변경 감지!")
                changed_items.append((title, url, current_text))
                state[url] = {"hash": current_hash, "updated_at": now_str}
            else:
                print("✅ 변동 없음")

        except Exception as e:
            print(f"❌ 오류: {e}")

    print()

    if changed_items:
        print(f"📧 변경된 페이지 {len(changed_items)}개 → 이메일 발송 중...")
        send_email(changed_items)
    else:
        print("📭 변동 없음 — 이메일 발송 안 함")

    save_state(state)
    print("\n✅ 점검 완료")


if __name__ == "__main__":
    main()
