import os
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# 目標網址清單
URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba#/f/tempdir-VTVTY1dnCWhUYwJgU39TMAcyADRXYQszWzlYOwVpBD0AY1JlADtfNldnUSsDMwBlBT8FMFtuDj0JYVcxUzRRbw",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d#/f/tempdir-VjZQYFRkWzoBNgRmBysGZQ47U2cANgoyCGpRNVE8AT4FbFFuADIPb1pgA3lSYgRhDjQANVZjXG8AaARiB2UHMg"
]

TARGET_DATE = datetime(2026, 7, 17)
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def parse_and_download():
    with sync_playwright() as p:
        # 啟動 Headless 瀏覽器
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        for idx, url in enumerate(URLS, 1):
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                # 等待檔案列表表格載入
                page.wait_for_selector("table", timeout=15000)

                # 尋找頁面中的表格行 (依據城通網盤 HTML 結構調整選擇器)
                rows = page.query_selector_all("tr")
                print(f"找到 {len(rows)} 個項目列")

                for row in rows:
                    text_content = row.inner_text()
                    
                    # 匹配日期格式 (YYYY-MM-DD 或 YYYY/MM/DD)
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text_content)
                    if date_match:
                        date_str = date_match.group(1).replace('/', '-')
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")

                        # 判斷是否大於指定日期
                        if file_date > TARGET_DATE:
                            print(f"發現符合條件檔案 (日期: {date_str})，準備下載...")
                            
                            # 尋找該列中的下載連結或檔名點擊處
                            link = row.query_selector("a")
                            if link:
                                with page.expect_download(timeout=60000) as download_info:
                                    link.click()
                                download = download_info.value
                                save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                                download.save_as(save_path)
                                print(f"已成功下載: {download.suggested_filename}")

            except Exception as e:
                print(f"處理網址 {url} 時發生錯誤或逾時: {e}")

        browser.close()

if __name__ == "__main__":
    parse_and_download()
