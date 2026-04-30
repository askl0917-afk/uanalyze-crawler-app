import os
import re
import io
import json
import time
import zipfile
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import streamlit as st
import streamlit.components.v1 as components

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except Exception:
    sync_playwright = None
    PlaywrightTimeoutError = Exception


APP_TITLE = "UAnalyze 產業情報小助理爬蟲"
LOGIN_URL_DEFAULT = "https://pro.uanalyze.com.tw/login-page"
DASHBOARD_URL_DEFAULT = "https://pro.uanalyze.com.tw/lab/dashboard/41873"

DEFAULT_TOPICS = [
    "近況發展",
    "產業趨勢",
    "產品線分析",
    "長短期展望",
    "供需分析",
    "觀察重點",
    "利多因素",
    "利空因素",
    "接單狀況",
    "資本支出",
    "新產品",
    "時間表",
    "相關公司",
    "同業競爭",
    "護城河分析",
    "併購分析",
    "重要數字",
    "公司概覽",
    "銷售地區",
    "名詞解釋",
]

OUT_DIR = Path("/tmp/uanalyze_crawler_outputs")
OUT_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------
# 基礎工具
# -----------------------------

def normalize_stock_code(raw: str) -> str:
    """
    只取股票代號。
    例如：
    - 3030_德律 -> 3030
    - 3030 德律 -> 3030
    - 德律3030 -> 3030
    """
    raw = (raw or "").strip()
    m = re.search(r"(\d{4,6})", raw)
    return m.group(1) if m else raw


def safe_filename(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|]+", "_", str(s))
    s = re.sub(r"\s+", "_", s).strip("_")
    return s[:120] or "uanalyze"


def run_cmd(cmd: List[str], timeout: int = 180) -> Tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return 999, str(e)


def ensure_playwright_chromium() -> str:
    """
    Streamlit Cloud 上第一次跑時，可能需要安裝 Chromium。
    這裡做一次性檢查，避免每次重裝。
    """
    marker = Path("/tmp/uanalyze_playwright_chromium_ready")
    if marker.exists():
        return "Playwright Chromium 已準備完成。"

    if sync_playwright is None:
        return "Playwright 尚未安裝，請確認 requirements.txt 有 playwright。"

    # 安裝 chromium。若已安裝，這行通常很快。
    code, out = run_cmd(["python", "-m", "playwright", "install", "chromium"], timeout=240)
    if code == 0:
        marker.write_text(datetime.now().isoformat(), encoding="utf-8")
        return "Playwright Chromium 安裝 / 檢查完成。"
    return f"Playwright Chromium 安裝可能失敗：\n{out[-2000:]}"


def text_contains_login_fields(text: str) -> bool:
    keywords = ["Facebook 登入", "Google 登入", "Apple 登入", "忘記密碼", "無法登入", "Email", "密碼"]
    return sum(k in text for k in keywords) >= 3


def strip_repeated_noise(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)

    # 移除常見頁尾 / cookie 長文，避免每個欄位重複塞爆
    cut_patterns = [
        "EPS法人預估",
        "優分析 UAnalyze 特別聲明",
        "服務條款|免責聲明|隱私權政策",
        "本網站使用 Cookie 技術",
    ]
    # 注意：這個函式不一定要砍到 EPS；主抽取函式會更精準切。
    return text.strip()


def detect_current_stock(text: str) -> Tuple[str, str]:
    """
    回傳 (stock_code, stock_name)。抓不到就回空字串。
    """
    text = text or ""

    code = ""
    name = ""

    patterns = [
        r"股票代碼[:：]\s*\n?\s*(\d{4,6})",
        r"股票代碼\s*\n?\s*(\d{4,6})",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            code = m.group(1)
            break

    name_patterns = [
        r"股票名稱[:：]\s*\n?\s*([^\n\r]+)",
        r"股票名稱\s*\n?\s*([^\n\r]+)",
    ]
    for pat in name_patterns:
        m = re.search(pat, text)
        if m:
            cand = m.group(1).strip()
            if cand and len(cand) <= 20:
                name = cand
                break

    # 後備：常見格式「台泥 \n 1101 \n 24.50%」
    if not code:
        m = re.search(r"\n([^\n]{1,20})\n(\d{4,6})\n", "\n" + text)
        if m:
            name, code = m.group(1).strip(), m.group(2).strip()

    return code, name


def infer_company_from_text(text: str) -> str:
    code, name = detect_current_stock(text)
    if code and name:
        return f"{code}_{name}"
    if code:
        return code
    return ""


def make_copy_button(markdown_text: str, button_label: str = "📋 一鍵複製全部爬蟲結果"):
    """
    Streamlit 原生按鈕不能直接寫入手機剪貼簿，所以用小段 HTML/JS。
    """
    payload = json.dumps(markdown_text)
    components.html(
        f"""
        <div style="margin: 8px 0 18px 0;">
          <button id="copy_btn" style="
            width:100%;
            background:#ff9800;
            color:#111;
            border:none;
            border-radius:12px;
            padding:14px 16px;
            font-size:18px;
            font-weight:700;
            cursor:pointer;">
            {button_label}
          </button>
          <div id="copy_msg" style="color:#41d37e; font-size:15px; margin-top:8px;"></div>
        </div>
        <script>
        const text = {payload};
        const btn = document.getElementById("copy_btn");
        const msg = document.getElementById("copy_msg");
        btn.onclick = async () => {{
            try {{
                await navigator.clipboard.writeText(text);
                msg.innerText = "已複製到剪貼簿";
            }} catch (e) {{
                const ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand("copy");
                document.body.removeChild(ta);
                msg.innerText = "已複製到剪貼簿";
            }}
        }};
        </script>
        """,
        height=95,
    )


def make_zip_bytes(files: Dict[str, bytes]) -> bytes:
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return bio.getvalue()


# -----------------------------
# Playwright 互動工具
# -----------------------------

def click_cookie_if_any(page):
    texts = ["我知道了", "接受", "同意", "OK"]
    for t in texts:
        try:
            loc = page.get_by_text(t, exact=True)
            if loc.count() > 0:
                loc.last.click(timeout=1500)
                page.wait_for_timeout(500)
                return True
        except Exception:
            pass
    return False


def fill_first_visible(page, selectors: List[str], value: str) -> bool:
    for sel in selectors:
        try:
            loc = page.locator(sel)
            count = loc.count()
            for i in range(min(count, 5)):
                item = loc.nth(i)
                if item.is_visible(timeout=800):
                    item.click(timeout=1500)
                    item.fill(value, timeout=3000)
                    return True
        except Exception:
            continue
    return False


def click_text_any(page, texts: List[str], exact: bool = True, timeout: int = 2500) -> Tuple[bool, str]:
    for t in texts:
        try:
            loc = page.get_by_text(t, exact=exact)
            count = loc.count()
            if count > 0:
                # 通常後面的按鈕比較接近內容區
                loc.last.click(timeout=timeout)
                return True, f"clicked text: {t}"
        except Exception:
            continue
    return False, "not clicked"


def goto_with_retry(page, url: str, timeout_ms: int = 120000):
    for i in range(2):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except Exception:
            if i == 1:
                raise
            page.wait_for_timeout(3000)


def login_email_password(page, login_url: str, email: str, password: str, login_wait_sec: int) -> str:
    """
    使用 Email + 密碼登入。
    如果本來就已登入，會直接略過。
    """
    goto_with_retry(page, login_url)
    page.wait_for_timeout(2500)
    click_cookie_if_any(page)

    initial_text = page.locator("body").inner_text(timeout=15000)
    if not text_contains_login_fields(initial_text):
        return "頁面看起來已經不是登入頁，略過登入。"

    email_selectors = [
        "input[type='email']",
        "input[name*='email' i]",
        "input[placeholder*='Email' i]",
        "input[placeholder*='email' i]",
        "input[autocomplete='username']",
        "input:not([type='password'])",
    ]
    pass_selectors = [
        "input[type='password']",
        "input[name*='password' i]",
        "input[placeholder*='密碼']",
        "input[placeholder*='Password' i]",
        "input[autocomplete='current-password']",
    ]

    email_ok = fill_first_visible(page, email_selectors, email)
    pass_ok = fill_first_visible(page, pass_selectors, password)

    if not email_ok or not pass_ok:
        return f"沒有成功找到 Email/密碼輸入框。email_ok={email_ok}, pass_ok={pass_ok}"

    ok, msg = click_text_any(page, ["登入", "Sign in", "Login", "Log in"], exact=True, timeout=4000)
    if not ok:
        # 最後手段：按 Enter
        try:
            page.keyboard.press("Enter")
            msg = "pressed Enter for login"
        except Exception:
            msg = "login button not found"

    page.wait_for_timeout(max(3, login_wait_sec) * 1000)
    click_cookie_if_any(page)
    return f"Email 密碼登入流程完成：{msg}"


def enter_huba_quick_view(page) -> str:
    """
    進入虎八速覽。
    """
    status = []
    for text in ["虎八速覽", "我的訂閱", "優分析產業資料庫"]:
        try:
            loc = page.get_by_text(text, exact=True)
            if loc.count() > 0:
                if text == "虎八速覽":
                    loc.last.click(timeout=3000)
                    page.wait_for_timeout(2500)
                    status.append("clicked 虎八速覽")
                    break
        except Exception:
            pass

    # 如果已經在虎八速覽，不強迫點
    body = page.locator("body").inner_text(timeout=15000)
    if "虎八速覽" in body:
        status.append("頁面包含虎八速覽")
    return "；".join(status) or "未特別點擊虎八速覽，但繼續執行"


def try_click_stock_from_left_list(page, stock_code: str, wait_sec: int) -> Tuple[bool, str]:
    """
    若左側清單已存在該股票代號，直接點擊。
    """
    attempts = [
        f"text=/{stock_code}/",
        f"text={stock_code}",
    ]
    for sel in attempts:
        try:
            loc = page.locator(sel)
            count = loc.count()
            if count > 0:
                # 避免點到輸入框或文字段落，先點靠前的可見元素
                for i in range(min(count, 10)):
                    item = loc.nth(i)
                    try:
                        if item.is_visible(timeout=500):
                            item.click(timeout=2500)
                            page.wait_for_timeout(wait_sec * 1000)
                            return True, f"clicked stock text/list item containing {stock_code}"
                    except Exception:
                        continue
        except Exception:
            continue
    return False, f"left list did not expose {stock_code}"


def set_input_value_by_js(page, selector: str, value: str) -> bool:
    """
    使用原生 setter + input/change 事件，對 React/Vue 比直接 fill 更穩。
    """
    try:
        return bool(page.evaluate(
            """
            ({selector, value}) => {
              const el = document.querySelector(selector);
              if (!el) return false;
              const proto = Object.getPrototypeOf(el);
              const desc = Object.getOwnPropertyDescriptor(proto, "value");
              if (desc && desc.set) desc.set.call(el, value);
              else el.value = value;
              el.dispatchEvent(new Event("input", {bubbles:true}));
              el.dispatchEvent(new Event("change", {bubbles:true}));
              return true;
            }
            """,
            {"selector": selector, "value": value}
        ))
    except Exception:
        return False


def switch_stock_by_editor(page, stock_code: str, after_click_wait_sec: int) -> Tuple[bool, str]:
    """
    主要修正版：
    1. 先按「編輯」
    2. 只把股票代號欄位改成純數字 stock_code
    3. 按 Enter / 儲存 / 確認 / 搜尋
    4. 檢查頁面股票代號是否真的切換成功
    """
    logs = []

    # 先接受 cookie，不然可能擋住點擊
    click_cookie_if_any(page)

    # 先嘗試從左側清單點，如果使用者的清單已有該股票，這最穩
    ok, msg = try_click_stock_from_left_list(page, stock_code, after_click_wait_sec)
    logs.append(msg)
    body = page.locator("body").inner_text(timeout=20000)
    current_code, current_name = detect_current_stock(body)
    if ok and current_code == stock_code:
        return True, "；".join(logs + [f"切換成功：{current_code} {current_name}".strip()])

    # 點編輯
    ok, msg = click_text_any(page, ["編輯"], exact=True, timeout=4000)
    logs.append(msg)
    page.wait_for_timeout(1500)

    # 以 JS 尋找「股票代碼」附近的 input，只塞 stock_code
    js_result = page.evaluate(
        """
        (stockCode) => {
          function setNativeValue(el, value) {
            const proto = Object.getPrototypeOf(el);
            const desc = Object.getOwnPropertyDescriptor(proto, "value");
            if (desc && desc.set) desc.set.call(el, value);
            else el.value = value;
            el.dispatchEvent(new Event("input", {bubbles:true}));
            el.dispatchEvent(new Event("change", {bubbles:true}));
          }

          const inputs = Array.from(document.querySelectorAll("input, textarea"));
          const visible = (el) => {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && style.display !== "none" && style.visibility !== "hidden";
          };

          let candidates = [];

          for (const el of inputs) {
            if (!visible(el)) continue;
            const val = (el.value || "").trim();
            const ph = (el.getAttribute("placeholder") || "").trim();
            const aria = (el.getAttribute("aria-label") || "").trim();
            const parentText = (el.closest("div")?.innerText || "").slice(0, 300);
            const html = (el.outerHTML || "").slice(0, 400);

            let score = 0;
            if (/股票代碼|股票代号|代碼|代号|stock/i.test(parentText + ph + aria + html)) score += 10;
            if (/^\\d{4,6}$/.test(val)) score += 8;
            if (val === "1101") score += 6;
            if (/請輸入.*股票|股票.*輸入|代碼|代号|stock/i.test(ph)) score += 5;
            if (el.type === "hidden" || el.disabled || el.readOnly) score -= 20;

            if (score > 0) candidates.push({el, score, val, ph, parentText});
          }

          candidates.sort((a, b) => b.score - a.score);

          if (candidates.length === 0) {
            return {ok:false, reason:"no candidate input", candidates:[]};
          }

          // 只填最高分欄位，避免把股票名稱欄也塞成 3030
          const target = candidates[0].el;
          setNativeValue(target, stockCode);
          target.focus();

          return {
            ok:true,
            reason:"filled best candidate",
            best:{
              score:candidates[0].score,
              oldValue:candidates[0].val,
              placeholder:candidates[0].ph,
              parentText:candidates[0].parentText
            },
            candidateCount:candidates.length
          };
        }
        """,
        stock_code
    )
    logs.append(f"JS 填入股票代號結果：{js_result}")

    page.wait_for_timeout(800)

    # 按 Enter，常見 SPA 會觸發查詢或保存
    try:
        page.keyboard.press("Enter")
        logs.append("pressed Enter after filling stock code")
    except Exception as e:
        logs.append(f"press Enter failed: {e}")

    page.wait_for_timeout(1500)

    # 嘗試點會觸發切換的按鈕
    for button_texts in [
        ["儲存", "保存", "確認", "確定"],
        ["查詢", "搜尋", "送出", "套用"],
        ["編輯"],
    ]:
        ok, msg = click_text_any(page, button_texts, exact=True, timeout=2500)
        logs.append(msg)
        page.wait_for_timeout(1200)
        # 有些頁面點第二次編輯才會儲存，先檢查一次
        try:
            body = page.locator("body").inner_text(timeout=15000)
            current_code, current_name = detect_current_stock(body)
            logs.append(f"目前偵測股票：{current_code} {current_name}".strip())
            if current_code == stock_code:
                page.wait_for_timeout(after_click_wait_sec * 1000)
                return True, "；".join(logs)
        except Exception:
            pass

    # 最後再等久一點，給後端更新
    page.wait_for_timeout(after_click_wait_sec * 1000)
    body = page.locator("body").inner_text(timeout=20000)
    current_code, current_name = detect_current_stock(body)
    logs.append(f"最後偵測股票：{current_code} {current_name}".strip())

    return current_code == stock_code, "；".join(logs)


def click_topic(page, topic: str, wait_sec: int) -> str:
    """
    點選產業情報小助理欄位。
    """
    click_cookie_if_any(page)

    # 產品線分析實際頁面可能有 ❤️產品線分析
    topic_variants = [topic]
    if topic == "產品線分析":
        topic_variants = ["產品線分析", "❤️產品線分析"]

    # 先 exact text
    for t in topic_variants:
        try:
            loc = page.get_by_text(t, exact=True)
            if loc.count() > 0:
                loc.last.click(timeout=5000)
                page.wait_for_timeout(wait_sec * 1000)
                return f"clicked exact topic: {t}"
        except Exception:
            pass

    # 再 JS 找可點擊文字
    escaped = topic.replace("\\", "\\\\").replace("'", "\\'")
    js_clicked = page.evaluate(
        f"""
        () => {{
          const target = '{escaped}';
          const els = Array.from(document.querySelectorAll('button, div, span, a, li'));
          const visible = (el) => {{
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
          }};
          for (const el of els) {{
            const txt = (el.innerText || el.textContent || '').trim();
            if (visible(el) && txt.includes(target)) {{
              el.click();
              return txt;
            }}
          }}
          return '';
        }}
        """
    )
    if js_clicked:
        page.wait_for_timeout(wait_sec * 1000)
        return f"JS clicked topic: {js_clicked}"

    # 找不到就回報，不中斷整個流程
    return f"topic not found: {topic}"


def extract_topic_content(page, topic: str) -> str:
    """
    從整頁文字中盡量切出該 topic 的正文。
    重點：避免把左側清單、EPS 圖表、Cookie 聲明全部重複塞進每個欄位。
    """
    text = page.locator("body").inner_text(timeout=30000)
    text = strip_repeated_noise(text)

    # 找 Q: topic。產品線分析可能是 Q: ❤️產品線分析
    q_candidates = [f"Q: {topic}"]
    if topic == "產品線分析":
        q_candidates.append("Q: ❤️產品線分析")

    start = -1
    for q in q_candidates:
        idx = text.find(q)
        if idx >= 0:
            start = idx
            break

    if start < 0:
        # 後備：找 topic 本身最後一次出現後的內容
        idx = text.rfind(topic)
        if idx >= 0:
            start = idx

    if start >= 0:
        content = text[start:].strip()
    else:
        content = text.strip()

    # 砍掉後面的共通財務圖表 / 聲明 / Cookie
    end_markers = [
        "\nEPS法人預估",
        "\n關注熱度提示",
        "\n優分析 UAnalyze 特別聲明",
        "\n服務條款|免責聲明",
        "\n本網站使用 Cookie 技術",
    ]
    end_positions = [content.find(m) for m in end_markers if content.find(m) > 0]
    if end_positions:
        content = content[:min(end_positions)].strip()

    # 移除 Q: 行之前若仍有導航殘留
    content = re.sub(r"\n{3,}", "\n\n", content).strip()
    return content


def crawl_uanalyze(
    email: str,
    password: str,
    stock_code_raw: str,
    topics: List[str],
    login_url: str,
    dashboard_url: str,
    login_wait_sec: int,
    after_stock_wait_sec: int,
    topic_wait_sec: int,
    save_screenshots: bool,
    allow_wrong_stock_continue: bool,
) -> Tuple[str, Dict[str, bytes], Dict[str, str]]:
    if sync_playwright is None:
        raise RuntimeError("Playwright 沒有成功安裝。請確認 requirements.txt。")

    stock_code = normalize_stock_code(stock_code_raw)
    if not re.fullmatch(r"\d{4,6}", stock_code):
        raise ValueError("股票代號只需要輸入數字，例如 3030。不要輸入中文或底線。")

    files: Dict[str, bytes] = {}
    diagnostics: Dict[str, str] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1440,1100",
            ],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            device_scale_factor=1,
            locale="zh-TW",
            timezone_id="Asia/Taipei",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(120000)

        login_status = login_email_password(page, login_url, email, password, login_wait_sec)
        diagnostics["login_status"] = login_status

        goto_with_retry(page, dashboard_url)
        page.wait_for_timeout(6000)
        click_cookie_if_any(page)
        huba_status = enter_huba_quick_view(page)
        diagnostics["huba_status"] = huba_status

        # 切換股票
        switch_ok, switch_log = switch_stock_by_editor(page, stock_code, after_stock_wait_sec)
        diagnostics["switch_stock_log"] = switch_log

        body = page.locator("body").inner_text(timeout=30000)
        actual_code, actual_name = detect_current_stock(body)
        diagnostics["actual_stock_code"] = actual_code
        diagnostics["actual_stock_name"] = actual_name
        diagnostics["page_title_after_switch"] = page.title()
        diagnostics["page_url_after_switch"] = page.url

        if save_screenshots:
            png = page.screenshot(full_page=True)
            files[f"screenshots/{stock_code}_after_stock_switch.png"] = png

        if actual_code != stock_code:
            warning = (
                f"⚠️ 股票切換失敗：目標是 {stock_code}，但頁面實際偵測為 {actual_code or '未知'} {actual_name or ''}。\n\n"
                f"為避免把台泥 1101 誤標成 {stock_code}，本次已停止爬取。\n\n"
                f"切換紀錄：\n{switch_log}"
            )
            if not allow_wrong_stock_continue:
                md = f"# UAnalyze 爬蟲停止\n\n{warning}\n"
                files[f"{stock_code}_switch_failed.md"] = md.encode("utf-8")
                browser.close()
                return md, files, diagnostics

        page_title = page.title()
        page_url = page.url
        company = actual_name or ""

        sections = []
        for topic in topics:
            status = click_topic(page, topic, topic_wait_sec)
            content = extract_topic_content(page, topic)

            if save_screenshots:
                try:
                    png = page.screenshot(full_page=True)
                    files[f"screenshots/{stock_code}_{safe_filename(topic)}.png"] = png
                except Exception:
                    pass

            sections.append(
                f"## {topic}\n\n"
                f"- 點擊狀態：{status}\n"
                f"- 頁面網址：{page.url}\n\n"
                f"{content}\n"
            )

        crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        md = (
            f"# UAnalyze 產業情報小助理爬蟲結果\n\n"
            f"- 股票代號：{stock_code}\n"
            f"- 頁面實際股票代號：{actual_code or '未偵測'}\n"
            f"- 頁面實際股票名稱：{company or '未偵測'}\n"
            f"- 擷取時間：{crawl_time}\n"
            f"- 最後頁面標題：{page_title}\n"
            f"- 最後頁面網址：{page_url}\n\n"
            f"---\n\n"
            + "\n---\n\n".join(sections)
        )

        files[f"{stock_code}_{safe_filename(company)}_uanalyze.md"] = md.encode("utf-8")
        files["diagnostics.json"] = json.dumps(diagnostics, ensure_ascii=False, indent=2).encode("utf-8")

        browser.close()
        return md, files, diagnostics


# -----------------------------
# Streamlit UI
# -----------------------------

st.set_page_config(page_title=APP_TITLE, layout="wide")
st.title(APP_TITLE)
st.caption("手機版操作：輸入帳密、股票代號、選欄位，按一次開始。股票欄位只要填數字，例如 3030。")

with st.expander("使用說明", expanded=False):
    st.markdown(
        """
        這版重點修正：

        1. 股票欄位只吃數字，`3030_德律` 會自動轉成 `3030`。
        2. 爬取前會先切換股票，並檢查頁面實際股票代碼。
        3. 如果切換失敗，預設會停止，避免把 `1101 台泥` 誤存成 `3030 德律`。
        4. 每個欄位等待時間可以拉長，不用分批爬。
        5. 產出結果可一鍵複製，也可下載 ZIP。
        """
    )

install_msg = ensure_playwright_chromium()
if "失敗" in install_msg:
    st.warning(install_msg)
else:
    st.success(install_msg)

with st.sidebar:
    st.header("登入與目標")
    login_url = st.text_input("登入網址", LOGIN_URL_DEFAULT)
    dashboard_url = st.text_input("虎八速覽網址", DASHBOARD_URL_DEFAULT)

    email = st.text_input("UAnalyze Email")
    password = st.text_input("UAnalyze 密碼", type="password")

    stock_code_raw = st.text_input("股票代號（只要數字）", value="3030", help="例如 3030。不要輸入 3030_德律，也不要輸入中文。")
    stock_code = normalize_stock_code(stock_code_raw)
    st.caption(f"實際送入爬蟲的股票代號：`{stock_code}`")

    st.header("欄位")
    topics = st.multiselect("選擇要爬的欄位", DEFAULT_TOPICS, default=DEFAULT_TOPICS)

    st.header("等待時間")
    login_wait_sec = st.slider("登入後等待秒數", min_value=5, max_value=90, value=25, step=5)
    after_stock_wait_sec = st.slider("股票切換後等待秒數", min_value=5, max_value=120, value=35, step=5)
    topic_wait_sec = st.slider("每個欄位點擊後等待秒數", min_value=5, max_value=90, value=25, step=5)

    st.header("進階")
    save_screenshots = st.checkbox("ZIP 內保存每個欄位截圖", value=False)
    allow_wrong_stock_continue = st.checkbox("即使股票切換失敗也繼續爬取（不建議）", value=False)

start = st.button("開始爬取產業情報欄位", type="primary", use_container_width=True)

if start:
    if not email or not password:
        st.error("請先輸入 UAnalyze Email 和密碼。")
    elif not topics:
        st.error("請至少選一個欄位。")
    elif not re.fullmatch(r"\d{4,6}", stock_code):
        st.error("股票代號只需要輸入數字，例如 3030。")
    else:
        with st.spinner("正在登入、切換股票、逐欄位爬取。這版等待時間較長，請不要關閉頁面。"):
            try:
                md, files, diagnostics = crawl_uanalyze(
                    email=email,
                    password=password,
                    stock_code_raw=stock_code_raw,
                    topics=topics,
                    login_url=login_url,
                    dashboard_url=dashboard_url,
                    login_wait_sec=login_wait_sec,
                    after_stock_wait_sec=after_stock_wait_sec,
                    topic_wait_sec=topic_wait_sec,
                    save_screenshots=save_screenshots,
                    allow_wrong_stock_continue=allow_wrong_stock_continue,
                )
                st.session_state["last_md"] = md
                st.session_state["last_files"] = files
                st.session_state["last_diagnostics"] = diagnostics
            except Exception as e:
                st.exception(e)

if "last_md" in st.session_state:
    md = st.session_state["last_md"]
    files = st.session_state.get("last_files", {})
    diagnostics = st.session_state.get("last_diagnostics", {})

    actual = diagnostics.get("actual_stock_code", "")
    target = normalize_stock_code(stock_code_raw)

    if actual and actual == target:
        st.success(f"看起來已成功切換並爬取：{actual} {diagnostics.get('actual_stock_name','')}")
    elif "爬蟲停止" in md:
        st.error("股票切換未成功，已停止避免抓錯公司。")
    else:
        st.warning(f"請確認實際股票代碼：{actual or '未偵測'}，目標：{target}")

    make_copy_button(md)

    st.subheader("爬蟲結果")
    st.text_area("page text", md, height=520)

    zip_bytes = make_zip_bytes(files)
    zip_name = f"uanalyze_{normalize_stock_code(stock_code_raw)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    st.download_button(
        "下載爬蟲結果 ZIP",
        data=zip_bytes,
        file_name=zip_name,
        mime="application/zip",
        use_container_width=True,
    )

    with st.expander("診斷紀錄", expanded=False):
        st.json(diagnostics)
