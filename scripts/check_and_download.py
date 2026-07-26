import os
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Comprehensive Fix ")
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
            found_download_urls = []

            # 監聽所有網路 Response，抓取 API 回傳的真實下載直鏈
            def handle_response(response):
                try:
                    res_url = response.url
                    # 抓取 AJAX 回傳的直鏈 URL 或檔案流
                    if any(k in res_url for k in ["get_file_url", "ajax.php", "down", "ctfile.com/download"]):
                        if response.status == 200:
                            ct = response.headers.get("content-type", "")
                            if "json" in ct or "javascript" in ct or "text" in ct:
                                text = response.text()
                                # 提取 json 中的 https 鏈接
                                links = re.findall(r'https?://[^\s"\']+', text)
                                for l in links:
                                    if "ctfile" in l or "down" in l:
                                        found_download_urls.append(l.replace('\\/', '/'))
                except Exception:
                    pass

            page.on("response", handle_response)
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                # 抓取表格項目 (自動排除 2020 年以前的古舊誤匹配日期)
                items = page.query_selector_all("tr, .file-list-item, .table-row, div.row, li")

                candidates = []
                for item in items:
                    text_content = item.inner_text()
                    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', text_content)
                    if date_match:
                        date_str = date_match.group(1).replace('/', '-')
                        try:
                            file_date = datetime.strptime(date_str, "%Y-%m-%d")
                            if file_date.year >= 2020:  # 排除異常極端舊日期
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
                    # 無法透過日期比對時，嘗試獲取第一張列表的第一筆
                    link_first = page.query_selector("a[href*='/file/'], a[href*='/f/']")
                    if link_first:
                        latest_target = {"item": link_first, "date_str": "列表第一筆"}

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
                    target_page.on("response", handle_response)
                    time.sleep(5)

                    # 收集所有的 frames (包含主頁面與所有 iframe)
                    all_frames = [target_page] + target_page.frames
                    
                    # 步驟一：搜尋免費下載 / Slow Download 按鈕
                    download_btn = None
                    for frame in all_frames:
                        try:
                            btn = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载|Slow", re.I)
                            ).first
                            if btn.is_visible():
                                download_btn = btn
                                break
                        except Exception:
                            continue

                    if download_btn:
                        print("    [i] 找到免費下載按鈕，執行點擊...")
                        
                        download_events = []
                        target_page.on("download", lambda d: download_events.append(d))

                        download_btn.click(force=True)
                        time.sleep(4)

                        # 步驟二：檢查彈窗 (Modal) 或二次確認按鈕
                        for frame in all_frames:
                            try:
                                confirm_btns = frame.locator("a, button, div, span").filter(
                                    has_text=re.compile(r"Slow Download|Download|普通下載|確定|Confirm", re.I)
                                )
                                for i in range(confirm_btns.count()):
                                    cb = confirm_btns.nth(i)
                                    if cb.is_visible():
                                        cb.click(force=True)
                                        time.sleep(1)
                            except Exception:
                                continue

                        print("    [i] 等待倒數與解析真實下載鏈接 (8 秒)...")
                        time.sleep(8)

                        # 優先考量原生 Download 事件
                        if download_events:
                            dl = download_events[0]
                            fname = dl.suggested_filename if dl.suggested_filename.endswith(".txt") else f"file_{idx}.txt"
                            save_path = os.path.join(DOWNLOAD_DIR, fname)
                            dl.save_as(save_path)
                            print(f"    [✓] 成功以原生下載獲取檔案: downloads/{fname}")
                        elif found_download_urls:
                            # 使用攔截到的真實 API 直鏈進行下載
                            print(f"    [i] 捕捉到背後下載直鏈，直接發送請求請求下載...")
                            final_url = found_download_urls[-1]
                            res = context.request.get(final_url)
                            if res.ok and len(res.body()) > 200:
                                fname = f"file_{idx}.txt"
                                save_path = os.path.join(DOWNLOAD_DIR, fname)
                                with open(save_path, "wb") as f:
                                    f.write(res.body())
                                print(f"    [✓] 成功通過直鏈請求下載檔案: downloads/{fname} (大小: {len(res.body())} bytes)")
                            else:
                                print("    [X] 直鏈請求失敗或無效數據")
                        else:
                            screenshot_path = os.path.join(BASE_DIR, f"error_url_{idx}.png")
                            target_page.screenshot(path=screenshot_path)
                            print(f"    [X] 未能觸發真實檔案下載，已拍照留存: {screenshot_path}")
                    else:
                        print("    [X] 跨 Frame 搜尋仍未找到免費下載按鈕")
                        target_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
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
