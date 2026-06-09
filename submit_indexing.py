import json
import os
import time
import requests
import sys
from datetime import datetime

# ==================== Google Indexing API 配置 ====================
# 你可以放多個 Service Account JSON 喺 GitHub Secrets（推薦 3-5 個先）
SERVICE_ACCOUNTS = [
    # 在 GitHub Secrets 加 GOOGLE_SERVICE_ACCOUNT_1, GOOGLE_SERVICE_ACCOUNT_2 等
    os.getenv("GOOGLE_SERVICE_ACCOUNT_1"),
    os.getenv("GOOGLE_SERVICE_ACCOUNT_2"),
    os.getenv("GOOGLE_SERVICE_ACCOUNT_3"),
    # 可以繼續加
]

current_account_idx = 0

def get_indexing_service():
    global current_account_idx
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        account_json = SERVICE_ACCOUNTS[current_account_idx]
        if not account_json:
            print(f"⚠️ Service Account {current_account_idx} is empty")
            current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
            return None
            
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(account_json)
        )
        service = build('indexing', 'v3', credentials=credentials)
        print(f"✅ Using Service Account #{current_account_idx + 1}")
        return service
    except Exception as e:
        print(f"❌ Failed to load Service Account: {e}")
        return None


def submit_to_indexing(urls):
    """提交 URLs 到 Google Indexing API"""
    if not urls:
        print("⚠️ No URLs to submit")
        return
    
    service = get_indexing_service()
    if not service:
        print("❌ No valid service account available")
        return

    success = 0
    for i, url in enumerate(urls[:200]):   # 一個 account 每日 limit ≈200
        try:
            body = {"url": url, "type": "URL_UPDATED"}
            response = service.urlNotifications().publish(body=body).execute()
            success += 1
            print(f"✅ Submitted [{i+1}/{len(urls)}]: {url}")
            time.sleep(0.5)  # 避免太快被 rate limit
        except Exception as e:
            print(f"❌ Failed to submit {url}: {e}")
            # 如果 quota 爆咗就換下一個 account
            if "quota" in str(e).lower() or "limit" in str(e).lower():
                global current_account_idx
                current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
                service = get_indexing_service()
    
    print(f"🎯 Indexing API: {success}/{len(urls)} URLs submitted successfully")


def generate_and_submit_indexing():
    print("🚀 Starting Google Indexing Submission...")
    
    CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    CLOUDFLARE_DATABASE_ID = os.environ.get("CLOUDFLARE_DATABASE_ID")
    CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not all([CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_DATABASE_ID, CLOUDFLARE_API_TOKEN]):
        print("❌ Missing Cloudflare credentials")
        return

    # 拉最近 24 小時新文章
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
        LIMIT 800
    """
    last_24h = int(time.time()) - 86400
    
    try:
        payload = {"sql": sql, "params": [last_24h]}
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        
        if resp.status_code == 200:
            results = resp.json().get("result", [{}])[0].get("results", [])
            urls = [f"https://virallnn.com/{row['url_slug']}" for row in results]
            
            print(f"📋 Found {len(urls)} new articles to submit")
            submit_to_indexing(urls)
        else:
            print(f"❌ D1 query failed: {resp.text}")
    except Exception as e:
        print(f"❌ Error during indexing process: {e}")


if __name__ == "__main__":
    generate_and_submit_indexing()
