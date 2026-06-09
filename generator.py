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

# 美國市場優化 Persona (5個)
PERSONA_MATRIX = [
    "Tabloid journalist, use heavy dramatic language, ALL CAPS hooks, shocking reveals, urgent tone, and American sensational style.",
    "Viral Gen-Z TikToker, high energy brainrot slang, short punchy sentences, heavy hype, emojis vibe, and trending American internet culture.",
    "Cynical Reddit user, heavy sarcasm, dark humor, AITA style commentary, and US-centric internet slang.",
    "Deep conspiracy investigator, 'hidden truth', 'stay woke', connecting dots others miss, with American political and cultural angle.",
    "Moral critic and societal observer, focus on ethical issues, 'society is collapsing' angle, and impact on American daily life."
]

def fetch_single_article(persona_tuple, seed, last_updated):
    round_idx, current_persona = persona_tuple
    query = seed['query']
   
    system_prompt = (
        f"You are a: {current_persona}. Write a unique, engaging viral news article for American audience.\n"
        f"CRITICAL RULES:\n"
        f"- The VERY FIRST LINE must be the title only.\n"
        f"- Title must naturally include '{query}' and be highly click-worthy.\n"
        f"- Write a full article of approximately 1000-1400 words.\n"
        f"- Include strong personal opinion and analysis at the end.\n"
        f"- Use American English. No Markdown in title."
    )
   
    try:
        completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Write a viral article about: {query}"},
            ],
            max_tokens=1400,
            temperature=0.85
        )
       
        content = completion.choices[0].message.content.strip()
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        raw_title = lines[0] if lines else query
        
        clean_title = re.sub(r'^(FOR IMMEDIATE RELEASE|BREAKING NEWS|BREAKING|HEADLINE|TITLE)[:\s]*', '', raw_title, flags=re.IGNORECASE).strip()
        clean_title = clean_title.replace("**", "").replace("#", "").strip()
        
        if len(clean_title) < 25:
            clean_title = f"Shocking New Update About {query} That's Going Viral Across America Right Now"
        
        return {
            "keyword": query,
            "persona_id": round_idx + 1,
            "persona_type": current_persona.split(',')[0],
            "title": clean_title,
            "body": content,
            "source_volume": seed.get("search_volume", 0),
            "generated_at": last_updated
        }
    except Exception as e:
        print(f"⚠️ Error processing {query}: {e}")
        return None


def generate_sitemap():
    print("🗺️ Generating sitemap...")
    try:
        CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        CLOUDFLARE_DATABASE_ID = os.environ.get("CLOUDFLARE_DATABASE_ID")
        CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")
        
        headers = {"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}", "Content-Type": "application/json"}
        url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{CLOUDFLARE_DATABASE_ID}/query"
        
        sql = "SELECT url_slug FROM articles WHERE created_at >= ? ORDER BY created_at DESC LIMIT 5000"
        payload = {"sql": sql, "params": [int(time.time()) - 172800]}
        
        resp = requests.post(url, headers=headers, json=payload)
        results = resp.json().get("result", [{}])[0].get("results", [])
        
        sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for row in results:
            full_url = f"https://virallnn.com/{row['url_slug']}"
            sitemap += f'  <url><loc>{full_url}</loc><lastmod>{datetime.now().strftime("%Y-%m-%d")}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>\n'
        sitemap += '</urlset>'
        
        os.makedirs('public', exist_ok=True)
        with open('public/sitemap.xml', 'w', encoding='utf-8') as f:
            f.write(sitemap)
        print(f"✅ Sitemap generated with {len(results)} URLs")
    except Exception as e:
        print(f"⚠️ Sitemap error: {e}")


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
        last_updated = data["matrix_metadata"].get("last_updated_hkt", "")
        print(f"✅ Loaded Top {len(seeds)} trends")
    except Exception as e:
        print(f"❌ Error fetching trends: {e}")
        sys.exit(1)

    # Generate 400 articles
    all_articles = []
    MAX_WORKERS = 30
    print(f"🚀 Generating 80 trends × 5 personas = 400 articles...")

    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for round_idx, persona in enumerate(PERSONA_MATRIX):
            for seed in seeds:
                tasks.append(executor.submit(fetch_single_article, (round_idx, persona), seed, last_updated))
       
        for future in as_completed(tasks):
            result = future.result()
            if result:
                all_articles.append(result)

    # ====================== D1 Injection ======================
    # （你原本 D1 注入代碼保持不變，我這裡簡化顯示，你可以保留之前完整版）
    print(f"🎉 Total {len(all_articles)} articles generated. Starting D1 injection...")

    # ... 你原本的 CLOUDFLARE D1 注入代碼保持不變 ...

    # Sitemap + Indexing（如果有 submit_indexing.py）
    generate_sitemap()
    print("✅ US Market Batch Complete!")


if __name__ == "__main__":
    generate_matrix()
