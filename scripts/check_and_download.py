import os
import re
import time
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

def is_valid_config_content(content):
    """驗證是否為有效的文字/介面設定檔內容（排除 HTML / CSS / JS）"""
    if not content or len(content) < 10:
        return False
    text = content[:1000].decode("utf-8", errors="ignore").strip().lower()
    invalid_tags = ["<html", "<!doctype", "datatable", "streamsaver", "function(", "404 not found"]
    if any(tag in text for tag in invalid_tags):
        return False
    return True

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Playwright Session JS Hybrid ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )

        for idx, url in enumerate(URLS, start=1):
            print(f"[{idx}/{len(URLS)}] 正在讀取資料夾頁面: {url}")
            page = context.new_page()
            captured_urls = []

            # 全局監聽城通的所有網絡響應
            def handle_response(response):
                try:
                    res_url = response.url
                    # 當城通返回含有 downurl 的 JSON 數據時自動捕捉
                    if response.status == 200 and ("get_file" in res_url or "ajax" in res_url or "chk" in res_url):
                        try:
                            data = response.json()
                            if isinstance(data, dict):
                                durl = data.get("downurl") or data.get("file_url") or data.get("url")
                                if durl and durl not in captured_urls:
                                    captured_urls.append(durl)
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                # 1. 前往城通資料夾頁面，等待 JS 完全載入
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # 2. 從 DOM 中獲取檔案項目的真正的 href 網址
                file_href = page.evaluate("""() => {
                    const aList = Array.from(document.querySelectorAll('a[href*="/file/"], a[href*="/f/"]'));
                    if (aList.length > 0) {
                        return aList[0].href;
                    }
                    return null;
                }""")

                if not file_href:
                    print("    [X] 無法在 DOM 列表中解析出檔案連結")
                    page.close()
                    print("-" * 50)
                    continue

                print(f"    [i] 成功提取內部檔案連結，正在進入詳細頁面...")
                
                # 3. 進入單檔詳細頁面
                file_page = context.new_page()
                file_page.on("response", handle_response)
                file_page.goto(file_href, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)

                # 4. 點擊「普通下載」按鈕觸發 AJAX 請求
                print("    [i] 觸發普通下載按鈕...")
                clicked = file_page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('a, button, div, span'));
                    for (let b of btns) {
                        if (/普通下載|免費下載|普通下载|Slow download/i.test(b.innerText) && !/極速|客戶端|客户端/i.test(b.innerText)) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""")

                if clicked:
                    time.sleep(8) # 等待城通倒數與發送 API

                # 5. 如果抓取到了 straight downurl，直接透過 Playwright Context 進行 HTTP 下載
                success = False
                if captured_urls:
                    print(f"    [i] 成功捕捉到 {len(captured_urls)} 個候選直鏈，驗證下載中...")
                    for cdn_url in captured_urls:
                        clean_url = cdn_url.replace('\\/', '/')
                        try:
                            res = context.request.get(clean_url)
                            if res.ok:
                                body = res.body()
                                if is_valid_config_content(body):
                                    fname = f"file_{idx}.txt"
                                    save_path = os.path.join(DOWNLOAD_DIR, fname)
                                    with open(save_path, "wb") as f:
                                        f.write(body)
                                    size_kb = len(body) / 1024
                                    print(f"    [✓] 下載成功！檔案已存至: downloads/{fname} ({size_kb:.2f} KB)")
                                    success = True
                                    break
                        except Exception:
                            continue

                if not success:
                    print("    [X] 未能提取到正向設定檔內容（可能被城通驗證碼攔截）")

                file_page.close()

            except Exception as e:
                print(f"    [X] 執行出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
