import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import os
import hashlib
import difflib
from datetime import datetime

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
GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL       = os.environ.get("NOTIFY_EMAIL", GMAIL_USER)
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_deal_table(url):
    res = requests.get(url, headers=HEADERS, timeout=15)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    container = soup.find("div", class_=lambda c: c and all(
        x in c.split() for x in ["col-lg-6", "main-deal-content"]
    ))
    table = container.find("table") if container else None
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


def make_diff(old_text, new_text):
    """추가(+)/삭제(-) 줄만 반환. 변경 없으면 빈 문자열."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff_lines = []
    for line in difflib.unified_diff(old_lines, new_lines, lineterm="", n=0):
        # 헤더(@@ 줄, --- +++줄) 제외하고 실제 변경 줄만
        if line.startswith(("---", "+++")):
            continue
        if line.startswith("@@"):
            diff_lines.append("")   # 구분용 빈 줄
            continue
        diff_lines.append(line)
    return "\n".join(diff_lines).strip()


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def send_email(changed_items):
    """changed_items: [(title, url, diff_text), ...]"""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    count = len(changed_items)
    subject = f"✈️ [마일리지 딜 알림] {count}개 변경 감지 ({now_str})"

    plain_lines = [f"마일리지 딜 변경 감지 — {now_str}\n"]
    for title, url, diff_text in changed_items:
        plain_lines += [f"{'='*50}", f"▶ {title}", url, "", diff_text, ""]
    plain_body = "\n".join(plain_lines)

    cards_html = ""
    for title, url, diff_text in changed_items:
        # diff 줄별로 색상 입히기
        colored_lines = []
        for line in diff_text.splitlines():
            if line.startswith("+"):
                colored_lines.append(
                    f'<span style="background:#e6f4ea;color:#137333;display:block">{line}</span>'
                )
            elif line.startswith("-"):
                colored_lines.append(
                    f'<span style="background:#fce8e6;color:#c5221f;display:block">{line}</span>'
                )
            else:
                colored_lines.append(f'<span style="display:block">{line}</span>')
        colored_diff = "\n".join(colored_lines)

        cards_html += f"""
        <div style="margin-bottom:28px;border:1px solid #e0e0e0;border-radius:8px;overflow:hidden;">
          <div style="background:#1a73e8;padding:12px 16px;">
            <span style="color:#fff;font-size:16px;font-weight:bold;">✈️ {title}</span>
          </div>
          <div style="padding:16px;">
            <div style="background:#f8f8f8;padding:12px;border-radius:6px;
                        font-family:monospace;font-size:13px;line-height:1.6;
                        overflow-x:auto;">
              {colored_diff}
            </div>
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
      <p style="color:#888;font-size:12px;">🟢 초록 = 추가된 내용 &nbsp; 🔴 빨강 = 삭제된 내용</p>
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
            last_text    = state.get(url, {}).get("text", "")  # ← 이전 텍스트 꺼내기

            if current_hash != last_hash:
                print("🚨 변경 감지!")
                if last_text:
                    diff_text = make_diff(last_text, current_text)
                else:
                    # 첫 실행이면 전체 내용 표시
                    diff_text = "\n".join(f"+ {line}" for line in current_text.splitlines())

                changed_items.append((title, url, diff_text))
                state[url] = {
                    "hash": current_hash,
                    "text": current_text,   # ← 이번 텍스트 저장
                    "updated_at": now_str,
                }
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
