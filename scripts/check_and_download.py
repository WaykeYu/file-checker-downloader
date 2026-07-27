import os
import re
import time
import json
from datetime import datetime
from playwright.sync_api import sync_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Strict Direct File Download ")
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
            captured_file_urls = []

            # 監聽背景網路請求，撈出真實 CDN 網址 (如 down.ctfile.com / file)
            def handle_response(response):
                try:
                    res_url = response.url
                    # 當城通網盤回應 get_file 或直鏈 API 時
                    if any(k in res_url for k in ["get_file", "file_info", "down.ctfile"]):
                        if response.status == 200:
                            ct = response.headers.get("content-type", "")
                            # 如果回傳是 JSON / 內文，試著尋找裡面的下載網址
                            if "json" in ct or "text" in ct:
                                text = response.text()
                                matches = re.findall(r'https?://[^\s"\']+\.ctfile\.com[^\s"\']*', text)
                                for m in matches:
                                    clean_m = m.replace('\\/', '/')
                                    if clean_m not in captured_file_urls and not clean_m.endswith(('.css', '.js', '.png', '.jpg')):
                                        captured_file_urls.append(clean_m)
                            # 如果直接觸發了重定向/下載流
                            elif "octet-stream" in ct or "attachment" in response.headers.get("content-disposition", ""):
                                if res_url not in captured_file_urls:
                                    captured_file_urls.append(res_url)
                except Exception:
                    pass

            page.on("response", handle_response)
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                # 比對最新日期項目
                items = page.query_selector_all("table tbody tr, .file-list-item, div.row, li")
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

                latest_target = max(candidates, key=lambda x: x["date"]) if candidates else None
                
                if not latest_target:
                    link_first = page.query_selector("a[href*='/file/'], a[href*='/f/'], table tbody tr a")
                    if link_first:
                        latest_target = {"item": link_first, "date_str": "預設第一筆項目"}

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
                    time.sleep(3)

                    # 尋找普通下載按鈕
                    slow_btn = None
                    for frame in [target_page] + target_page.frames:
                        try:
                            locs = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                            )
                            for i in range(locs.count()):
                                btn = locs.nth(i)
                                btn_text = btn.inner_text()
                                if btn.is_visible() and not any(k in btn_text for k in ["客戶端", "客户端", "高速", "極速"]):
                                    slow_btn = btn
                                    break
                            if slow_btn:
                                break
                        except Exception:
                            continue

                    if slow_btn:
                        print("    [i] 點擊普通下載，等待倒數與網路事件...")
                        slow_btn.click(force=True)
                        time.sleep(6)  # 等待 6 秒倒數結束

                        # 倒數結束後再次點擊真正的下載鏈接
                        for frame in [target_page] + target_page.frames:
                            try:
                                final_btns = frame.locator("a, button").filter(
                                    has_text=re.compile(r"^Download$|^普通下載$|^直接下載$|^下載$", re.I)
                                )
                                for i in range(final_btns.count()):
                                    if final_btns.nth(i).is_visible():
                                        final_btns.nth(i).click(force=True)
                                        break
                            except Exception:
                                continue

                        time.sleep(5)

                    # 內容驗證與存檔
                    download_success = False
                    if captured_file_urls:
                        print(f"    [i] 捕捉到 {len(captured_file_urls)} 個可能直鏈，進行內容過濾與驗證...")
                        for direct_url in captured_file_urls:
                            try:
                                res = context.request.get(direct_url)
                                if res.ok:
                                    content = res.body()
                                    
                                    # 關鍵點：內容過濾（確保不是 HTML 網頁）
                                    text_head = content[:500].decode("utf-8", errors="ignore").lower()
                                    if "<html" in text_head or "<!doctype" in text_head or "<head" in text_head:
                                        continue  # 忽略 HTML 網頁

                                    if 10 < len(content) <= MAX_FILE_SIZE:
                                        fname = f"file_{idx}.txt"
                                        save_path = os.path.join(DOWNLOAD_DIR, fname)
                                        with open(save_path, "wb") as f:
                                            f.write(content)
                                        print(f"    [✓] 成功下載正確檔案內容: downloads/{fname} (大小: {len(content)/1024:.2f} KB)")
                                        download_success = True
                                        break
                            except Exception:
                                continue

                    if not download_success:
                        print("    [X] 未能取得正確的檔案內容，儲存截圖備查...")
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
