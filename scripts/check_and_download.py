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
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # 抓取所有檔案項目
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
                    print("    [i] 嘗試點擊檔案連結...")

                    # 嘗試優先尋找內部 <a> 標籤
                    link_el = item_element.query_selector("a") or item_element

                    # 處理可能觸發的新頁籤
                    try:
                        with context.expect_page(timeout=4000) as new_page_info:
                            link_el.click(force=True)
                        target_page = new_page_info.value
                        print("    [i] 已開啟新頁籤進行載入...")
                    except Exception:
                        target_page = page
                        print("    [i] 於原頁面進行載入...")

                    target_page.wait_for_load_state("domcontentloaded")
                    time.sleep(5)

                    # 收集當前頁面與所有 iframe 框架
                    frames = [target_page] + target_page.frames
                    target_btn = None

                    # 定義常見的城通網盤下載按鈕選擇器與關鍵字
                    selectors = [
                        "a:has-text('普通下載')",
                        "button:has-text('普通下載')",
                        "a:has-text('免費下載')",
                        "button:has-text('免費下載')",
                        ".btn-outline-primary",
                        "#free_down_link",
                        ".download-btn",
                        "a[href*='down']"
                    ]

                    for frame in frames:
                        for sel in selectors:
                            try:
                                loc = frame.locator(sel).first
                                if loc.is_visible():
                                    target_btn = loc
                                    break
                            except Exception:
                                continue
                        if target_btn:
                            break

                    if target_btn:
                        print("    [i] 成功定位下載按鈕，執行下載作業...")
                        try:
                            with target_page.expect_download(timeout=30000) as download_info:
                                target_btn.click(force=True)
                            
                            download = download_info.value
                            save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                            download.save_as(save_path)
                            print(f"    [✓] 已成功下載最新檔案至: downloads/{download.suggested_filename}")
                        except Exception as dl_err:
                            print(f"    [!] 點擊後未直接觸發下載流 ({dl_err})，嘗試二次驗證與連結抓取...")
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
