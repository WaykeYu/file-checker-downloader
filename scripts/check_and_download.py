import os
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 1. 定位專案根目錄與 downloads/ 資料夾
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 2. 目標網址清單
URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Always Get Latest File ")
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
        page = context.new_page()

        for idx, url in enumerate(URLS, start=1):
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(5)  # 等待前端動態渲染

                # 抓取所有項目行
                items = page.query_selector_all("tr, .file-list-item, .table-row, div.row")
                if not items:
                    items = page.query_selector_all("div, li")

                candidates = []
                for item in items:
                    text_content = item.inner_text()
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text_content)
                    if date_match:
                        date_str = date_match.group(1).replace('/', '-')
                        try:
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                            candidates.append({
                                "item": item,
                                "date": file_date,
                                "date_str": date_str
                            })
                        except ValueError:
                            continue

                latest_target = None
                if candidates:
                    latest_target = max(candidates, key=lambda x: x["date"])
                    print(f"    [!] 成功比對到最新檔案 (更新日期: {latest_target['date_str']})")
                elif items:
                    latest_target = {"item": items[-1], "date_str": "未知/最新順序"}
                    print("    [!] 未偵測到明確日期格式，取列表中最後一個項目...")

                if latest_target:
                    item_element = latest_target["item"]
                    print("    [i] 點擊檔案項目（於原頁面載入）...")
                    
                    # 直接在原頁面點擊，不等待新分頁
                    item_element.click(force=True)
                    time.sleep(5)  # 等待進入詳情頁或內容刷新

                    # 收集主頁面與所有 iframe 框架
                    frames = [page] + page.frames
                    target_btn = None

                    print(f"    [i] 正在掃描 {len(frames)} 個頁面框架 (Frames)...")
                    for frame in frames:
                        try:
                            locator = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"普通下載|免費下載|Free Download|立即下載|下載", re.I)
                            )
                            for i in range(locator.count()):
                                loc = locator.nth(i)
                                if loc.is_visible():
                                    target_btn = loc
                                    break
                            if target_btn:
                                break
                        except Exception:
                            continue

                    if target_btn:
                        print("    [i] 成功找到可見的下載按鈕，執行下載...")
                        with page.expect_download(timeout=60000) as download_info:
                            target_btn.click(force=True)
                        
                        download = download_info.value
                        save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                        download.save_as(save_path)
                        print(f"    [✓] 已成功下載最新檔案至: downloads/{download.suggested_filename}")
                    else:
                        print("    [X] 所有框架中皆未找到可見的下載按鈕。")
                else:
                    print("    [-] 該頁面未找到任何檔案項目。")

            except Exception as e:
                print(f"    [X] 處理網址時發生錯誤: {e}")
                screenshot_path = os.path.join(BASE_DIR, f"error_url_{idx}.png")
                page.screenshot(path=screenshot_path)
                print(f"    [i] 已將錯誤畫面存為截圖: {screenshot_path}")

            print("-" * 50)

        browser.close()
        print("\n[*] 檢查與下載任務執行完成。")

if __name__ == "__main__":
    check_and_download()
