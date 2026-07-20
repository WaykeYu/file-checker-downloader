import os
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba#/f/tempdir-VTVTY1dnCWhUYwJgU39TMAcyADRXYQszWzlYOwVpBD0AY1JlADtfNldnUSsDMwBlBT8FMFtuDj0JYVcxUzRRbw",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d#/f/tempdir-VjZQYFRkWzoBNgRmBysGZQ47U2cANgoyCGpRNVE8AT4FbFFuADIPb1pgA3lSYgRhDjQANVZjXG8AaARiB2UHMg"
]

TARGET_DATE = datetime(2026, 7, 17)

def check_and_download():
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}")
    print(f"[*] 篩選日期條件: > {TARGET_DATE.strftime('%Y-%m-%d')}\n")

    with sync_playwright() as p:
        # 1. 啟用偽裝與特定屬性
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
            print(f"[{idx}/{len(URLS)}] 正在載入網址: {url}")
            try:
                # 2. 改為 domcontentloaded 避免 networkidle 永久掛起
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # 給予前端 SPA 框架 5 秒緩衝載入渲染列表
                time.sleep(5)

                # 嘗試尋找表格或列表容器
                content = page.content()

                # 若找不到表格，抓取頁面所有連結或文字區塊
                rows = page.query_selector_all("tr")
                if not rows:
                    print("    [!] 未找到 <tr> 標籤，嘗試解析通用列表項目...")
                    rows = page.query_selector_all("div, li")

                print(f"    找到 {len(rows)} 個潛在數據項目，開始分析日期...")

                found_file = False
                for row in rows:
                    text_content = row.inner_text()

                    # 尋找日期格式 (YYYY-MM-DD 或 YYYY/MM/DD)
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text_content)
                    if date_match:
                        date_str = date_match.group(1).replace('/', '-')
                        try:
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        except ValueError:
                            continue

                        if file_date > TARGET_DATE:
                            print(f"    [!] 發現符合條件檔案 (更新日期: {date_str})")
                            found_file = True
                            
                            link = row.query_selector("a")
                            if link:
                                with page.expect_download(timeout=60000) as download_info:
                                    link.click()
                                download = download_info.value
                                save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                                download.save_as(save_path)
                                print(f"    [✓] 已成功下載至: downloads/{download.suggested_filename}")

                if not found_file:
                    print("    [-] 未發現 2026-07-17 後更新的檔案。")

            except Exception as e:
                print(f"    [X] 處理網址時發生錯誤: {e}")
                # 失敗時儲存截圖，便於在 GitHub Actions Artifacts 檢查頁面狀態
                screenshot_path = os.path.join(BASE_DIR, f"error_url_{idx}.png")
                page.screenshot(path=screenshot_path)
                print(f"    [i] 已儲存錯誤畫面截圖至: {screenshot_path}")

        browser.close()
        print("\n[*] 檢查與下載流程完成。")

if __name__ == "__main__":
    check_and_download()
