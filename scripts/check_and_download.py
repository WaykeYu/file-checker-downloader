import os
import re
import time
import json
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

def is_valid_content(content):
    """嚴格判斷內容是否為有效的介面/設定檔（排除 HTML 網頁與 StreamSaver 腳本）"""
    if not content or len(content) < 10:
        return False
    head = content[:500].decode("utf-8", errors="ignore").strip().lower()
    
    # 判斷是否為 HTML 或 StreamSaver 原始碼
    invalid_keywords = ["<html", "<!doctype", "streamsaver", "service worker", "mitm.html", "404 not found"]
    if any(kw in head for kw in invalid_keywords):
        return False
    return True

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Anti-StreamSaver Direct Intercept ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-popup-blocking",
                "--disable-web-security" # 允許跨域攔截
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        for idx, url in enumerate(URLS, start=1):
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            page = context.new_page()
            captured_cdn_urls = []

            # 專門抓取背景 JSON API 中的真實下載網址，避開 mitm.html 與 sw.js
            def handle_response(response):
                try:
                    res_url = response.url
                    
                    # 忽略所有 StreamSaver 與 HTML 中案頁
                    if "mitm" in res_url or "sw.js" in res_url:
                        return

                    # 1. 攔截城通 JSON API
                    if "get_file" in res_url or "ajax" in res_url or "chk" in res_url:
                        if response.status == 200:
                            try:
                                data = response.json()
                                if isinstance(data, dict):
                                    d_url = data.get("downurl") or data.get("file_url") or data.get("url")
                                    if d_url and d_url not in captured_cdn_urls:
                                        captured_cdn_urls.append(d_url)
                            except Exception:
                                pass

                    # 2. 攔截直接發往 CDN 的檔案下載請求 (通常包含 /down/ 或 .ctfile.com)
                    if "/down/" in res_url or "file" in res_url:
                        if response.status in [200, 206] and res_url not in captured_cdn_urls:
                            # 檢查 content-type 避開 HTML
                            ct = response.headers.get("content-type", "").lower()
                            if "text/html" not in ct and "javascript" not in ct:
                                captured_cdn_urls.append(res_url)

                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                # 載入資料夾頁面
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                # 點擊資料夾內第一個檔案項目
                file_link = page.query_selector("a[href*='/file/'], a[href*='/f/'], tbody tr a")
                if file_link:
                    print("    [i] 進入檔案詳細頁面...")
                    try:
                        with context.expect_page(timeout=5000) as new_page_info:
                            file_link.click(force=True)
                        target_page = new_page_info.value
                    except Exception:
                        target_page = page

                    target_page.wait_for_load_state("domcontentloaded")
                    target_page.on("response", handle_response)
                    time.sleep(3)

                    # 尋找並點擊免費/普通下載按鈕
                    print("    [i] 點擊普通下載，觸發背景 API 攔截...")
                    slow_btn = None
                    for frame in [target_page] + target_page.frames:
                        try:
                            locs = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                            )
                            if locs.count() > 0:
                                slow_btn = locs.first
                                break
                        except Exception:
                            continue

                    if slow_btn:
                        slow_btn.click(force=True)
                        time.sleep(8) # 等待倒數與 AJAX 觸發

                    # 嘗試點擊二次出現的「直接下載」按鈕
                    for frame in [target_page] + target_page.frames:
                        try:
                            final_btns = frame.locator("a, button").filter(
                                has_text=re.compile(r"^Download$|^普通下載$|^直接下載$|^下載$", re.I)
                            )
                            if final_btns.count() > 0:
                                final_btns.first.click(force=True)
                                time.sleep(3)
                        except Exception:
                            continue

                    # 開始使用 Python API 直接對捕捉到的 CDN 網址進行請求（完全繞過 StreamSaver）
                    success = False
                    if captured_cdn_urls:
                        print(f"    [i] 捕捉到 {len(captured_cdn_urls)} 個候選直鏈，驗證下載中...")
                        for cdn_url in captured_cdn_urls:
                            clean_url = cdn_url.replace('\\/', '/')
                            try:
                                # 使用 context.request 直接對 CDN 發送原生 GET 請求
                                res = context.request.get(clean_url)
                                if res.ok:
                                    body = res.body()
                                    if is_valid_content(body):
                                        fname = f"file_{idx}.txt"
                                        save_path = os.path.join(DOWNLOAD_DIR, fname)
                                        with open(save_path, "wb") as f:
                                            f.write(body)
                                        size_kb = len(body) / 1024
                                        print(f"    [✓] 成功繞過 StreamSaver！正確寫入檔案: downloads/{fname} ({size_kb:.2f} KB)")
                                        success = True
                                        break
                            except Exception:
                                continue

                    if not success:
                        print("    [X] 未能從小捕獲的網絡請求中提取出有效的正向檔案")
                        target_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
                else:
                    print("    [-] 資料夾內未找到有效的檔案項目")

            except Exception as e:
                print(f"    [X] 執行過程出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
