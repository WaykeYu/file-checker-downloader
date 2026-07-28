import os
import re
import json
import requests
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

URLS = [
    "https://url55.ctfile.com/d/172955-2339886-8818eb?p=197222&d=2339886&fk=16adba",
    "https://url55.ctfile.com/d/172955-5565970-4df5fd?p=197222&d=5565970&fk=b89d4d"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://url55.ctfile.com/"
}

def is_valid_content(content):
    """確認下載到的內容是真實介面文字（非 HTML 網頁）"""
    if not content or len(content) < 10:
        return False
    head = content[:500].decode("utf-8", errors="ignore").strip().lower()
    if "<html" in head or "<!doctype" in head or "404 not found" in head:
        return False
    return True

def download_ctfile(url, idx):
    session = requests.Session()
    session.headers.update(HEADERS)

    parsed_url = urlparse(url)
    qs = parse_qs(parsed_url.query)
    passcode = qs.get("p", [""])[0]
    folder_id = qs.get("d", [""])[0]

    print(f"[{idx}/{len(URLS)}] 讀取城通連結 (Passcode: {passcode}, Folder: {folder_id})...")

    # Step 1: 訪問主要入口頁面以拿取 Cookies & 頁面原始碼
    resp = session.get(url, timeout=15)
    html = resp.text

    # 從頁面尋找 file_id, userid, chk 或 ajax 端點
    file_ids = re.findall(r'file_id\s*[:=]\s*["\']?(\d+)["\']?', html)
    uids = re.findall(r'uid\s*[:=]\s*["\']?(\d+)["\']?', html) or re.findall(r'userid\s*[:=]\s*["\']?(\d+)["\']?', html)
    chks = re.findall(r'chk\s*[:=]\s*["\']?([a-f0-9]+)["\']?', html)

    # 如果沒撈到 file_id，嘗試匹配鏈接格式
    if not file_ids:
        file_ids = re.findall(r'/file/172955-(\d+)', html) or re.findall(r'172955-(\d+)', url)

    file_id = file_ids[0] if file_ids else folder_id
    uid = uids[0] if uids else "172955"
    chk = chks[0] if chks else ""

    print(f"    [i] 解析到參數 -> File ID: {file_id}, UID: {uid}")

    # Step 2: 發送 API 請求獲取直鏈
    # 城通常見的 API 介面路徑組合
    api_urls = [
        f"https://url55.ctfile.com/ajax.php?action=get_file_url&uid={uid}&fid={file_id}&p={passcode}&chk={chk}",
        f"https://webapi.ctfile.com/get_file_url.php?uid={uid}&fid={file_id}&p={passcode}",
        f"https://url55.ctfile.com/get_file_url.php?uid={uid}&fid={file_id}&p={passcode}"
    ]

    direct_url = None

    for api in api_urls:
        try:
            r = session.get(api, timeout=10)
            if r.status_code == 200:
                try:
                    res_json = r.json()
                    if res_json.get("code") == 200 or "downurl" in res_json or "file_url" in res_json:
                        direct_url = res_json.get("downurl") or res_json.get("file_url")
                        if direct_url:
                            print("    [✓] 成功透過城通 API 換取直鏈！")
                            break
                except Exception:
                    # 嘗試從純文字正文尋找 down.ctfile.com 網址
                    urls = re.findall(r'https?://[^\s"\']+\.ctfile\.com[^\s"\']*', r.text)
                    if urls:
                        direct_url = urls[0].replace('\\/', '/')
                        break
        except Exception:
            continue

    # Step 3: 如果 API 沒拿到，嘗試從頁面中 regex 抓取硬編碼直鏈
    if not direct_url:
        page_urls = re.findall(r'https?://[^\s"\']+\.ctfile\.com/down/[^\s"\']*', html)
        if page_urls:
            direct_url = page_urls[0]

    # Step 4: 下載並驗證檔案內容
    if direct_url:
        try:
            print(f"    [i] 正在下載檔案正文...")
            file_resp = session.get(direct_url, timeout=20)
            if file_resp.status_code == 200 and is_valid_content(file_resp.content):
                fname = f"file_{idx}.txt"
                save_path = os.path.join(DOWNLOAD_DIR, fname)
                with open(save_path, "wb") as f:
                    f.write(file_resp.content)
                size_kb = len(file_resp.content) / 1024
                print(f"    [✓] 成功寫入檔案: downloads/{fname} ({size_kb:.2f} KB)")
                return True
            else:
                print("    [X] 下載內容無效（為網頁原始碼或已失效）")
        except Exception as e:
            print(f"    [X] 下載發送失敗: {e}")
    else:
        print("    [X] 無法解析到有效的下載 API 直鏈")

    return False

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Pure API Request Mode ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}\n")

    for idx, url in enumerate(URLS, start=1):
        success = download_ctfile(url, idx)
        if not success:
            print("    [-] 該連結下載失敗。")
        print("-" * 50)

    print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
