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

PERSONA_MATRIX = [
    "Tabloid journalist, use heavy dramatic language, ALL CAPS hooks, shocking reveals, urgent tone, and American sensational style.",
    "Viral Gen-Z TikToker, high energy brainrot slang, short punchy sentences, heavy hype, emojis vibe, and trending American internet culture.",
    "Cynical Reddit user, heavy sarcasm, dark humor, AITA style commentary, and US-centric internet slang.",
    "Deep conspiracy investigator, 'hidden truth', 'stay woke', connecting dots others miss, with American political and cultural angle.",
    "Moral critic and societal observer, focus on ethical issues, 'society is collapsing' angle, and impact on American daily life."
]

def download_image(url, filename):
    try:
        os.makedirs('public/images', exist_ok=True)
        filepath = f"public/images/{filename}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            return f"/images/{filename}"
    except:
        return None
    return None

def get_pexels_image(query):
    if not PEXELS_API_KEY:
        return None
    try:
        headers = {"Authorization": PEXELS_API_KEY}
        params = {"query": query, "per_page": 1, "orientation": "landscape"}
        resp = requests.get("https://api.pexels.com/v1/search", headers=headers, params=params, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("photos"):
                photo = data["photos"][0]
                image_url = photo["src"]["large"]
                filename = f"{int(time.time())}_{photo['id']}.jpg"
                return download_image(image_url, filename)
    except:
        pass
    return None

def fetch_single_article(persona_tuple, seed, last_updated):
    round_idx, current_persona = persona_tuple
    query = seed['query']
   
    system_prompt = (
        f"You are a: {current_persona}. Write a unique, engaging viral news article for American audience.\n"
        f"CRITICAL RULES:\n"
        f"- The VERY FIRST LINE must be the title only.\n"
        f"- Write the main article body (800-1100 words).\n"
        f"- Do NOT write conclusion yet.\n"
        f"- Use American English."
    )
   
    try:
        completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": f"Write a viral article about: {query}"}],
            max_tokens=1300,
            temperature=0.85
        )
       
        content = completion.choices[0].message.content.strip()
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        raw_title = lines[0] if lines else query
       
        clean_title = re.sub(r'^(FOR IMMEDIATE RELEASE|BREAKING NEWS|BREAKING|HEADLINE|TITLE)[:\s]*', '', raw_title, flags=re.IGNORECASE).strip()
       
        if len(clean_title) < 30:
            clean_title = f"Shocking New Update About {query} That's Going Viral Across America Right Now"

        # Human Touch Opinion
        opinion_prompt = f"Based on the article about '{query}', write 2-3 insightful sentences as a personal opinion and conclusion. Sound like a real experienced journalist."
        opinion_completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": opinion_prompt}],
            max_tokens=180,
            temperature=0.9
        )
        opinion = opinion_completion.choices[0].message.content.strip()
       
        final_content = content + "\n\n<h3>Final Thoughts</h3>\n<p>" + opinion + "</p>"

        # 加圖片
        image_path = get_pexels_image(query)
        if image_path:
            final_content = f'<img src="{image_path}" alt="{clean_title}" style="max-width:100%; height:auto; border-radius:8px;"><br><br>' + final_content

        return {
            "keyword": query,
            "persona_id": round_idx + 1,
            "persona_type": current_persona.split(',')[0],
            "title": clean_title,
            "body": final_content,
            "source_volume": seed.get("search_volume", 0),
            "generated_at": last_updated
        }
    except Exception as e:
        print(f"⚠️ Error processing {query}: {e}")
        return None


def generate_sitemap():
    print("🗺️ Generating sitemap...")
    # （你可以之後再補完整 sitemap 代碼，先跳過都得）


def generate_matrix():
    trends_url = "https://raw.githubusercontent.com/pakwingg-del/Trends-Hub/main/master_trends.json"
    print(f"📡 Fetching latest US trends...")
   
    try:
        response = requests.get(trends_url)
        response.raise_for_status()
        data = response.json()
        trending_seeds = data.get("trending_seeds", [])
        trending_seeds.sort(key=lambda x: (x.get("increase", 0), x.get("search_volume", 0)), reverse=True)
        seeds = trending_seeds[:80]
        print(f"✅ Loaded Top {len(seeds)} trends")
    except Exception as e:
        print(f"❌ Error fetching trends: {e}")
        sys.exit(1)

    all_articles = []
    MAX_WORKERS = 50
    
    print(f"🚀 Starting Large Generation: 80 trends × 15 variants = 1200 articles...")

    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for i in range(3):  # 3 輪循環 = 15 variants
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

    print(f"✅ Successfully generated {len(all_articles)} articles.")

    # D1 Injection（你原本的代碼）
    # ... 你原本 D1 部分貼上來 ...

    generate_sitemap()
    print("🎉 US Market Batch Complete!")


if __name__ == "__main__":
    generate_matrix()
