import os
import re
import time
import json
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def is_valid_content(content):
    """確認下載到的內容是真實介面/文字檔（非 HTML 網頁）"""
    if not content or len(content) < 10:
        return False
    head = content[:500].decode("utf-8", errors="ignore").strip().lower()
    if "<html" in head or "<!doctype" in head or "404 not found" in head:
        return False
    return True

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Dynamic Network Intercept ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-popup-blocking"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        for idx, url in enumerate(URLS, start=1):
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            page = context.new_page()
            captured_urls = []

            # 全局監聽城通網盤發送的所有 API 響應
            def handle_response(response):
                try:
                    res_url = response.url
                    # 捕捉包含下載 API 或直鏈特徵的網絡響應
                    if any(k in res_url for k in ["get_file", "ajax", "down", "file_info"]):
                        if response.status == 200:
                            try:
                                data = response.json()
                                if isinstance(data, dict):
                                    d_url = data.get("downurl") or data.get("file_url") or data.get("url")
                                    if d_url and d_url not in captured_urls:
                                        captured_urls.append(d_url)
                            except Exception:
                                text = response.text()
                                matches = re.findall(r'https?://[^\s"\']+\.ctfile\.com[^\s"\']*', text)
                                for m in matches:
                                    clean_m = m.replace('\\/', '/')
                                    if clean_m not in captured_urls and not clean_m.endswith(('.css', '.js', '.png', '.jpg')):
                                        captured_urls.append(clean_m)
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                # 載入頁面並等待 JS 渲染檔案清單
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # 尋找最新檔案或點擊列表中第一筆檔案
                rows = page.query_selector_all("table tbody tr, .file-list-item, div.row, li")
                target_link = None

                for row in rows:
                    link = row.query_selector("a[href*='/file/'], a[href*='/f/'], td a")
                    if link:
                        target_link = link
                        break

                if not target_link:
                    target_link = page.query_selector("a[href*='/file/'], a[href*='/f/']")

                if target_link:
                    print("    [i] 已定位到檔案項目，點擊進入詳細頁面...")
                    try:
                        with context.expect_page(timeout=5000) as new_page_info:
                            target_link.click(force=True)
                        target_page = new_page_info.value
                    except Exception:
                        target_page = page

                    target_page.wait_for_load_state("domcontentloaded")
                    target_page.on("response", handle_response)
                    time.sleep(3)

                    # 在詳細頁搜尋並點擊普通下載/免費下載按鈕
                    slow_btn = None
                    for frame in [target_page] + target_page.frames:
                        try:
                            locs = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                            )
                            for i in range(locs.count()):
                                btn = locs.nth(i)
                                btn_text = btn.inner_text()
                                if btn.is_visible() and not any(k in btn_text for k in ["客戶端", "客户端", "高速", "極速"]):
                                    slow_btn = btn
                                    break
                            if slow_btn:
                                break
                        except Exception:
                            continue

                    if slow_btn:
                        print("    [i] 觸發免費下載按鈕，等待網絡 API 傳回直鏈...")
                        slow_btn.click(force=True)
                        time.sleep(8)  # 等待倒數與 AJAX API 回傳

                    # 嘗試點擊二次出現的下載按鈕以確保 API 被喚醒
                    for frame in [target_page] + target_page.frames:
                        try:
                            final_btns = frame.locator("a, button").filter(
                                has_text=re.compile(r"^Download$|^普通下載$|^直接下載$|^下載$", re.I)
                            )
                            for i in range(final_btns.count()):
                                if final_btns.nth(i).is_visible():
                                    final_btns.nth(i).click(force=True)
                                    time.sleep(2)
                        except Exception:
                            continue

                    time.sleep(3)

                    # 開始嘗試請求捕捉到的可能直鏈
                    success = False
                    if captured_urls:
                        print(f"    [i] 成功攔截到 {len(captured_urls)} 個候選直鏈，開始校驗內容...")
                        for direct_url in captured_urls:
                            try:
                                res = context.request.get(direct_url)
                                if res.ok:
                                    body = res.body()
                                    if is_valid_content(body):
                                        fname = f"file_{idx}.txt"
                                        save_path = os.path.join(DOWNLOAD_DIR, fname)
                                        with open(save_path, "wb") as f:
                                            f.write(body)
                                        size_kb = len(body) / 1024
                                        print(f"    [✓] 成功下載並驗證正向檔案: downloads/{fname} ({size_kb:.2f} KB)")
                                        success = True
                                        break
                            except Exception:
                                continue

                    if not success:
                        print("    [X] 無法從小抓到的 API 響應中獲取正確檔案內容")
                        target_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
                else:
                    print("    [-] 未能在資料夾中找到任何有效檔案連結")

            except Exception as e:
                print(f"    [X] 執行過程出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
