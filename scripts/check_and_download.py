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
    print(" File Checker & Downloader - Network Capture Version ")
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
            captured_files = []

            # 監聽 Response，若捕捉到真正檔案發送則直接攔截儲存
            def handle_response(response):
                try:
                    headers = response.headers
                    content_disposition = headers.get("content-disposition", "")
                    content_type = headers.get("content-type", "")
                    
                    # 判斷是否為檔案下載
                    is_file = "attachment" in content_disposition or "text/plain" in content_type or "octet-stream" in content_type
                    
                    if is_file and response.status == 200:
                        filename = f"downloaded_file_{idx}.txt"
                        if "filename=" in content_disposition:
                            matched = re.findall(r'filename="?([^";]+)"?', content_disposition)
                            if matched:
                                filename = matched[0]
                        
                        body = response.body()
                        if len(body) > 100:  # 排除過小檔或錯誤頁
                            save_path = os.path.join(DOWNLOAD_DIR, filename)
                            with open(save_path, "wb") as f:
                                f.write(body)
                            captured_files.append((filename, len(body)))
                except Exception:
                    pass

            page.on("response", handle_response)

            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                # 抓取項目
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

                    # 點擊開啟詳情
                    try:
                        with context.expect_page(timeout=5000) as new_page_info:
                            link_el.click(force=True)
                        target_page = new_page_info.value
                        target_page.on("response", handle_response)
                    except Exception:
                        target_page = page

                    target_page.wait_for_load_state("domcontentloaded")
                    time.sleep(5)

                    # 尋找免費下載按鈕 (Slow download)
                    btn = target_page.locator("a, button, div").filter(
                        has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                    ).first

                    if btn.is_visible():
                        print("    [i] 點擊 [Slow Download] 免費下載按鈕...")
                        btn.click(force=True)
                        time.sleep(3)

                        # 檢查是否有二次彈窗按鈕
                        confirm_btn = target_page.locator("a, button, div").filter(
                            has_text=re.compile(r"Slow Download|Download|下載|確定|Confirm", re.I)
                        ).first
                        
                        if confirm_btn.is_visible():
                            print("    [i] 點擊彈窗確認按鈕...")
                            confirm_btn.click(force=True)

                        # 等待倒數與網路封包傳輸完成
                        print("    [i] 等待免費下載倒數 (8 秒)...")
                        time.sleep(8)

                        # 處理標準下載流 (Download event)
                        if not captured_files:
                            try:
                                with target_page.expect_download(timeout=5000) as download_info:
                                    confirm_btn.click(force=True)
                                dl = download_info.value
                                save_p = os.path.join(DOWNLOAD_DIR, dl.suggested_filename)
                                dl.save_as(save_p)
                                print(f"    [✓] 已通過原生下載捕捉至: downloads/{dl.suggested_filename}")
                            except Exception:
                                pass

                        if captured_files:
                            fname, fsize = captured_files[-1]
                            print(f"    [✓] 成功攔截網路傳輸並儲存檔案: downloads/{fname} (大小: {fsize} bytes)")
                        else:
                            print("    [X] 未能成功攔截檔案內容，拍下截圖備查...")
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
