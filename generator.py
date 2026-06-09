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

# 美國市場優化 Persona (5個)
PERSONA_MATRIX = [
    "Tabloid journalist, use heavy dramatic language, ALL CAPS hooks, shocking reveals, urgent tone, and American sensational style.",
    "Viral Gen-Z TikToker, high energy brainrot slang, short punchy sentences, heavy hype, emojis vibe, and trending American internet culture.",
    "Cynical Reddit user, heavy sarcasm, dark humor, AITA style commentary, and US-centric internet slang.",
    "Deep conspiracy investigator, 'hidden truth', 'stay woke', connecting dots others miss, with American political and cultural angle.",
    "Moral critic and societal observer, focus on ethical issues, 'society is collapsing' angle, and impact on American daily life."
]

def download_image(url, filename):
    """下載圖片"""
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
    """從 Pexels 獲取相關圖片"""
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
   
    # 第一階段：生成主體內容
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

        # 第二階段：Human Touch Opinion
        opinion_prompt = (
            f"Based on the article about '{query}', write 2-3 insightful sentences as a personal opinion and conclusion.\n"
            f"Sound like a real experienced journalist. Be slightly emotional, critical or reflective. Give a clear takeaway."
        )
        
        opinion_completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": opinion_prompt}],
            max_tokens=180,
            temperature=0.9
        )
        opinion = opinion_completion.choices[0].message.content.strip()
        
        # 合併內容
        final_content = content + "\n\n<h3>Final Thoughts</h3>\n<p>" + opinion + "</p>"

        # 加 Pexels 圖片
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
    print("🗺️ Generating sitemap from D1...")
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
        print(f"✅ Loaded Top {len(seeds)} trends")
    except Exception as e:
        print(f"❌ Error fetching trends: {e}")
        sys.exit(1)

    all_articles = []
    MAX_WORKERS = 30
    print(f"🚀 Starting Generation: 80 trends × 5 personas = 400 articles...")

    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for round_idx, persona in enumerate(PERSONA_MATRIX):
            for seed in seeds:
                tasks.append(executor.submit(fetch_single_article, (round_idx, persona), seed, datetime.now().isoformat()))

    for future in as_completed(tasks):
        result = future.result()
        if result:
            all_articles.append(result)

    print(f"✅ Successfully generated {len(all_articles)} articles with images + human touch.")

    # ==================== D1 Injection (你原本完整代碼) ====================
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
                print(f"❌ Failed chunk {i//chunk_size + 1}: {response.text}")
                has_error = True
        except Exception as e:
            print(f"⚠️ Error in chunk {i//chunk_size + 1}: {e}")
            has_error = True

    if has_error:
        print("❌ MISSION FAILED: Some chunks failed.")
        sys.exit(1)
    else:
        print("🎉 All articles successfully injected into D1!")

    generate_sitemap()
    print("🎉 US Market Batch Complete!")


if __name__ == "__main__":
    generate_matrix()
