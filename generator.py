import json
import os
import time
import requests
import sys
import re
from datetime import datetime
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

# ====================== 配置 ======================
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

# Persona Matrix（保持 5 個，但會重複使用以達到 1200 篇）
PERSONA_MATRIX = [
    "Tabloid journalist, use heavy dramatic language, ALL CAPS hooks, shocking reveals, urgent tone, and American sensational style.",
    "Viral Gen-Z TikToker, high energy brainrot slang, short punchy sentences, heavy hype, emojis vibe, and trending American internet culture.",
    "Cynical Reddit user, heavy sarcasm, dark humor, AITA style commentary, and US-centric internet slang.",
    "Deep conspiracy investigator, 'hidden truth', 'stay woke', connecting dots others miss, with American political and cultural angle.",
    "Moral critic and societal observer, focus on ethical issues, 'society is collapsing' angle, and impact on American daily life."
]

# ... download_image, get_pexels_image, fetch_single_article 函數保持不變（你原本的）...

def generate_matrix():
    trends_url = "https://raw.githubusercontent.com/pakwingg-del/Trends-Hub/main/master_trends.json"
    print(f"📡 Fetching latest US trends...")
   
    try:
        response = requests.get(trends_url)
        response.raise_for_status()
        data = response.json()
        trending_seeds = data.get("trending_seeds", [])
        trending_seeds.sort(key=lambda x: (x.get("increase", 0), x.get("search_volume", 0)), reverse=True)
        seeds = trending_seeds[:80]      # 保持 80 個 trends
        print(f"✅ Loaded Top {len(seeds)} trends")
    except Exception as e:
        print(f"❌ Error fetching trends: {e}")
        sys.exit(1)

    all_articles = []
    MAX_WORKERS = 50   # 提升 worker 數量，加快生成
    
    # 改成 1200 篇：每個 trend 用 15 個 persona 變體 (5 persona × 3 次)
    print(f"🚀 Starting Large Generation: 80 trends × 15 variants = 1200 articles...")

    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(3):   # 重複 3 次 persona 循環
            for round_idx, persona in enumerate(PERSONA_MATRIX):
                for seed in seeds:
                    tasks.append(executor.submit(fetch_single_article, (round_idx, persona), seed, datetime.now().isoformat()))

        completed_count = 0
        for future in as_completed(tasks):
            result = future.result()
            if result:
                all_articles.append(result)
           
            completed_count += 1
            if completed_count % 100 == 0 or completed_count == len(tasks):
                print(f"📦 Progress: {completed_count}/{len(tasks)} articles processed...")

    print(f"✅ Successfully generated {len(all_articles)} articles with images + human touch.")

    # ==================== D1 Injection ====================
    # （你原本的 D1 注入代碼保持不變）
    CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    CLOUDFLARE_DATABASE_ID = os.environ.get("CLOUDFLARE_DATABASE_ID")
    CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")
   
    if not all([CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_DATABASE_ID, CLOUDFLARE_API_TOKEN]):
        print("❌ Critical Error: Missing Cloudflare credentials!")
        sys.exit(1)

    print(f"🚀 Preparing to inject {len(all_articles)} articles into Cloudflare D1...")
    current_time = int(time.time())
    hugo_date = datetime.now()
    year = hugo_date.strftime("%Y")
    month = hugo_date.strftime("%m")
    day = hugo_date.strftime("%d")
   
    statements = []
    for idx, article in enumerate(all_articles):
        safe_keyword = "".join([c if c.isalnum() else "_" for c in article['keyword']]).lower()
        url_slug = f"{year}/{month}/{day}/{safe_keyword}_{idx}"
       
        article_body = article['body']
        if idx == 0:
            article_body += "\n\nAdsterra verification string: 2HDmQ9"
       
        sql = "INSERT OR REPLACE INTO articles (title, keyword, body, persona_id, persona_type, search_volume, created_at, url_slug) VALUES (?, ?, ?, ?, ?, ?, ?, ?);"
        params = [article['title'], article['keyword'], article_body, article['persona_id'],
                  article['persona_type'], str(article['source_volume']), current_time, url_slug]
        statements.append({"sql": sql, "params": params})

    # 分批注入
    chunk_size = 50
    headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}", "Content-Type": "application/json"}
    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{CLOUDFLARE_DATABASE_ID}/query"
   
    has_error = False
    for i in range(0, len(statements), chunk_size):
        chunk = statements[i:i + chunk_size]
        payload = {"batch": chunk}
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200 and response.json().get("success"):
                print(f"✅ Injected chunk {i//chunk_size + 1}")
            else:
                print(f"❌ Failed chunk {i//chunk_size + 1}")
                has_error = True
        except Exception as e:
            print(f"⚠️ Error in chunk: {e}")
            has_error = True

    if has_error:
        print("❌ MISSION FAILED")
        sys.exit(1)
    else:
        print("🎉 All articles injected into D1!")

    generate_sitemap()
    print("🎉 US Market Batch Complete!")


if __name__ == "__main__":
    generate_matrix()
