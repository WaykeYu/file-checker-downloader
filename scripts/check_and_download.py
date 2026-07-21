import os
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 1. 自動定位專案根目錄與 downloads/ 資料夾
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

                # 讀取檔案列表項目
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
                    item = latest_target["item"]
                    link = item.query_selector("a")
                    
                    if link:
                        print("    [i] 嘗試開啟檔案詳情...")
                        
                        # 處理點擊後可能開啟新分頁 (Popup) 的情況
                        with context.expect_page(timeout=5000) as page_info:
                            link.click(force=True)
                        try:
                            target_page = page_info.value
                            target_page.wait_for_load_state("domcontentloaded")
                        except Exception:
                            # 若未開新分頁，則留在當前頁面
                            target_page = page

                        time.sleep(3)

                        # 尋找「普通下載」按鈕
                        download_btn = target_page.query_selector("text=/普通下載|免費下載|Free Download/i")
                        if not download_btn:
                            download_btn = target_page.query_selector(".btn-free, .btn-primary, button")

                        if download_btn:
                            print("    [i] 找到下載按鈕，執行強制點擊觸發下載...")
                            # 捲動至按鈕位置
                            download_btn.scroll_into_view_if_needed()
                            
                            with target_page.expect_download(timeout=60000) as download_info:
                                download_btn.click(force=True)  # force=True 繞過透明遮罩或蓋板
                            
                            download = download_info.value
                            save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                            download.save_as(save_path)
                            print(f"    [✓] 已成功下載最新檔案至: downloads/{download.suggested_filename}")
                        else:
                            print("    [X] 詳情頁中未找到下載按鈕。")
                    else:
                        print("    [X] 未能在最新項目中找到檔案連結。")
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
