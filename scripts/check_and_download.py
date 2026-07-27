import os
import re
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

# 1. 定位專案目錄與下載目錄
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 2. 目標網址
URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Countdown Handling Version ")
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
                time.sleep(5)

                # 嘗試多重選擇器抓取列表
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

                        # 等待倒數計時結束
                        print("    [i] 等待 6 秒倒數計時結束...")
                        time.sleep(6)

                        download_events = []
                        target_page.on("download", lambda d: download_events.append(d))
                        context.on("download", lambda d: download_events.append(d))

                        # 倒數結束後，再次點擊 Download 按鈕
                        clicked_final = False
                        for frame in all_frames:
                            try:
                                final_btns = frame.locator("a, button").filter(
                                    has_text=re.compile(r"^Download$|^普通下載$|^直接下載$|^下載$", re.I)
                                )
                                for i in range(final_btns.count()):
                                    fb = final_btns.nth(i)
                                    if fb.is_visible():
                                        print("    [i] 點擊倒數結束後的真正下載按鈕...")
                                        fb.click(force=True)
                                        clicked_final = True
                                        break
                                if clicked_final:
                                    break
                            except Exception:
                                continue

                        if not clicked_final:
                            print("    [i] 再次點擊主下載按鈕...")
                            slow_btn.click(force=True)

                        print("    [i] 等待網絡下載流回應 (6 秒)...")
                        time.sleep(6)

                        if download_events:
                            dl = download_events[0]
                            suggested_name = dl.suggested_filename
                            
                            if any(suggested_name.lower().endswith(ext) for ext in [".exe", ".dmg", ".apk", ".msi", ".zip"]):
                                print(f"    [X] 拒絕非目標檔案格式: {suggested_name}")
                            else:
                                fname = suggested_name if (suggested_name.endswith(".txt") or suggested_name.endswith(".json")) else f"file_{idx}.txt"
                                save_path = os.path.join(DOWNLOAD_DIR, fname)
                                dl.save_as(save_path)

                                file_size = os.path.getsize(save_path)
                                if file_size > MAX_FILE_SIZE:
                                    print(f"    [X] 檔案容量過大 ({file_size/(1024*1024):.2f}MB)，自動清除！")
                                    os.remove(save_path)
                                else:
                                    print(f"    [✓] 成功取得目標檔案: downloads/{fname} ({file_size/1024:.2f} KB)")
                        else:
                            print("    [X] 倒數後點擊仍未發送下載流，截圖備查...")
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
