import json
import os
import time
import requests
import sys  # 🚀 新增：用來在出錯時中斷 GitHub 流程
from datetime import datetime
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. API 配置
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), 
    base_url="https://api.deepseek.com"
)

# 2. 完整保留你原本的 20 個人格矩陣
PERSONA_MATRIX = [
    # A. 爆料組 (Sensationalist)
    "Tabloid journalist, use heavy ALL CAPS, dramatic 'JUST IN' hooks, and suspenseful language.",
    "Anonymous insider leaking 'off-the-record' secrets, use a mysterious and confidential tone.",
    "Viral news scout, focus on why this topic is breaking the internet right now with high energy.",
    "Red carpet reporter, focus on celebrity reactions, drama, and the shock factor.",
    # B. 網民組 (Social/Viral)
    "Cynical Reddit user, use internet slang like AITA, TL;DR, and heavy sarcasm/irony.",
    "Gen-Z TikToker, use 'brainrot' slang, very informal, short sentences, and high hype.",
    "Angry local resident commenting on a Facebook community group, focus on 'common sense'.",
    "Meme historian, explaining the irony or the funny side of why this is trending.",
    # C. 陰謀/深度組 (Investigative)
    "Deep-web investigator, connecting dots others miss. Use 'Stay woke' and 'The hidden truth'.",
    "Technical analyst finding 'glitches in the matrix' or weird coincidences in the data.",
    "Skeptical observer asking 'Who benefits from this?' and questioning mainstream narratives.",
    "History buff comparing this event to a famous past event or hidden historical pattern.",
    # D. 資訊/專業組 (Informational)
    "Professional news anchor, neutral tone, 5W1H format, very formal and authoritative.",
    "Listicle creator, 'Top 5 things you need to know about this' format with bullet points.",
    "Executive summary writer for CEOs, strictly business, concise, and impact-oriented.",
    "Fact-checker verifying the latest viral rumors and clarifying what is real vs fake.",
    # E. 價值/生活組 (Value-driven)
    "Consumer advocate, focus on how this news affects the reader's wallet and daily life.",
    "Life coach giving psychological or motivational advice based on this trending event.",
    "Futurist predicting how this topic will evolve and impact society in the next 10 years.",
    "Moral critic, discussing the ethical implications and the 'downfall of society' angle."
]

def fetch_single_article(persona_tuple, seed, last_updated):
    round_idx, current_persona = persona_tuple
    query = seed['query']
    
    try:
        completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": f"You are a: {current_persona}. Write a unique viral news snippet."},
                {"role": "user", "content": f"Topic: {query}"},
            ],
            max_tokens=400,
            temperature=1.0 
        )
        content = completion.choices[0].message.content
        
        return {
            "keyword": query,
            "persona_id": round_idx + 1,
            "persona_type": current_persona.split(',')[0],
            "title": content.split('\n')[0].replace('#', '').strip(),
            "body": content,
            "source_volume": seed.get("search_volume"),
            "generated_at": last_updated
        }
    except Exception as e:
        print(f"⚠️ Error with {query} (Round {round_idx+1}): {e}")
        return None

def generate_matrix():
    trends_url = "https://raw.githubusercontent.com/pakwingg-del/Trends-Hub/main/master_trends.json"
    print(f"📡 Fetching latest seeds from Trends-Hub...")
    
    try:
        response = requests.get(trends_url)
        response.raise_for_status()
        data = response.json()
        seeds = data.get("trending_seeds", [])[:30]
        last_updated = data["matrix_metadata"]["last_updated_hkt"]
    except Exception as e:
        print(f"❌ Error fetching trends: {e}")
        sys.exit(1)

    all_articles = []
    
    print(f"🚀 Starting Parallel Generation (600 tasks) with 5 workers...")
    
    tasks = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        for round_idx, persona in enumerate(PERSONA_MATRIX):
            for seed in seeds:
                tasks.append(executor.submit(fetch_single_article, (round_idx, persona), seed, last_updated))
        
        completed_count = 0
        for future in as_completed(tasks):
            result = future.result()
            if result:
                all_articles.append(result)
            
            completed_count += 1
            if completed_count % 50 == 0:
                print(f"📦 Progress: {completed_count}/600 articles generated...")

    # ====================================================
    # 修正：全面改為從環境變數讀取，不再硬編碼
    # ====================================================
    CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    CLOUDFLARE_DATABASE_ID = os.environ.get("CLOUDFLARE_DATABASE_ID")
    CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not all([CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_DATABASE_ID, CLOUDFLARE_API_TOKEN]):
        print("❌ Critical Error: Missing Cloudflare credentials in environment variables!")
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
        params = [
            article['title'],
            article['keyword'],
            article_body,
            article['persona_id'],
            article['persona_type'],
            str(article['source_volume']),
            current_time,
            url_slug
        ]
        statements.append({"sql": sql, "params": params})

    # Cloudflare API 分批打包發送
    chunk_size = 50
    headers = {
        "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # 🚀 修正 1: database -> databases (複數)
    url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/databases/{CLOUDFLARE_DATABASE_ID}/query"

    has_error = False
    for i in range(0, len(statements), chunk_size):
        chunk = statements[i:i + chunk_size]
        try:
            # 🚀 修正 2: json=chunk 直接傳送 List，不再包一層 "batches"
            response = requests.post(url, headers=headers, json=chunk, timeout=30)
            if response.status_code == 200 and response.json().get("success"):
                print(f"✅ Successfully injected chunk {i // chunk_size + 1}/{((len(statements)-1)//chunk_size)+1}")
            else:
                print(f"❌ Failed to inject chunk {i // chunk_size + 1}: {response.text}")
                has_error = True
        except Exception as e:
            print(f"⚠️ Connection error during chunk {i // chunk_size + 1}: {e}")
            has_error = True

    if has_error:
        print("❌ MISSION FAILED: Some or all chunks failed to inject into D1.")
        sys.exit(1)  # 讓 GitHub 真正亮紅燈
    else:
        print("🎉 MISSION COMPLETE: All AI articles are stored in the Edge Cloud Database!")

if __name__ == "__main__":
    generate_matrix()
