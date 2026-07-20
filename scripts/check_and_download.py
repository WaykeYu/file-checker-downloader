import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# 1. 定義專案根目錄與下載資料夾路徑 (downloads/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")

# 自動建立 downloads 資料夾
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 2. 設定目標網址與篩選日期條件 (2026/07/17 以後)
URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba#/f/tempdir-VTVTY1dnCWhUYwJgU39TMAcyADRXYQszWzlYOwVpBD0AY1JlADtfNldnUSsDMwBlBT8FMFtuDj0JYVcxUzRRbw",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d#/f/tempdir-VjZQYFRkWzoBNgRmBysGZQ47U2cANgoyCGpRNVE8AT4FbFFuADIPb1pgA3lSYgRhDjQANVZjXG8AaARiB2UHMg"
]

TARGET_DATE = datetime(2026, 7, 17)

def check_and_download():
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}")
    print(f"[*] 篩選日期條件: > {TARGET_DATE.strftime('%Y-%m-%d')}\n")

    with sync_playwright() as p:
        # 啟動無頭瀏覽器
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        for idx, url in enumerate(URLS, start=1):
            print(f"[{idx}/{len(URLS)}] 正在載入網址: {url}")
            try:
                # 開啟網頁並等待網路空閒
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_selector("table", timeout=20000)

                # 讀取表格項目列
                rows = page.query_selector_all("tr")
                print(f"    找到 {len(rows)} 個項目列，開始檢查更新日期...")

                for row in rows:
                    text_content = row.inner_text()

                    # 匹配日期格式 (YYYY-MM-DD 或 YYYY/MM/DD)
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text_content)
                    if date_match:
                        date_str = date_match.group(1).replace('/', '-')
                        try:
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        except ValueError:
                            continue

                        # 判斷是否符合日期條件
                        if file_date > TARGET_DATE:
                            print(f"    [!] 發現符合條件檔案 (更新日期: {date_str})")
                            
                            # 尋找下載連結並觸發下載
                            link = row.query_selector("a")
                            if link:
                                with page.expect_download(timeout=60000) as download_info:
                                    link.click()
                                download = download_info.value
                                
                                # 存入 downloads/ 資料夾
                                save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                                download.save_as(save_path)
                                print(f"    [✓] 已成功下載至: downloads/{download.suggested_filename}")

            except Exception as e:
                print(f"    [X] 處理網址時發生錯誤或逾時: {e}")

        browser.close()
        print("\n[*] 檢查與下載流程完成。")

if __name__ == "__main__":
    check_and_download()
