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
                time.sleep(5)  # 等待前端動態渲染

                # 抓取所有項目行
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
                    print("    [i] 點擊進入檔案詳情...")
                    item_element.click(force=True)
                    time.sleep(5)

                    # 收集主頁面與所有 iframe 框架
                    frames = [page] + page.frames
                    target_btn = None

                    # 尋找第一層按鈕（進入下載頁或開啟下載對話框）
                    for frame in frames:
                        try:
                            locator = frame.locator("a, button, div, span").filter(
                                has_text=re.compile(r"普通下載|免費下載|Free Download|立即下載|下載", re.I)
                            )
                            for i in range(locator.count()):
                                loc = locator.nth(i)
                                if loc.is_visible():
                                    target_btn = loc
                                    break
                            if target_btn:
                                break
                        except Exception:
                            continue

                    if target_btn:
                        print("    [i] 點擊初級下載按鈕...")
                        # 先嘗試無 expect_download 點擊，看看是否會跳轉或開啟彈窗
                        target_btn.click(force=True)
                        time.sleep(5)

                        # 更新最新頁面與框架資訊
                        active_pages = context.pages
                        current_page = active_pages[-1] if active_pages else page
                        all_frames = [current_page] + current_page.frames

                        # 嘗試尋找終極下載按鈕/直鏈
                        final_btn = None
                        for frame in all_frames:
                            try:
                                locs = frame.locator("a, button").filter(
                                    has_text=re.compile(r"普通下載|點擊下載|立即下載|下載地址", re.I)
                                )
                                for i in range(locs.count()):
                                    loc = locs.nth(i)
                                    if loc.is_visible():
                                        final_btn = loc
                                        break
                                if final_btn:
                                    break
                            except Exception:
                                continue

                        # 如果沒找到特別的終極按鈕，就退回原本的 target_btn
                        btn_to_click = final_btn if final_btn else target_btn

                        print("    [i] 嘗試觸發最終檔案下載...")
                        try:
                            with current_page.expect_download(timeout=15000) as download_info:
                                btn_to_click.click(force=True)
                            
                            download = download_info.value
                            save_path = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
                            download.save_as(save_path)
                            print(f"    [✓] 已成功下載最新檔案至: downloads/{download.suggested_filename}")

                        except Exception as dl_err:
                            print(f"    [!] 未觸發原生下載流 ({dl_err})，嘗試掃描頁面中的下載 URL/直鏈...")
                            # 備用方案：尋找頁面上包含 down, file, ctdisk 等關鍵字的 href 連結
                            href_links = current_page.eval_on_selector_all(
                                "a[href]",
                                "elements => elements.map(e => e.href)"
                            )
                            download_url = None
                            for href in href_links:
                                if any(k in href.lower() for k in ["/down/", "/file/", "down_file", "ctfile"]):
                                    download_url = href
                                    break

                            if download_url:
                                print(f"    [i] 找到潛在下載直鏈: {download_url}，透過 APIRequest 進行下載...")
                                response = context.request.get(download_url)
                                if response.ok:
                                    # 從 Content-Disposition 標頭解析檔名或使用預設檔名
                                    cd = response.headers.get("content-disposition", "")
                                    filename = "downloaded_file"
                                    if "filename=" in cd:
                                        filename = re.findall(r'filename="?([^";]+)"?', cd)[0]
                                    else:
                                        filename = f"file_{idx}.zip"
                                    
                                    save_path = os.path.join(DOWNLOAD_DIR, filename)
                                    with open(save_path, "wb") as f:
                                        f.write(response.body())
                                    print(f"    [✓] 已成功經由直鏈下載檔案至: downloads/{filename}")
                                else:
                                    print(f"    [X] 直鏈請求失敗，HTTP 狀態碼: {response.status}")
                            else:
                                print("    [X] 無法捕獲檔案下載流或下載直鏈。")
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
