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

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB Limit

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Direct API Mode ")
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
            viewport={"width": 1280, "height": 800},
            accept_downloads=True
        )

        for idx, url in enumerate(URLS, start=1):
            page = context.new_page()
            captured_file_urls = []

            # 監聽後端 API 響應以抓取真正的下載網址
            def handle_response(response):
                try:
                    res_url = response.url
                    if "get_file" in res_url or "file_info" in res_url or "down" in res_url:
                        if response.status == 200:
                            text = response.text()
                            # 搜尋回傳的 json 或 text 中是否包含真實下載網址
                            matches = re.findall(r'https?://[^\s"\']+\.ctfile\.com[^\s"\']*', text)
                            for m in matches:
                                clean_m = m.replace('\\/', '/')
                                if clean_m not in captured_file_urls and not clean_m.endswith(('.css', '.js', '.png', '.jpg')):
                                    captured_file_urls.append(clean_m)
                except Exception:
                    pass

            page.on("response", handle_response)
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                # 定位檔案列表項目
                items = page.query_selector_all("table tbody tr, .file-list-item, div.row, li")
                candidates = []
                for item in items:
                    text_content = item.inner_text()
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text_content)
                    if date_match:
                        date_str = date_match.group(1).replace('/', '-')
                        try:
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                            if file_date.year >= 2020:
                                candidates.append({
                                    "item": item,
                                    "date": file_date,
                                    "date_str": date_str
                                })
                        except ValueError:
                            continue

                latest_target = max(candidates, key=lambda x: x["date"]) if candidates else None
                
                if not latest_target:
                    link_first = page.query_selector("a[href*='/file/'], a[href*='/f/'], table tbody tr a")
                    if link_first:
                        latest_target = {"item": link_first, "date_str": "預設第一筆項目"}

                if latest_target:
                    item_element = latest_target["item"]
                    link_el = item_element.query_selector("a") or item_element

                    try:
                        with context.expect_page(timeout=5000) as new_page_info:
                            link_el.click(force=True)
                        target_page = new_page_info.value
                    except Exception:
                        target_page = page

                    target_page.wait_for_load_state("domcontentloaded")
                    target_page.on("response", handle_response)
                    time.sleep(3)

                    # 在目標頁面中尋找免費/普通下載按鈕並觸發
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
                        print("    [i] 觸發免費下載區域，等待 API 回傳真實直鏈...")
                        slow_btn.click(force=True)
                        time.sleep(6)

                    # 下載驗證邏輯
                    download_success = False
                    if captured_file_urls:
                        print(f"    [i] 成功擷取到 {len(captured_file_urls)} 個可能直鏈，開始嘗試請求...")
                        for direct_url in captured_file_urls:
                            try:
                                res = context.request.get(direct_url)
                                if res.ok:
                                    content = res.body()
                                    # 驗證內容：排除 html/css/js 網頁，確認為純文字/介面內容
                                    text_preview = content[:500].decode("utf-8", errors="ignore")
                                    if "<html" not in text_preview.lower() and "<!doctype" not in text_preview.lower():
                                        if len(content) <= MAX_FILE_SIZE:
                                            fname = f"file_{idx}.txt"
                                            save_path = os.path.join(DOWNLOAD_DIR, fname)
                                            with open(save_path, "wb") as f:
                                                f.write(content)
                                            print(f"    [✓] 成功下載正確檔案: downloads/{fname} (大小: {len(content)/1024:.2f} KB)")
                                            download_success = True
                                            break
                            except Exception:
                                continue

                    if not download_success:
                        print("    [X] 未能取得有效的檔案內容，儲存截圖備查...")
                        target_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
                else:
                    print("    [-] 未找到有效檔案項目")

            except Exception as e:
                print(f"    [X] 執行過程出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
