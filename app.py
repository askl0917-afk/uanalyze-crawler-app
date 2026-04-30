import io
import json
import re
import zipfile
import subprocess
import sys
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components


st.set_page_config(page_title="UAnalyze 產業情報爬蟲", layout="wide")

st.title("UAnalyze 產業情報小助理爬蟲版")
st.caption("登入後進入虎八速覽，輸入股票代號，點擊產業情報欄位，彙整成 Markdown，支援一鍵複製與 ZIP 下載。密碼不會寫入檔案。")


TOPICS = [
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


login_url = st.text_input(
    "UAnalyze 登入頁網址",
    value="https://pro.uanalyze.com.tw/login-page",
)

email = st.text_input("UAnalyze Email")
password = st.text_input("UAnalyze 密碼", type="password")

st.divider()

stock_code = st.text_input("股票代號", value="3030")
company_name = st.text_input("公司名稱", value="德律")

selected_topics = st.multiselect(
    "選擇要爬的欄位",
    TOPICS,
    default=TOPICS,
)

wait_seconds = st.slider("登入後等待秒數", 5, 45, 15)
topic_wait_seconds = st.slider("每個欄位點擊後等待秒數", 3, 25, 8)

save_screenshots = st.checkbox("ZIP 內同時保存每個欄位截圖", value=False)


def safe_name(text: str) -> str:
    text = str(text).strip()
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    text = re.sub(r"\s+", "_", text)
    return text[:80] or "untitled"


def copy_button(text: str, label: str = "一鍵複製全部資料"):
    safe_text = json.dumps(text or "", ensure_ascii=False)

    components.html(
        f"""
        <div style="margin: 12px 0;">
            <button
                onclick="copyTextToClipboard()"
                style="
                    background-color:#ff9800;
                    color:#111;
                    border:none;
                    border-radius:10px;
                    padding:14px 18px;
                    font-size:18px;
                    font-weight:700;
                    cursor:pointer;
                    width:100%;
                    max-width:460px;
                "
            >
                📋 {label}
            </button>
            <div id="copy-status" style="margin-top:10px;color:#20c997;font-size:16px;"></div>
        </div>

        <script>
        const textToCopy = {safe_text};

        async function copyTextToClipboard() {{
            const status = document.getElementById("copy-status");

            try {{
                await navigator.clipboard.writeText(textToCopy);
                status.innerText = "已複製到剪貼簿";
            }} catch (err) {{
                const textarea = document.createElement("textarea");
                textarea.value = textToCopy;
                textarea.style.position = "fixed";
                textarea.style.left = "0";
                textarea.style.top = "0";
                textarea.style.width = "1px";
                textarea.style.height = "1px";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();

                try {{
                    document.execCommand("copy");
                    status.innerText = "已複製到剪貼簿";
                }} catch (fallbackErr) {{
                    status.innerText = "複製失敗，請改用下方文字框手動長按複製";
                }}

                document.body.removeChild(textarea);
            }}
        }}
        </script>
        """,
        height=100,
    )


def install_playwright_chromium():
    return subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
        timeout=240,
    )


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = []

    skip_exact = {
        "深色主題",
        "帳戶和訂閱",
        "最新公告",
        "我的訂閱",
        "商城",
    }

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue

        if line in skip_exact:
            continue

        lines.append(line)

    return "\n".join(lines).strip()


def close_blockers(page):
    actions = []

    try:
        if page.get_by_text("重新整理", exact=False).count() > 0:
            page.get_by_text("重新整理", exact=False).first.click(timeout=4000)
            actions.append("clicked 重新整理")
            page.wait_for_timeout(6000)
    except Exception:
        pass

    try:
        body = page.locator("body").inner_text(timeout=5000)
        if "系統已有更新" in body or "請重新整理" in body:
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(7000)
            actions.append("page.reload")
    except Exception:
        pass

    for t in ["我知道了", "同意", "接受", "接受所有", "OK"]:
        try:
            if page.get_by_text(t, exact=False).count() > 0:
                page.get_by_text(t, exact=False).last.click(timeout=4000)
                actions.append(f"clicked {t}")
                page.wait_for_timeout(1500)
                break
        except Exception:
            pass

    return actions


def fill_like_human(page, email, password):
    actions = []

    email_candidates = [
        "input[placeholder*='Email']",
        "input[placeholder*='email']",
        "input[type='email']",
        "input:not([type])",
        "input[type='text']",
    ]

    email_filled = False

    for selector in email_candidates:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=5000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(email, delay=60)
                actions.append(f"typed email by {selector}")
                email_filled = True
                break
        except Exception:
            pass

    password_filled = False

    try:
        loc = page.locator("input[type='password']").first
        if loc.count() > 0:
            loc.click(timeout=5000)
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            page.keyboard.type(password, delay=70)
            actions.append("typed password by input[type=password]")
            password_filled = True
    except Exception:
        pass

    page.wait_for_timeout(1500)

    return {
        "email_filled": email_filled,
        "password_filled": password_filled,
        "actions": actions,
    }


def click_login(page):
    methods = []

    try:
        buttons = page.locator("button").filter(has_text="登入")
        if buttons.count() > 0:
            buttons.last.click(timeout=5000)
            methods.append("clicked button has_text 登入")
            return methods
    except Exception:
        pass

    try:
        clicked = page.evaluate(
            """
            () => {
                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 5 &&
                           r.height > 5 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden' &&
                           s.opacity !== '0';
                }

                const nodes = Array.from(document.querySelectorAll('button, div, span, a'))
                    .filter(visible)
                    .map(el => ({
                        el,
                        text: (el.innerText || '').trim(),
                        top: el.getBoundingClientRect().top,
                    }))
                    .filter(x =>
                        (x.text === '登入' || x.text === '登 入') &&
                        !x.text.includes('Google') &&
                        !x.text.includes('Facebook') &&
                        !x.text.includes('Apple')
                    )
                    .sort((a, b) => a.top - b.top);

                if (!nodes.length) return false;

                nodes[nodes.length - 1].el.scrollIntoView({block: 'center'});
                nodes[nodes.length - 1].el.click();
                return true;
            }
            """
        )

        if clicked:
            methods.append("JS clicked native login")
            return methods
    except Exception:
        pass

    try:
        page.locator("input[type='password']").first.click(timeout=5000)
        page.keyboard.press("Enter")
        methods.append("pressed Enter in password field")
        return methods
    except Exception:
        pass

    return methods


def click_huba_quick_view(page):
    actions = []
    page.wait_for_timeout(3000)

    try:
        if page.get_by_text("虎八速覽", exact=False).count() > 0:
            page.get_by_text("虎八速覽", exact=False).first.click(timeout=5000)
            actions.append("clicked text 虎八速覽")
            page.wait_for_timeout(8000)
            return actions
    except Exception:
        pass

    try:
        clicked = page.evaluate(
            """
            () => {
                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 5 &&
                           r.height > 5 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden' &&
                           s.opacity !== '0';
                }

                const nodes = Array.from(document.querySelectorAll('button, a, div, span, li'))
                    .filter(visible)
                    .map(el => ({
                        el,
                        text: (el.innerText || '').trim(),
                        top: el.getBoundingClientRect().top,
                        left: el.getBoundingClientRect().left,
                        len: ((el.innerText || '').trim()).length
                    }))
                    .filter(x => x.text.includes('虎八速覽'))
                    .sort((a, b) => a.len - b.len || a.left - b.left || a.top - b.top);

                if (!nodes.length) return false;

                nodes[0].el.scrollIntoView({block: 'center'});
                nodes[0].el.click();
                return true;
            }
            """
        )

        if clicked:
            actions.append("JS clicked visible 虎八速覽")
            page.wait_for_timeout(8000)
            return actions
    except Exception:
        pass

    actions.append("failed to click 虎八速覽")
    return actions


def switch_stock(page, stock_code: str, company_name: str):
    actions = []
    query = stock_code.strip() or company_name.strip()

    if not query:
        actions.append("no stock query")
        return actions

    page.wait_for_timeout(3000)

    search_selectors = [
        "input[placeholder*='搜尋代碼或名稱']",
        "input[placeholder*='搜尋']",
        "input[placeholder*='代碼']",
        "input[placeholder*='名稱']",
        "input[role='combobox']",
    ]

    used_selector = ""

    for selector in search_selectors:
        try:
            loc = page.locator(selector).first
            if loc.count() > 0:
                loc.click(timeout=5000)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                page.keyboard.type(query, delay=80)
                used_selector = selector
                actions.append(f"typed stock query {query} by {selector}")
                page.wait_for_timeout(2000)

                # 常見搜尋下拉選單：先按 Enter
                page.keyboard.press("Enter")
                page.wait_for_timeout(6000)

                break
        except Exception:
            pass

    if not used_selector:
        actions.append("failed to find search input")
        return actions

    # 如果 Enter 沒有切換，嘗試 ArrowDown + Enter
    try:
        body_text = page.locator("body").inner_text(timeout=10000)
        if stock_code not in body_text and company_name not in body_text:
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(500)
            page.keyboard.press("Enter")
            actions.append("pressed ArrowDown + Enter fallback")
            page.wait_for_timeout(7000)
    except Exception:
        pass

    # 如果畫面有直接出現股票代號或公司名稱，嘗試點擊
    for text in [stock_code, company_name, f"{stock_code} {company_name}".strip()]:
        if not text:
            continue
        try:
            if page.get_by_text(text, exact=False).count() > 0:
                page.get_by_text(text, exact=False).first.click(timeout=4000)
                actions.append(f"clicked visible search result: {text}")
                page.wait_for_timeout(7000)
                break
        except Exception:
            pass

    return actions


def click_topic(page, topic: str):
    actions = []

    try:
        if page.get_by_text(topic, exact=True).count() > 0:
            page.get_by_text(topic, exact=True).last.click(timeout=5000)
            actions.append(f"clicked exact topic: {topic}")
            page.wait_for_timeout(3000)
            return actions
    except Exception:
        pass

    try:
        clicked = page.evaluate(
            """
            (topic) => {
                function visible(el) {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 5 &&
                           r.height > 5 &&
                           s.display !== 'none' &&
                           s.visibility !== 'hidden' &&
                           s.opacity !== '0';
                }

                const nodes = Array.from(document.querySelectorAll('button, a, div, span, li'))
                    .filter(visible)
                    .map(el => ({
                        el,
                        text: (el.innerText || '').trim(),
                        top: el.getBoundingClientRect().top,
                        left: el.getBoundingClientRect().left,
                        len: ((el.innerText || '').trim()).length
                    }))
                    .filter(x => x.text === topic || x.text.includes(topic))
                    .sort((a, b) => a.len - b.len || a.left - b.left || a.top - b.top);

                if (!nodes.length) return false;

                nodes[0].el.scrollIntoView({block: 'center'});
                nodes[0].el.click();
                return true;
            }
            """,
            topic,
        )

        if clicked:
            actions.append(f"JS clicked topic: {topic}")
            page.wait_for_timeout(3000)
            return actions
    except Exception:
        pass

    actions.append(f"failed to click topic: {topic}")
    return actions


def extract_topic_text(page):
    try:
        text = page.locator("body").inner_text(timeout=10000)
        return clean_text(text)
    except Exception:
        return ""


def build_markdown(company_label, page_title, page_url, topic_results):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    parts = [
        f"# UAnalyze 產業情報小助理爬蟲結果",
        "",
        f"- 公司：{company_label}",
        f"- 擷取時間：{now}",
        f"- 頁面標題：{page_title}",
        f"- 頁面網址：{page_url}",
        "",
        "---",
        "",
    ]

    for item in topic_results:
        parts.append(f"## {item['topic']}")
        parts.append("")
        parts.append(f"- 點擊狀態：{', '.join(item['actions'])}")
        parts.append("")
        parts.append(item["text"] or "無內容")
        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)


if st.button("開始爬取產業情報欄位"):
    if not email or not password:
        st.error("請先輸入 Email 和密碼。")
        st.stop()

    if not stock_code and not company_name:
        st.error("請先輸入股票代號或公司名稱。")
        st.stop()

    if not selected_topics:
        st.error("請至少選一個要爬的欄位。")
        st.stop()

    company_label = f"{stock_code}_{company_name}".strip("_")

    st.info("開始檢查 Playwright Chromium，這一步可能需要 1～3 分鐘。")

    install = install_playwright_chromium()

    if install.returncode != 0:
        st.error("Playwright Chromium 安裝失敗。")
        st.code(install.stdout + "\n" + install.stderr)
        st.stop()

    st.success("Playwright Chromium 安裝 / 檢查完成。")

    progress = st.progress(0)
    status_box = st.empty()

    try:
        from playwright.sync_api import sync_playwright

        topic_results = []
        screenshots = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )

            context = browser.new_context(
                viewport={"width": 1440, "height": 1000},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            page = context.new_page()

            status_box.write("登入 UAnalyze 中...")
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)

            blocker_actions = close_blockers(page)
            page.wait_for_timeout(3000)

            fill_result = fill_like_human(page, email, password)
            login_methods = click_login(page)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(wait_seconds * 1000)

            login_title = page.title()
            login_url_after = page.url
            login_text = extract_topic_text(page)

            progress.progress(10)

            status_box.write("開啟虎八速覽中...")
            huba_actions = click_huba_quick_view(page)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(5000)

            huba_title = page.title()
            huba_url = page.url
            huba_text = extract_topic_text(page)

            progress.progress(20)

            status_box.write(f"切換公司：{company_label} ...")
            stock_actions = switch_stock(page, stock_code, company_name)

            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            page.wait_for_timeout(5000)

            after_stock_title = page.title()
            after_stock_url = page.url
            after_stock_text = extract_topic_text(page)
            after_stock_screenshot = page.screenshot(full_page=True)

            progress.progress(30)

            total = len(selected_topics)

            for idx, topic in enumerate(selected_topics, start=1):
                status_box.write(f"處理欄位 {idx}/{total}：{topic}")

                actions = click_topic(page, topic)

                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass

                page.wait_for_timeout(topic_wait_seconds * 1000)

                topic_text = extract_topic_text(page)

                topic_item = {
                    "topic": topic,
                    "actions": actions,
                    "text": topic_text,
                    "url": page.url,
                    "title": page.title(),
                }

                topic_results.append(topic_item)

                if save_screenshots:
                    try:
                        screenshots[topic] = page.screenshot(full_page=True)
                    except Exception:
                        pass

                progress_value = 30 + int(idx / total * 65)
                progress.progress(min(progress_value, 95))

            final_title = page.title()
            final_url = page.url

            browser.close()

        result_markdown = build_markdown(
            company_label=company_label,
            page_title=final_title,
            page_url=final_url,
            topic_results=topic_results,
        )

        progress.progress(100)
        status_box.write("完成。")

        st.subheader("登入與切換公司結果")
        st.write("登入後標題：", login_title)
        st.write("登入後網址：", login_url_after)
        st.write("虎八速覽點擊動作：", huba_actions)
        st.write("切換公司動作：", stock_actions)
        st.write("切換公司後標題：", after_stock_title)
        st.write("切換公司後網址：", after_stock_url)

        st.image(after_stock_screenshot, caption="切換公司後截圖")

        company_success_hint = (
            (stock_code and stock_code in after_stock_text)
            or (company_name and company_name in after_stock_text)
        )

        if company_success_hint:
            st.success(f"看起來已經切換到 {company_label}。")
        else:
            st.warning("不確定是否成功切換公司，請看截圖。若仍是台泥，需要再調整搜尋欄位點擊方式。")

        st.subheader("爬取結果")

        copy_button(result_markdown, "一鍵複製全部爬蟲結果")

        st.text_area("全部結果 Markdown", result_markdown, height=500)

        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"uanalyze_{safe_name(company_label)}_{now}.zip"

        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("_ALL_CONTENT.md", result_markdown)
            z.writestr("debug_login_text.txt", login_text)
            z.writestr("debug_huba_text.txt", huba_text)
            z.writestr("debug_after_stock_text.txt", after_stock_text)
            z.writestr(
                "debug_info.txt",
                f"company_label={company_label}\n"
                f"blocker_actions={blocker_actions}\n"
                f"fill_result={fill_result}\n"
                f"login_methods={login_methods}\n"
                f"login_title={login_title}\n"
                f"login_url_after={login_url_after}\n"
                f"huba_actions={huba_actions}\n"
                f"huba_title={huba_title}\n"
                f"huba_url={huba_url}\n"
                f"stock_actions={stock_actions}\n"
                f"after_stock_title={after_stock_title}\n"
                f"after_stock_url={after_stock_url}\n"
            )

            z.writestr("after_stock_screenshot.png", after_stock_screenshot)

            for item in topic_results:
                topic_file = f"{safe_name(item['topic'])}.md"
                z.writestr(topic_file, f"# {item['topic']}\n\n{item['text']}")

            if save_screenshots:
                for topic, png in screenshots.items():
                    z.writestr(f"screenshots/{safe_name(topic)}.png", png)

        zip_buffer.seek(0)

        st.download_button(
            label="下載 ZIP",
            data=zip_buffer,
            file_name=zip_name,
            mime="application/zip",
        )

        st.download_button(
            label="下載 Markdown",
            data=result_markdown.encode("utf-8"),
            file_name=f"uanalyze_{safe_name(company_label)}_{now}.md",
            mime="text/markdown",
        )

    except Exception as e:
        st.error("爬取流程失敗。")
        st.exception(e)
