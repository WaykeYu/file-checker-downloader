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

def is_valid_text_config(content):
    """嚴格校驗：確保下載到的不是 GIF、PNG、HTML、CSS 等無效檔案"""
    if not content or len(content) < 10:
        return False
    
    # 檢查是否為圖片檔頭
    if content.startswith(b"GIF89a") or content.startswith(b"GIF87a") or content.startswith(b"\x89PNG") or content.startswith(b"\xff\xd8"):
        return False
        
    text = content[:1000].decode("utf-8", errors="ignore").strip().lower()
    
    # 檢查是否為網頁或樣式檔
    invalid_keywords = ["<html", "<!doctype", "datatable", "streamsaver", "function(", "404 not found", "javascript"]
    if any(kw in text for kw in invalid_keywords):
        return False
        
    return True

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Strict Image & GIF Filtering ")
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
            captured_api_urls = []

            # 監聽 Response API (只攔截 JSON 或純文字)
            def handle_response(response):
                try:
                    res_url = response.url
                    # 排除圖片、樣式與腳本
                    if any(ext in res_url.lower() for ext in ['.gif', '.png', '.jpg', '.jpeg', '.css', '.js', '.ico']):
                        return

                    if response.status in [200, 206]:
                        try:
                            data = response.json()
                            if isinstance(data, dict):
                                durl = data.get("downurl") or data.get("file_url") or data.get("url")
                                if durl and isinstance(durl, str) and durl.startswith("http"):
                                    captured_api_urls.append(durl)
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                # 1. 前往資料夾頁面
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # 2. 獲取第一個檔案連結
                file_href = page.evaluate("""() => {
                    const aList = Array.from(document.querySelectorAll('a[href*="/file/"], a[href*="/f/"]'));
                    return aList.length > 0 ? aList[0].href : null;
                }""")

                if not file_href:
                    print("    [X] 未能在資料夾中解析出內部檔案項目")
                    page.close()
                    print("-" * 50)
                    continue

                print(f"    [i] 進入檔案詳細頁面...")
                file_page = context.new_page()
                file_page.on("response", handle_response)

                file_page.goto(file_href, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)

                # 3. 點擊普通下載按鈕
                print("    [i] 點擊普通下載按鈕...")
                file_page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('a, button, div, span'));
                    for (let b of btns) {
                        const txt = (b.innerText || '').trim();
                        if (/普通下載|免費下載|普通下载|Slow download/i.test(txt) && !/極速|客戶端|客户端/i.test(txt)) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""")

                time.sleep(12)  # 等待倒數計時與網絡 API 觸發

                # 4. 點擊「直接下載」按鈕
                print("    [i] 點擊二次確認「直接下載」按鈕...")
                file_page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('a, button, div, span'));
                    for (let b of btns) {
                        const txt = (b.innerText || '').trim();
                        if (/^直接下載$|^直接下载$|^下載$|^下载$|^Download$/i.test(txt)) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""")

                time.sleep(5)

                # 5. 驗證並下載正向內容（過濾 GIF/PNG）
                success = False
                if captured_api_urls:
                    print(f"    [i] 攔截到 {len(captured_api_urls)} 個 API 候選直鏈，校驗檔案中...")
                    for cdn_url in captured_api_urls:
                        clean_url = cdn_url.replace('\\/', '/')
                        try:
                            res = context.request.get(clean_url)
                            if res.ok:
                                body = res.body()
                                if is_valid_text_config(body):
                                    fname = f"file_{idx}.txt"
                                    save_path = os.path.join(DOWNLOAD_DIR, fname)
                                    with open(save_path, "wb") as f:
                                        f.write(body)
                                    size_kb = len(body) / 1024
                                    print(f"    [✓] 成功寫入正向設定檔: downloads/{fname} ({size_kb:.2f} KB)")
                                    success = True
                                    break
                                else:
                                    print("    [!] 跳過無效內容 (GIF 圖片/HTML 廣告頁面)")
                        except Exception:
                            continue

                if not success:
                    print("    [X] 無法從小擷取的網路 API 中取得正確的設定檔內容（已儲存備查截圖）")
                    file_page.screenshot(path=os.path.join(BASE_DIR, f"error_page_{idx}.png"))

                file_page.close()

            except Exception as e:
                print(f"    [X] 執行過程出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
