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
    "Referer": "https://url55.ctfile.com/",
    "X-Requested-With": "XMLHttpRequest"
}

def is_valid_config_content(content):
    """檢查下載到的文字內容是否為有效的介面/設定檔（排除 HTML、CSS、JS）"""
    if not content or len(content) < 10:
        return False
    text = content[:1000].decode("utf-8", errors="ignore").strip().lower()
    
    # 無效類型關鍵字
    invalid_tags = ["<html", "<!doctype", "table.datatable", "function(", "var ", "streamsaver"]
    if any(tag in text for tag in invalid_tags):
        return False
    return True

def process_ctfile_folder(url, idx):
    session = requests.Session()
    session.headers.update(HEADERS)

    # 解析網址參數
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    passcode = qs.get("p", [""])[0]
    folder_id = qs.get("d", [""])[0]

    print(f"[{idx}/{len(URLS)}] 處理資料夾網址: {url}")
    print(f"    [i] Folder ID: {folder_id} | Passcode: {passcode}")

    # Step 1: 存取首頁建立 Session Cookie
    try:
        resp = session.get(url, timeout=15)
        html = resp.text
    except Exception as e:
        print(f"    [X] 連線失敗: {e}")
        return False

    # Step 2: 請求城通資料夾內部的檔案列表 API
    # 城通網盤資料夾 API 格式
    folder_api_urls = [
        f"https://webapi.ctfile.com/get_folder_file_list.php?uid=172955&fid={folder_id}&p={passcode}",
        f"https://url55.ctfile.com/ajax.php?action=get_folder_file_list&uid=172955&fid={folder_id}&p={passcode}"
    ]

    file_ids = []
    for api_url in folder_api_urls:
        try:
            r = session.get(api_url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                # 解析檔案列表中最新的檔案 fid
                files = data.get("file_list") or data.get("files") or data.get("aaData") or []
                for f in files:
                    if isinstance(f, dict):
                        fid = f.get("file_id") or f.get("fid") or f.get("id")
                        if fid:
                            file_ids.append(str(fid))
                    elif isinstance(f, list) and len(f) > 0:
                        # 部分 DataTables 回傳格式
                        fid_match = re.findall(r'\d+', str(f[0]))
                        if fid_match:
                            file_ids.append(fid_match[0])
                if file_ids:
                    break
        except Exception:
            continue

    # 如果 API 沒拿到，退回用 Regex 解析 HTML 內的 file_id
    if not file_ids:
        file_ids = re.findall(r'file_id\s*[:=]\s*["\']?(\d+)["\']?', html) or re.findall(r'/file/172955-(\d+)', html)

    if not file_ids:
        print("    [X] 無法解析到資料夾內的檔案 ID (File ID)")
        return False

    target_fid = file_ids[0]
    print(f"    [i] 成功鎖定目標檔案 ID: {target_fid}")

    # Step 3: 使用 File ID + Passcode 換取直鏈
    link_api_urls = [
        f"https://webapi.ctfile.com/get_file_url.php?uid=172955&fid={target_fid}&p={passcode}",
        f"https://url55.ctfile.com/ajax.php?action=get_file_url&uid=172955&fid={target_fid}&p={passcode}"
    ]

    direct_url = None
    for l_api in link_api_urls:
        try:
            res = session.get(l_api, timeout=10)
            if res.status_code == 200:
                j_data = res.json()
                direct_url = j_data.get("downurl") or j_data.get("file_url")
                if direct_url:
                    break
        except Exception:
            continue

    if not direct_url:
        print("    [X] 換取直鏈失敗（城通防刷或驗證碼觸發）")
        return False

    # Step 4: 直接存取直鏈下載檔案內容
    print(f"    [i] 取得直鏈成功，正在下載檔案內容...")
    try:
        file_res = session.get(direct_url, timeout=20)
        if file_res.status_code in [200, 206]:
            content = file_res.content
            if is_valid_config_content(content):
                fname = f"file_{idx}.txt"
                save_path = os.path.join(DOWNLOAD_DIR, fname)
                with open(save_path, "wb") as f:
                    f.write(content)
                size_kb = len(content) / 1024
                print(f"    [✓] 下載成功！檔案已存至: downloads/{fname} ({size_kb:.2f} KB)")
                return True
            else:
                print("    [X] 下載內容無效（抓取到 CSS/HTML 網頁而非設定檔）")
        else:
            print(f"    [X] HTTP 請求失敗: Status {file_res.status_code}")
    except Exception as e:
        print(f"    [X] 下載過程發生錯誤: {e}")

    return False

def check_and_download():
    print("=" * 60)
    print(" File Checker & Downloader - Pure Direct API ")
    print("=" * 60)
    print(f"[*] 下載目標目錄: {DOWNLOAD_DIR}\n")

    for idx, url in enumerate(URLS, start=1):
        success = process_ctfile_folder(url, idx)
        if not success:
            print("    [-] 該連結處理失敗。")
        print("-" * 50)

    print("\n[*] 任務執行完畢。")

if __name__ == "__main__":
    check_and_download()
