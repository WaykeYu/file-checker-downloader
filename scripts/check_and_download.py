import os
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 1. 自動定位專案根目錄與 downloads/ 資料夾
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 2. 設定目標網址清單與日期過濾條件
URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba#/f/tempdir-VTVTY1dnCWhUYwJgU39TMAcyADRXYQszWzlYOwVpBD0AY1JlADtfNldnUSsDMwBlBT8FMFtuDj0JYVcxUzRRbw",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d#/f/tempdir-VjZQYFRkWzoBNgRmBysGZQ47U2cANgoyCGpRNVE8AT4FbFFuADIPb1pgA3lSYgRhDjQANVZjXG8AaARiB2UHMg",
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba"
]

TARGET_DATE = datetime(2026, 7, 17)

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}")
    print(f"[*] 篩選日期條件: > {TARGET_DATE.strftime('%Y-%m-%d')}\n")

    with sync_playwright() as p:
        # 啟動無頭 Chromium，並設定防爬偽裝參數
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
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
                # 載入網頁 DOM
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # 給予 5 秒緩衝時間供前端動態渲染列表內容
                time.sleep(5)

                # 優先比對表格或通用行容器
                items = page.query_selector_all("tr, .file-list-item, .table-row, div.row")
                if not items:
                    items = page.query_selector_all("div, li")

                print(f"    找到 {len(items)} 個資料項目，開始分析日期...")

                found_file = False
                for item in items:
                    text_content = item.inner_text()

                    # 匹配日期格式 (YYYY-MM-DD 或 YYYY/MM/DD)
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text_content)
                    if date_match:
                        date_str = date_match.group(1).replace('/', '-')
                        try:
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        except ValueError:
                            continue

                        # 判斷是否大於指定目標日期
                        if file_date > TARGET_DATE:
                            print(f"    [!] 發現符合條件檔案 (更新日期: {date_str})")
                            found_file = True
                            
                            # 尋找該項目內的下載或開啟連結
                            link = item.query_selector("a")
                            if link:
                                with page.expect_download(timeout=60000) as download_info:
                                    link.click()
                                download = download_info.value
                                
                                save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                                download.save_as(save_path)
                                print(f"    [✓] 已成功下載至: downloads/{download.suggested_filename}")

                if not found_file:
                    print(f"    [-] 未發現 {TARGET_DATE.strftime('%Y-%m-%d')} 後更新的檔案。")

            except Exception as e:
                print(f"    [X] 處理網址時發生錯誤: {e}")
                screenshot_path = os.path.join(BASE_DIR, f"error_url_{idx}.png")
                page.screenshot(path=screenshot_path)
                print(f"    [i] 已將錯誤畫面存為截圖: {screenshot_path}")

            print("-" * 50)

        browser.close()
        print("\n[*] 檢查與下載任務已執行完成。")

if __name__ == "__main__":
    check_and_download()
