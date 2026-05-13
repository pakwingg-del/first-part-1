import json
import os
import time
import requests
from openai import OpenAI

# 1. API 配置 - 使用 GitHub Secrets 中的 DEEPSEEK_API_KEY
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"), 
    base_url="https://api.deepseek.com"
)

# 2. 定義 20 個細分的人格，確保內容多樣性，對沖 SEO 重複風險
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

def generate_matrix():
    # 3. 從 Trends-Hub 抓取最新藍圖 (Blueprint)
    trends_url = "https://raw.githubusercontent.com/pakwingg-del/Trends-Hub/main/master_trends.json"
    print(f"📡 Fetching latest seeds from Trends-Hub...")
    
    try:
        response = requests.get(trends_url)
        response.raise_for_status()
        data = response.json()
        seeds = data.get("trending_seeds", [])[:30] # 嚴格執行 Top 30 策略
    except Exception as e:
        print(f"❌ Error fetching trends: {e}")
        return

    all_articles = []

    # 4. 核心矩陣生成邏輯：20 Rounds x 30 Topics = 600 Articles
    for round_idx in range(20):
        current_persona = PERSONA_MATRIX[round_idx]
        print(f"🌀 ROUND {round_idx + 1}/20 | Persona: {current_persona[:40]}...")

        for seed in seeds:
            query = seed['query']
            
            try:
                # 呼叫 DeepSeek-V3
                completion = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": f"You are a: {current_persona}. Write a unique viral news snippet."},
                        {"role": "user", "content": f"Topic: {query}"},
                    ],
                    max_tokens=400,
                    temperature=1.0 # 提高隨機性，確保即使人格相似內容也不同
                )
                
                content = completion.choices[0].message.content
                
                all_articles.append({
                    "keyword": query,
                    "persona_id": round_idx + 1,
                    "persona_type": current_persona.split(',')[0], # 記錄人格類型
                    "title": content.split('\n')[0].replace('#', '').strip(),
                    "body": content,
                    "source_volume": seed.get("search_volume"),
                    "generated_at": data["matrix_metadata"]["last_updated_hkt"]
                })
                
                # 短暫延遲：每秒約 2 個 Request，保護 API RPM
                time.sleep(0.5)
                
            except Exception as e:
                print(f"⚠️ Skipping {query} due to error: {e}")
                continue

        # 每完成一個 Round (30篇) 大休息，防止 Actions 逾時或 API 過熱
        print(f"✅ Round {round_idx + 1} finished. Total so far: {len(all_articles)}")
        time.sleep(10)

    # 5. 儲存成品
    output_file = "matrix_articles.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_articles, f, indent=2, ensure_ascii=False)
    
    print(f"🏁 MISSION COMPLETE: {len(all_articles)} articles saved to {output_file}")

if __name__ == "__main__":
    generate_matrix()
