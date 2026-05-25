import json
import os
import time
import requests
from datetime import datetime, timedelta
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
            # 保持 keyword 原貌供檔名轉換使用
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
        return

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
    # 核心更改：Plan A 儲存與 30 天自動清理機制
    # ====================================================
    output_dir = "content/posts"
    os.makedirs(output_dir, exist_ok=True)

    # 1. 自動清理過期檔案 (大於 30 天)
    print("🧹 Checking for expired articles (older than 30 days)...")
    now = datetime.now()
    retention_days = 3
    deleted_count = 0

    for file_name in os.listdir(output_dir):
        if file_name.endswith(".md"):
            file_path = os.path.join(output_dir, file_name)
            file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            if now - file_time > timedelta(days=retention_days):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    print(f"⚠️ Failed to delete {file_name}: {e}")

    if deleted_count > 0:
        print(f"🗑️ Cleaned up {deleted_count} expired Markdown files.")
    else:
        print("✨ No expired articles found.")

    # 2. 將 600 篇新文章分別寫入獨立的 .md 檔案
    print(f"✍️ Writing {len(all_articles)} new Markdown files for Hugo...")
    
    # 格式化 Hugo 所需的 Date 欄位 (e.g., 2026-05-19T06:00:00)
    # 如果 last_updated 格式不支援，則 fallback 使用目前系統時間
    try:
        hugo_date = datetime.strptime(last_updated, "%Y-%m-%d %H:%M").strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:
        hugo_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for idx, article in enumerate(all_articles):
        # 移除非法字元，確保檔名安全
        safe_keyword = "".join([c if c.isalnum() else "_" for c in article['keyword']])
        timestamp = int(time.time())
        file_name = f"{output_dir}/article_{safe_keyword}_{timestamp}_{idx}.md"
        
        with open(file_name, "w", encoding="utf-8") as f:
            # 寫入 Hugo Front Matter 
            f.write("---\n")
            f.write(f"title: {json.dumps(article['title'], ensure_ascii=False)}\n") # 用 json.dumps 處理特殊符號與雙引號
            f.write(f"date: {hugo_date}\n")
            f.write(f"persona_id: {article['persona_id']}\n")
            f.write(f"persona_type: {json.dumps(article['persona_type'], ensure_ascii=False)}\n")
            f.write(f"search_volume: \"{article['source_volume']}\"\n")
            f.write("---\n\n")
            f.write(article['body'])
            
    print(f"🏁 MISSION COMPLETE: Saved to {output_dir}/")

if __name__ == "__main__":
    generate_matrix()
