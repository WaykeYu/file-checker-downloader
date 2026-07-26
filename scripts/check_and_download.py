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
    print(" File Checker & Downloader - Real File Download Version ")
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
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(3)

                # 抓取項目列表並比對最新日期
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
                    latest_target = {"item": items[-1], "date_str": "最新項目"}

                if latest_target:
                    item_element = latest_target["item"]
                    link_el = item_element.query_selector("a") or item_element

                    # 點擊開啟檔案下載主頁
                    try:
                        with context.expect_page(timeout=5000) as new_page_info:
                            link_el.click(force=True)
                        target_page = new_page_info.value
                    except Exception:
                        target_page = page

                    target_page.wait_for_load_state("domcontentloaded")
                    time.sleep(4)

                    # 定位免費下載按鈕 (Slow download / 普通下載)
                    slow_btn = target_page.locator("a, button, div, span").filter(
                        has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                    ).first

                    if slow_btn.is_visible():
                        print("    [i] 找到免費下載按鈕，準備觸發下載點擊...")

                        # 設定下載監聽容器
                        download_container = []

                        def on_download(download):
                            download_container.append(download)

                        target_page.on("download", on_download)
                        context.on("download", on_download)

                        # 第一次點擊：觸發免費下載 modal 或倒數
                        slow_btn.click(force=True)
                        time.sleep(3)

                        # 檢查頁面中是否有跳出二次確認按鈕 (例如: Download / 確定下載)
                        confirm_btn = target_page.locator("a, button, div, span").filter(
                            has_text=re.compile(r"^Download$|^下載$|^Slow Download$|普通下載", re.I)
                        ).first

                        if confirm_btn.is_visible():
                            print("    [i] 點擊二次彈窗下載確認按鈕...")
                            confirm_btn.click(force=True)

                        print("    [i] 等待伺服器產生真實檔案與下載倒數 (10 秒)...")
                        
                        # 循環等待下載事件觸發
                        for _ in range(10):
                            if download_container:
                                break
                            time.sleep(1)

                        if download_container:
                            dl = download_container[0]
                            filename = dl.suggested_filename
                            
                            # 確保副檔名為 .txt
                            if not filename.endswith(".txt"):
                                filename = f"file_{idx}.txt"

                            save_path = os.path.join(DOWNLOAD_DIR, filename)
                            dl.save_as(save_path)

                            # 驗證下載檔案大小與內容
                            file_size = os.path.getsize(save_path)
                            print(f"    [✓] 成功下載真實檔案: downloads/{filename} (大小: {file_size} bytes)")
                            
                            # 檢查下載的檔案是否為有效的接口內容 (非 HTML 網頁)
                            with open(save_path, "r", encoding="utf-8", errors="ignore") as f:
                                first_line = f.readline().strip()
                                if "<html" in first_line.lower() or "<!doctype" in first_line.lower():
                                    print("    [!] 警告: 下載到的內容為 HTML 網頁而非文本，儲存截圖進行排查...")
                                    target_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
                                else:
                                    print(f"    [i] 檔案內容開頭預覽: {first_line[:60]}...")
                        else:
                            print("    [X] 點擊後未能在預計時間內觸發檔案下載流，截圖備查...")
                            target_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
                    else:
                        print("    [X] 未定位到免費下載按鈕")
                else:
                    print("    [-] 未找到檔案項目")

            except Exception as e:
                print(f"    [X] 執行過程出錯: {e}")

            page.close()
            print("-" * 50)

        browser.close()
        print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
