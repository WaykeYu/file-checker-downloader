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
    print(" File Checker & Downloader - Interactive Fallback Version ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-popup-blocking",
                "--disable-extensions"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            accept_downloads=True
        )

        for idx, url in enumerate(URLS, start=1):
            download_objs = []
            
            def on_download(download):
                download_objs.append(download)

            context.on("download", on_download)
            page = context.new_page()
            print(f"[{idx}/{len(URLS)}] 正在讀取網址: {url}")
            
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                time.sleep(3)

                # 尋找最新檔案項目
                items = page.query_selector_all("table tbody tr, .file-list-item, tr")
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
                        latest_target = {"item": link_first, "date_str": "第一筆資料"}

                if latest_target:
                    item_element = latest_target["item"]
                    link_el = item_element.query_selector("a") or item_element

                    # 處理跳轉頁面
                    try:
                        with context.expect_page(timeout=5000) as new_page_info:
                            link_el.click(force=True)
                        target_page = new_page_info.value
                    except Exception:
                        target_page = page

                    target_page.wait_for_load_state("domcontentloaded")
                    time.sleep(3)

                    # 尋找免費下載按鈕
                    active_frames = [target_page] + target_page.frames
                    slow_btn = None
                    for frame in active_frames:
                        try:
                            locs = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"Slow download|普通下載|免費下載|普通下载", re.I)
                            )
                            for i in range(locs.count()):
                                btn = locs.nth(i)
                                if btn.is_visible() and not any(k in btn.inner_text() for k in ["客戶端", "客户端", "高速", "極速"]):
                                    slow_btn = btn
                                    break
                            if slow_btn:
                                break
                        except Exception:
                            continue

                    if slow_btn:
                        print("    [i] 找到普通下載按鈕，準備觸發...")
                        
                        # 點擊並等待可能產生的 Popup 或頁面更新
                        try:
                            with context.expect_page(timeout=4000) as p_info:
                                slow_btn.click(force=True)
                            dl_page = p_info.value
                        except Exception:
                            dl_page = target_page

                        print("    [i] 等待倒數計時 (8 秒)...")
                        time.sleep(8)

                        # 在所有可能的 Frame 中尋找真正的下載按鈕或 direct url
                        all_target_frames = [dl_page] + dl_page.frames
                        
                        # 嘗試點擊倒數完畢後的下載按鈕
                        for frame in all_target_frames:
                            try:
                                clickables = frame.locator("a, button, div.btn").filter(
                                    has_text=re.compile(r"Download|普通下載|直接下載|立即下載|下载", re.I)
                                )
                                for i in range(clickables.count()):
                                    el = clickables.nth(i)
                                    if el.is_visible():
                                        el.click(force=True)
                                        time.sleep(2)
                            except Exception:
                                continue

                        time.sleep(4)

                        success = False

                        # 1. 檢查 Playwright 是否捕捉到 download 事件
                        if download_objs:
                            dl = download_objs[-1]
                            suggested_name = dl.suggested_filename
                            if not any(suggested_name.lower().endswith(ext) for ext in [".exe", ".dmg", ".apk", ".msi"]):
                                fname = f"file_{idx}.txt"
                                save_path = os.path.join(DOWNLOAD_DIR, fname)
                                dl.save_as(save_path)

                                file_size = os.path.getsize(save_path)
                                if file_size <= MAX_FILE_SIZE:
                                    print(f"    [✓] 下載成功: downloads/{fname} ({file_size/1024:.2f} KB)")
                                    success = True
                                else:
                                    os.remove(save_path)

                        # 2. 備援方案：自動掃描 DOM 內部鏈接或 HTML 中的直鏈
                        if not success:
                            print("    [i] 嘗試頁面 DOM 鏈接提取...")
                            page_content = dl_page.content()
                            urls = re.findall(r'https?://[^\s"\']+\.ctfile\.com/down/[^\s"\']*', page_content)
                            
                            if not urls:
                                # 找尋含有 down 的 a 標籤 href
                                links = dl_page.query_selector_all("a[href*='down'], a[href*='file']")
                                for l in links:
                                    href = l.get_attribute("href")
                                    if href and "ctfile.com" in href:
                                        urls.append(href)

                            for download_url in urls:
                                try:
                                    res = context.request.get(download_url)
                                    if res.ok:
                                        body = res.body()
                                        head_text = body[:300].decode("utf-8", errors="ignore").lower()
                                        if "<html" not in head_text and "<!doctype" not in head_text:
                                            if 10 < len(body) <= MAX_FILE_SIZE:
                                                fname = f"file_{idx}.txt"
                                                save_path = os.path.join(DOWNLOAD_DIR, fname)
                                                with open(save_path, "wb") as f:
                                                    f.write(body)
                                                print(f"    [✓] DOM 鏈接提取成功: downloads/{fname} ({len(body)/1024:.2f} KB)")
                                                success = True
                                                break
                                except Exception:
                                    continue

                        if not success:
                            print("    [X] 無法完成下載，已儲存除錯截圖...")
                            dl_page.screenshot(path=os.path.join(BASE_DIR, f"error_url_{idx}.png"))
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
