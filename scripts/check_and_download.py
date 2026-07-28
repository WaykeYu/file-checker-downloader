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

def is_valid_config_content(content):
    """驗證內容是否為有效的文字/介面設定檔內容（排除 HTML / CSS / JS）"""
    if not content or len(content) < 10:
        return False
    text = content[:1000].decode("utf-8", errors="ignore").strip().lower()
    invalid_tags = ["<html", "<!doctype", "datatable", "streamsaver", "function(", "404 not found"]
    if any(tag in text for tag in invalid_tags):
        return False
    return True

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Full Automation Dual-Click ")
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
            viewport={"width": 1280, "height": 800},
            accept_downloads=True
        )

        for idx, url in enumerate(URLS, start=1):
            print(f"[{idx}/{len(URLS)}] 正在讀取資料夾頁面: {url}")
            page = context.new_page()
            captured_urls = []

            # 監聽全局響應：只要包含 CDN 下載連結或 downurl 的 JSON 全部攔截
            def handle_response(response):
                try:
                    res_url = response.url
                    # 1. 攔截 JSON API 中的 downurl / url
                    if response.status == 200:
                        ct = response.headers.get("content-type", "").lower()
                        if "json" in ct or "javascript" in ct or "plain" in ct:
                            try:
                                data = response.json()
                                if isinstance(data, dict):
                                    durl = data.get("downurl") or data.get("file_url") or data.get("url") or data.get("link")
                                    if durl and isinstance(durl, str) and durl.startswith("http"):
                                        if durl not in captured_urls:
                                            captured_urls.append(durl)
                            except Exception:
                                pass
                    
                    # 2. 直接捕捉向 ctfile CDN 發起的大檔案 GET/POST 請求
                    if (".ctfile." in res_url or "/down/" in res_url or "file" in res_url) and response.status in [200, 206]:
                        ct = response.headers.get("content-type", "").lower()
                        if "html" not in ct and "javascript" not in ct and "css" not in ct:
                            if res_url not in captured_urls:
                                captured_urls.append(res_url)
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                # 1. 前往城通資料夾頁面
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # 2. 獲取內部第一個檔案項目的網址
                file_href = page.evaluate("""() => {
                    const aList = Array.from(document.querySelectorAll('a[href*="/file/"], a[href*="/f/"]'));
                    return aList.length > 0 ? aList[0].href : null;
                }""")

                if not file_href:
                    print("    [X] 無法在 DOM 列表中解析出檔案連結")
                    page.close()
                    print("-" * 50)
                    continue

                print(f"    [i] 進入檔案詳細頁面...")
                file_page = context.new_page()
                file_page.on("response", handle_response)
                
                # 監聽可能觸發的原生下載事件
                download_holder = []
                file_page.on("download", lambda d: download_holder.append(d))

                file_page.goto(file_href, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)

                # 3. 第一次點擊：「普通下載 / 免費下載」
                print("    [i] 步驟 1: 點擊普通下載按鈕...")
                clicked_first = file_page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('a, button, div, span'));
                    for (let b of btns) {
                        const txt = b.innerText || '';
                        if (/普通下載|免費下載|普通下载|Slow download/i.test(txt) && !/極速|客戶端|客户端/i.test(txt)) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""")

                if clicked_first:
                    print("    [i] 已觸發首次點擊，等待 12 秒城通倒數計時與彈窗...")
                    time.sleep(12)

                # 4. 第二次點擊：等待倒數完成後出現的「直接下載 / 下載」
                print("    [i] 步驟 2: 點擊二次確認的「直接下載」按鈕...")
                file_page.evaluate("""() => {
                    const btns = Array.from(document.querySelectorAll('a, button, div, span'));
                    for (let b of btns) {
                        const txt = (b.innerText || '').strip();
                        if (/^直接下載$|^直接下载$|^下載$|^下载$|^Download$/i.test(txt)) {
                            b.click();
                            return true;
                        }
                    }
                    // 備用：嘗試點擊頁面上所有含 downurl 的 <a> 標籤
                    const links = Array.from(document.querySelectorAll('a[href*="http"]'));
                    for (let l of links) {
                        if (/ctfile|down/i.test(l.href)) {
                            l.click();
                        }
                    }
                    return false;
                }""")
                time.sleep(5)

                # 5. 優先檢查是否觸發了原生 Playwright Download
                success = False
                if download_holder:
                    print("    [i] 觸發瀏覽器原生下載流程...")
                    dl = download_holder[0]
                    fname = f"file_{idx}.txt"
                    save_path = os.path.join(DOWNLOAD_DIR, fname)
                    dl.save_as(save_path)
                    
                    with open(save_path, "rb") as f:
                        if is_valid_config_content(f.read()):
                            print(f"    [✓] 原生下載成功！已儲存至: downloads/{fname}")
                            success = True

                # 6. 若無原生下載，驗證捕捉到的 CDN 候選直鏈
                if not success and captured_urls:
                    print(f"    [i] 捕捉到 {len(captured_urls)} 個候選直鏈，開始逐一拉取驗證...")
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
                                    print(f"    [✓] 直鏈拉取成功！已儲存至: downloads/{fname} ({size_kb:.2f} KB)")
                                    success = True
                                    break
                        except Exception:
                            continue

                if not success:
                    print("    [X] 未能成功下載正向設定檔（已截圖存檔備查）")
                    file_page.screenshot(path=os.path.join(BASE_DIR, f"debug_file_{idx}.png"))

                file_page.close()

            except Exception as e:
                print(f"    [X] 執行過程出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
