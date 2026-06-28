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
    """提交 URLs 到 Google Indexing API（具備安全的專案切換與熔斷機制）"""
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
    
    # 紀錄連續因為 Quota 限制而切換失敗的次數，如果 6 個都滿了，就安全退出
    consecutive_quota_failures = 0 

    for i, url in enumerate(urls):
        # 熔斷保護：若 6 個專案全部都已耗盡配額，直接提早中斷，避免盲目狂撞
        if consecutive_quota_failures >= len(SERVICE_ACCOUNTS):
            print("🚨 [熔斷觸發] 所有 6 個 Service Accounts 的今日配額均已耗盡！程式提前結束。")
            break

        try:
            body = {"url": url, "type": "URL_UPDATED"}
            response = service.urlNotifications().publish(body=body).execute()
            
            success += 1
            submitted_count += 1
            consecutive_quota_failures = 0  # 只要成功提交一條，重置失敗計數
            print(f"✅ Submitted [{submitted_count}/{len(urls)}]: {url}")
            
            # 每成功提交 180 個換下一個 Account，平攤風險
            if submitted_count % 180 == 0 and submitted_count < len(urls):
                print("🔄 Reached 180 URLs limit for this project. Switching to next Project...")
                current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
                service = get_indexing_service()
                if not service:
                    print("⚠️ Switch failed, stopping process.")
                    break
                
            time.sleep(0.5)  # 稍微拉長間隔，對 API 更安全穩定
            
        except Exception as e:
            error_str = str(e).lower()
            print(f"❌ Failed {url}: {e}")
            
            # 判斷是否為配額超出 (429) 或權限臨時卡住 (403)
            if "quota" in error_str or "limit" in error_str or "permission" in error_str:
                consecutive_quota_failures += 1
                print(f"⚠️ Account #{current_account_idx + 1} 遇到限制 ({consecutive_quota_failures}/{len(SERVICE_ACCOUNTS)}).")
                
                if consecutive_quota_failures >= len(SERVICE_ACCOUNTS):
                    print("🚨 所有帳號皆已嘗試，全數無剩餘配額。")
                    break
                
                # 順序切換去下一個專案
                print("🔄 Switching to next Project...")
                current_account_idx = (current_account_idx + 1) % len(SERVICE_ACCOUNTS)
                service = get_indexing_service()
                if not service:
                    print("⚠️ No more service accounts available after error.")
                    break
                
                # 給予 2 秒沉澱緩衝，防止連環瞬間撞擊
                time.sleep(2)
            else:
                # 其他網絡波動等隨機錯誤，停 1 秒繼續試下一條
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
            # 🔴 修正盲點：確保 Domain 係正確的 viralnn.com (得一個 l)
            urls = [f"https://viralnn.com/{row['url_slug']}" for row in results]
            
            print(f"📋 Found {len(urls)} new articles to submit to Google")
            submit_to_indexing(urls)
        else:
            print(f"❌ D1 query failed: {resp.text}")
    except Exception as e:
        print(f"❌ Error during indexing process: {e}")


if __name__ == "__main__":
    generate_and_submit_indexing()
