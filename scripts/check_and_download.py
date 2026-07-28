import os
import re
import time
import json
import requests
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def is_valid_file_content(content):
    """驗證內容是否為有效的直播介面/設定檔文字（非 HTML 網頁）"""
    if not content or len(content) < 10 or len(content) > MAX_FILE_SIZE:
        return False
    head = content[:500].decode("utf-8", errors="ignore").strip().lower()
    if "<html" in head or "<!doctype" in head or "<head" in head or "404 not found" in head:
        return False
    return True

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - API Protocol Mode ")
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
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        )

        for idx, url in enumerate(URLS, start=1):
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            page = context.new_page()
            captured_api_data = {}

            # 監聽城通的所有 XHR / Fetch API 響應
            def handle_response(response):
                try:
                    res_url = response.url
                    if "get_file" in res_url or "file_info" in res_url or "ajax" in res_url or "guest_chk" in res_url:
                        if response.status == 200:
                            try:
                                data = response.json()
                                if isinstance(data, dict):
                                    captured_api_data.update(data)
                            except Exception:
                                text = response.text()
                                matches = re.findall(r'https?://[^\s"\']+\.ctfile\.com[^\s"\']*', text)
                                if matches:
                                    captured_api_data["direct_urls"] = matches
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                # 載入頁面並自動注入跳過倒數的腳本
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # 嘗試自動點擊第一個可用的檔案項目
                item_links = page.query_selector_all("table tbody tr a, .file-list-item a, a[href*='/file/'], a[href*='/f/']")
                if item_links:
                    item_links[0].click(force=True)
                    time.sleep(3)

                # 嘗試強制點擊免費下載區域
                for frame in [page] + page.frames:
                    try:
                        slow_btns = frame.locator("a, button, div").filter(
                            has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                        )
                        if slow_btns.count() > 0:
                            slow_btns.first.click(force=True)
                            break
                    except Exception:
                        continue

                time.sleep(6) # 等待 6 秒網路 API 回應

                success = False

                # 優先檢查是否從 API 回應中抓到了真實直鏈 (code: 200, downurl/file_url)
                direct_url = captured_api_data.get("downurl") or captured_api_data.get("file_url") or captured_api_data.get("url")
                
                urls_to_try = []
                if direct_url:
                    urls_to_try.append(direct_url)
                if "direct_urls" in captured_api_data:
                    urls_to_try.extend(captured_api_data["direct_urls"])

                # 如果背景 API 被阻擋，嘗試直接解析頁面 DOM 裡可能藏有的直鏈變數
                if not urls_to_try:
                    content_text = page.content()
                    found_urls = re.findall(r'https?://[^\s"\']+\.ctfile\.com/down/[^\s"\']*', content_text)
                    urls_to_try.extend(found_urls)

                for candidate_url in urls_to_try:
                    clean_url = candidate_url.replace('\\/', '/')
                    try:
                        res = context.request.get(clean_url)
                        if res.ok:
                            body = res.body()
                            if is_valid_file_content(body):
                                fname = f"file_{idx}.txt"
                                save_path = os.path.join(DOWNLOAD_DIR, fname)
                                with open(save_path, "wb") as f:
                                    f.write(body)
                                print(f"    [✓] API 直鏈驗證成功！已儲存正項檔案: downloads/{fname} ({len(body)/1024:.2f} KB)")
                                success = True
                                break
                    except Exception:
                        continue

                if not success:
                    print("    [X] 未能下載到正確的檔案，可能觸發了城通網盤的圖形驗證碼 (CAPTCHA)。")
                    page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))

            except Exception as e:
                print(f"    [X] 執行出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
