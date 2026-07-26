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

# 安全檔案大小上限 (10 MB = 10 * 1024 * 1024 bytes)
MAX_FILE_SIZE = 10 * 1024 * 1024  

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Strict Size Filter ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}")
    print(f"[*] 限制最大檔案大小: {MAX_FILE_SIZE / (1024 * 1024)} MB\n")

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
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                # 抓取項目列表並比對最新日期 (排除極端舊年份)
                items = page.query_selector_all("tr, .file-list-item, .table-row, div.row, li")
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

                latest_target = None
                if candidates:
                    latest_target = max(candidates, key=lambda x: x["date"])
                    print(f"    [!] 成功比對到最新檔案 (更新日期: {latest_target['date_str']})")
                else:
                    link_first = page.query_selector("a[href*='/file/'], a[href*='/f/']")
                    if link_first:
                        latest_target = {"item": link_first, "date_str": "預設第一筆"}

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
                    time.sleep(5)

                    all_frames = [target_page] + target_page.frames
                    
                    # 避開「高速」、「客戶端」、「極速」等關鍵字，只選擇純「普通下載/Slow download」
                    slow_btn = None
                    for frame in all_frames:
                        try:
                            locs = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                            )
                            for i in range(locs.count()):
                                btn = locs.nth(i)
                                btn_text = btn.inner_text()
                                # 嚴格排除客戶端與高速下載
                                if btn.is_visible() and not any(k in btn_text for k in ["客戶端", "客户端", "高速", "極速", "VIP"]):
                                    slow_btn = btn
                                    break
                            if slow_btn:
                                break
                        except Exception:
                            continue

                    if slow_btn:
                        print(f"    [i] 成功鎖定純文字/普通下載按鈕: [{slow_btn.inner_text().strip()}]")
                        
                        download_events = []
                        target_page.on("download", lambda d: download_events.append(d))

                        slow_btn.click(force=True)
                        time.sleep(3)

                        # 處理二次彈窗（若有）
                        for frame in all_frames:
                            try:
                                confirm_btns = frame.locator("a, button, div, span").filter(
                                    has_text=re.compile(r"^Download$|^下載$|^Slow Download$|普通下載", re.I)
                                )
                                for i in range(confirm_btns.count()):
                                    cb = confirm_btns.nth(i)
                                    cb_text = cb.inner_text()
                                    if cb.is_visible() and not any(k in cb_text for k in ["客戶端", "客户端", "高速"]):
                                        cb.click(force=True)
                                        time.sleep(1)
                            except Exception:
                                continue

                        print("    [i] 等待下載流觸發 (8 秒)...")
                        time.sleep(8)

                        if download_events:
                            dl = download_events[0]
                            suggested_name = dl.suggested_filename
                            
                            # 1. 安全檢查：副檔名過濾
                            if any(suggested_name.lower().endswith(ext) for ext in [".exe", ".dmg", ".apk", ".msi", ".zip"]):
                                print(f"    [X] 警告: 捕獲到疑為安裝包或壓縮包檔案 [{suggested_name}]，取消儲存！")
                            else:
                                fname = suggested_name if (suggested_name.endswith(".txt") or suggested_name.endswith(".json")) else f"file_{idx}.txt"
                                save_path = os.path.join(DOWNLOAD_DIR, fname)
                                dl.save_as(save_path)

                                # 2. 安全檢查：檔案大小過濾
                                file_size = os.path.getsize(save_path)
                                if file_size > MAX_FILE_SIZE:
                                    print(f"    [X] 錯誤: 下載檔案過大 ({file_size / (1024*1024):.2f} MB)，超過 {MAX_FILE_SIZE/(1024*1024)}MB 上限，已刪除該檔案！")
                                    os.remove(save_path)
                                else:
                                    print(f"    [✓] 成功下載正確檔案: downloads/{fname} (大小: {file_size / 1024:.2f} KB)")
                        else:
                            print("    [X] 點擊後未觸發合規的檔案下載")
                    else:
                        print("    [X] 未找到合規的普通下載按鈕")
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
