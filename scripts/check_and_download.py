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
                time.sleep(4)

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

                    link_el = item_element.query_selector("a") or item_element

                    try:
                        with context.expect_page(timeout=5000) as new_page_info:
                            link_el.click(force=True)
                        target_page = new_page_info.value
                        print("    [i] 已開啟新頁籤，等待內容完全加載...")
                    except Exception:
                        target_page = page
                        print("    [i] 於原頁面進行加載...")

                    # 充分等待新頁籤的網絡發送與 DOM 渲染完成
                    try:
                        target_page.wait_for_load_state("networkidle", timeout=10000)
                    except Exception:
                        pass
                    time.sleep(6)

                    # 收集當前頁面與所有 iframe 框架
                    frames = [target_page] + target_page.frames
                    target_btn = None

                    # 1. 精準文字匹配
                    regex_pattern = re.compile(r"普通|免費|立即|下載|Free|Download", re.I)
                    for frame in frames:
                        try:
                            locs = frame.locator("a, button, div, span").filter(has_text=regex_pattern)
                            for i in range(locs.count()):
                                loc = locs.nth(i)
                                if loc.is_visible():
                                    target_btn = loc
                                    break
                            if target_btn:
                                break
                        except Exception:
                            continue

                    # 2. 備用 Selector 匹配 (萬用 class/id 檢索)
                    if not target_btn:
                        css_list = [
                            ".btn", "a.btn", "button",
                            "[class*='down']", "[id*='down']",
                            "[class*='btn']", "[id*='btn']"
                        ]
                        for frame in frames:
                            for css in css_list:
                                try:
                                    locs = frame.locator(css)
                                    for i in range(locs.count()):
                                        loc = locs.nth(i)
                                        if loc.is_visible() and len(loc.inner_text().strip()) > 0:
                                            target_btn = loc
                                            break
                                    if target_btn:
                                        break
                                except Exception:
                                    continue
                            if target_btn:
                                break

                    if target_btn:
                        btn_text = target_btn.inner_text().replace('\n', ' ').strip()
                        print(f"    [i] 成功定位下載按鈕/元素 [{btn_text}]，執行點擊...")
                        
                        try:
                            with target_page.expect_download(timeout=20000) as download_info:
                                target_btn.click(force=True)
                            
                            download = download_info.value
                            save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                            download.save_as(save_path)
                            print(f"    [✓] 已成功下載最新檔案至: downloads/{download.suggested_filename}")
                        except Exception as dl_err:
                            print(f"    [!] 點擊未觸發直接下載流 ({dl_err})，拍攝當前畫面...")
                            screenshot_path = os.path.join(BASE_DIR, f"error_url_{idx}.png")
                            target_page.screenshot(path=screenshot_path)
                    else:
                        print("    [X] 所有框架中皆未找到可見的下載按鈕。")
                        screenshot_path = os.path.join(BASE_DIR, f"error_url_{idx}.png")
                        target_page.screenshot(path=screenshot_path)
                        print(f"    [i] 已將新頁籤畫面存為截圖: {screenshot_path}")
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
