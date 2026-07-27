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

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - API & Pop-up Handling ")
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

        # 全局下載事件監聽
        download_events = []
        captured_direct_urls = []

        def handle_download(dl):
            download_events.append(dl)

        def handle_response(response):
            try:
                res_url = response.url
                # 攔截包含下載直鏈或檔案內容的 API 響應
                if any(k in res_url for k in ["ctfile.com", "down", "file", "get_file"]):
                    ct = response.headers.get("content-type", "")
                    if "text" in ct or "json" in ct or "octet-stream" in ct:
                        body_text = response.text()
                        # 自動搜尋返回內容中的真實 CDN 下載 URL
                        urls = re.findall(r'https?://[^\s"\']+\.ctfile\.com[^\s"\']*', body_text)
                        for u in urls:
                            clean_u = u.replace('\\/', '/')
                            if clean_u not in captured_direct_urls:
                                captured_direct_urls.append(clean_u)
            except Exception:
                pass

        context.on("download", handle_download)
        
        # 當跳出 Popup/新分頁時，也幫它掛上 Response 與 Download 監聽
        def handle_new_page(new_page):
            new_page.on("download", handle_download)
            new_page.on("response", handle_response)

        context.on("page", handle_new_page)

        for idx, url in enumerate(URLS, start=1):
            download_events.clear()
            captured_direct_urls.clear()

            page = context.new_page()
            page.on("response", handle_response)
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(4)

                # 比對最新項目
                items = page.query_selector_all("tr, .file-list-item, .table-row, div.row, li, .file-item")
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
                    link_first = page.query_selector("a[href*='/file/'], a[href*='/f/'], td a, .file-name a")
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
                    time.sleep(4)

                    all_frames = [target_page] + target_page.frames
                    
                    slow_btn = None
                    for frame in all_frames:
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
                        print("    [i] 觸發免費下載區域...")
                        slow_btn.click(force=True)

                        print("    [i] 等待倒數與按鈕狀態更新 (6 秒)...")
                        time.sleep(6)

                        # 倒數結束後，嘗試多重點擊二次下載按鈕
                        for frame in all_frames:
                            try:
                                final_btns = frame.locator("a, button, div, span").filter(
                                    has_text=re.compile(r"^Download$|^普通下載$|^直接下載$|^下載$", re.I)
                                )
                                for i in range(final_btns.count()):
                                    fb = final_btns.nth(i)
                                    if fb.is_visible():
                                        fb.click(force=True)
                                        time.sleep(1)
                            except Exception:
                                continue

                        # 再次點擊原本按鈕觸發下載流程
                        try:
                            slow_btn.click(force=True)
                        except Exception:
                            pass

                        print("    [i] 等待下載事件或直鏈回應 (8 秒)...")
                        time.sleep(8)

                        success = False
                        
                        # 方案 A: Playwright 捕獲原生 Download 事件
                        if download_events:
                            dl = download_events[0]
                            suggested_name = dl.suggested_filename
                            if not any(suggested_name.lower().endswith(ext) for ext in [".exe", ".dmg", ".apk", ".msi", ".zip"]):
                                fname = suggested_name if (suggested_name.endswith(".txt") or suggested_name.endswith(".json")) else f"file_{idx}.txt"
                                save_path = os.path.join(DOWNLOAD_DIR, fname)
                                dl.save_as(save_path)

                                file_size = os.path.getsize(save_path)
                                if file_size <= MAX_FILE_SIZE:
                                    print(f"    [✓] 原生下載成功: downloads/{fname} ({file_size/1024:.2f} KB)")
                                    success = True
                                else:
                                    print(f"    [X] 檔案容量超過限制，已刪除 ({file_size/(1024*1024):.2f}MB)")
                                    os.remove(save_path)

                        # 方案 B: 使用 API 捕捉到的直鏈下載
                        if not success and captured_direct_urls:
                            print(f"    [i] 嘗試使用背景捕捉到的 API 直鏈發送下載請求...")
                            for direct_url in captured_direct_urls:
                                try:
                                    res = context.request.get(direct_url)
                                    if res.ok:
                                        body = res.body()
                                        if 10 < len(body) <= MAX_FILE_SIZE:
                                            fname = f"file_{idx}.txt"
                                            save_path = os.path.join(DOWNLOAD_DIR, fname)
                                            with open(save_path, "wb") as f:
                                                f.write(body)
                                            print(f"    [✓] API 直鏈請求成功: downloads/{fname} ({len(body)/1024:.2f} KB)")
                                            success = True
                                            break
                                except Exception:
                                    continue

                        if not success:
                            print("    [X] 未能成功獲取檔案內容，儲存截圖備查...")
                            target_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
                    else:
                        print("    [X] 未找到普通下載按鈕")
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
