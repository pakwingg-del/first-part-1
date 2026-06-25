import json
import os
import time
import requests
import sys
from datetime import datetime

# ====================== Google Indexing API 配置 ======================
# 支援 6 個 Service Account (必須來自 6 個不同的 GCP Projects)
SERVICE_ACCOUNTS = [
    os.getenv("GOOGLE_SERVICE_ACCOUNT_1"),
    os.getenv("GOOGLE_SERVICE_ACCOUNT_2"),
    os.getenv("GOOGLE_SERVICE_ACCOUNT_3"),
    os.getenv("GOOGLE_SERVICE_ACCOUNT_4"),
    os.getenv("GOOGLE_SERVICE_ACCOUNT_5"),
    os.getenv("GOOGLE_SERVICE_ACCOUNT_6"),
]

current_account_idx = 0

def get_indexing_service():
    global current_account_idx
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        # 輪流檢查並使用有效嘅 account
        for _ in range(len(SERVICE_ACCOUNTS)):
            account_json = SERVICE_ACCOUNTS[current_account_idx]
            if account_json and account_json.strip():
                credentials = service_account.Credentials.from_service_account_info(
                    json.loads(account_json)
                )
                service = build('indexing', 'v3', credentials=credentials)
                print(f"✅ Using Service Account #{current_account_idx + 1}")
                return service
            
            # 如果呢個 account 無內容，就直接跳下一個
            current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
        
        print("❌ No valid Service Account found!")
        return None
    except Exception as e:
        print(f"❌ Failed to load Service Account #{current_account_idx + 1}: {e}")
        # 載入失敗也必須移到下一個，避免卡死
        current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
        return None


def submit_to_indexing(urls):
    """提交 URLs 到 Google Indexing API"""
    global current_account_idx
    if not urls:
        print("⚠️ No URLs to submit")
        return

    service = get_indexing_service()
    if not service:
        print("❌ No valid service account available")
        return

    success = 0
    submitted_count = 0

    for i, url in enumerate(urls):
        try:
            body = {"url": url, "type": "URL_UPDATED"}
            response = service.urlNotifications().publish(body=body).execute()
            success += 1
            submitted_count += 1
            print(f"✅ Submitted [{submitted_count}/{len(urls)}]: {url}")
            
            # 【修正】：每到 180 個換下一個 Account 時，手動將 index 移至下一個獨立 Project
            if submitted_count % 180 == 0 and submitted_count < len(urls):
                print("🔄 Reached 180 URLs limit for this project. Switching to next Project...")
                current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
                service = get_indexing_service()
                if not service:
                    print("⚠️ Switch failed, stopping process.")
                    break
                
            time.sleep(0.4)  # 避免瞬時頻率過快爆 Rate Limit
            
        except Exception as e:
            error_str = str(e).lower()
            print(f"❌ Failed {url}: {e}")
            
            # 【修正】：遇到 Quota 上限（如 429 錯誤），即時切換到下一個獨立 Project
            if "quota" in error_str or "limit" in error_str or "permission" in error_str:
                print("🔄 Quota exceeded or error met. Switching to next Project...")
                current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
                service = get_indexing_service()
                if not service:
                    print("⚠️ No more service accounts available after error.")
                    break
            time.sleep(1)

    print(f"🎯 Indexing API Complete: {success} URLs submitted successfully")


def generate_and_submit_indexing():
    print("🚀 Starting Google Indexing Submission (6 Accounts)...")
   
    CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    CLOUDFLARE_DATABASE_ID = os.environ.get("CLOUDFLARE_DATABASE_ID")
    CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not all([CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_DATABASE_ID, CLOUDFLARE_API_TOKEN]):
        print("❌ Missing Cloudflare credentials")
        return

    # 拉最近 48 小時文章
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{CLOUDFLARE_DATABASE_ID}/query"
    
    sql = """
        SELECT url_slug, created_at 
        FROM articles 
        WHERE created_at >= ? 
        ORDER BY created_at DESC 
        LIMIT 1200
    """
    last_48h = int(time.time()) - 172800   # 48小時
    
    try:
        payload = {"sql": sql, "params": [last_48h]}
        resp = requests.post(url, headers=headers, json=payload, timeout=25)
        
        if resp.status_code == 200:
            results = resp.json().get("result", [{}])[0].get("results", [])
            urls = [f"https://virallnn.com/{row['url_slug']}" for row in results]
            
            print(f"📋 Found {len(urls)} new articles to submit to Google")
            submit_to_indexing(urls)
        else:
            print(f"❌ D1 query failed: {resp.text}")
    except Exception as e:
        print(f"❌ Error during indexing process: {e}")


if __name__ == "__main__":
    generate_and_submit_indexing()
