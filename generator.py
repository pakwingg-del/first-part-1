import json
import os
import time
import requests
import sys
import re
from datetime import datetime
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed

# 1. API 配置
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 2. 優化後的 5 個 Persona（適合美國市場）
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
   
    # 強化 Prompt - 適合美國市場 + 更長內容
    system_prompt = (
        f"You are a: {current_persona}. Write a unique, engaging viral news article for American audience.\n"
        f"CRITICAL RULES:\n"
        f"- The VERY FIRST LINE of your output must be the title only.\n"
        f"- Title must naturally include the keyword '{query}' and be click-worthy but natural.\n"
        f"- NEVER use Markdown, **, or bold in the title.\n"
        f"- NEVER start title with BREAKING, HEADLINE, etc.\n"
        f"- After title, write a full article around 900-1300 words.\n"
        f"- Include strong personal opinion / analysis at the end.\n"
        f"- Use American English."
    )
   
    try:
        completion = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Write a viral article about: {query}"},
            ],
            max_tokens=1400,      # 大幅提升長度
            temperature=0.85
        )
       
        if not completion or not completion.choices:
            print(f"⚠️ Warning: Empty response from DeepSeek for {query}")
            return None
           
        choice = completion.choices[0]
        if not choice or not choice.message or not choice.message.content:
            print(f"⚠️ Warning: Bad response from DeepSeek for {query}")
            return None
       
        content = choice.message.content.strip()
       
        # 清洗 Title
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        raw_title = lines[0] if lines else query
       
        clean_title = raw_title.replace("**", "").replace("#", "").strip()
        clean_title = re.sub(
            r'^(FOR IMMEDIATE RELEASE|BREAKING NEWS|BREAKING|HEADLINE|VIRAL NEWS SNIPPET|TITLE)[:\s]*',
            '', clean_title, flags=re.IGNORECASE
        ).strip()
       
        # 後備 Title
        if not clean_title or len(clean_title) < 25:
            if round_idx in [0, 1]:
                clean_title = f"Shocking New Development Involving {query} That's Going Viral Across America"
            else:
                clean_title = f"What Americans Need To Know About The {query} Phenomenon Right Now"
       
        return {
            "keyword": query,
            "persona_id": round_idx + 1,
            "persona_type": current_persona.split(',')[0],
            "title": clean_title,
            "body": content,
            "source_volume": seed.get("search_volume"),
            "generated_at": last_updated
        }
    except Exception as e:
        print(f"⚠️ Error processing {query} (Persona {round_idx+1}): {e}")
        return None


def generate_sitemap():
    """簡單版 sitemap 生成（之後可以再優化）"""
    print("🗺️ Generating sitemap from D1...")
    try:
        CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
        CLOUDFLARE_DATABASE_ID = os.environ.get("CLOUDFLARE_DATABASE_ID")
        CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN")
        
        headers = {
            "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json"
        }
        url = f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/d1/database/{CLOUDFLARE_DATABASE_ID}/query"
        
        # 拉最近 48 小時文章
        sql = "SELECT url_slug, created_at FROM articles WHERE created_at >= ? ORDER BY created_at DESC LIMIT 5000"
        last_48h = int(time.time()) - 172800
        
        payload = {"sql": sql, "params": [last_48h]}
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        
        if resp.status_code == 200:
            results = resp.json().get("result", [{}])[0].get("results", [])
            
            sitemap_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
            sitemap_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            
            for row in results:
                full_url = f"https://virallnn.com/{row['url_slug']}"
                lastmod = datetime.fromtimestamp(row['created_at']).strftime("%Y-%m-%d")
                sitemap_content += f'  <url>\n    <loc>{full_url}</loc>\n    <lastmod>{lastmod}</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.8</priority>\n  </url>\n'
            
            sitemap_content += '</urlset>'
            
            os.makedirs('public', exist_ok=True)
            with open('public/sitemap.xml', 'w', encoding='utf-8') as f:
                f.write(sitemap_content)
            
            print(f"✅ Sitemap generated with {len(results)} URLs")
            return True
    except Exception as e:
        print(f"⚠️ Sitemap generation error: {e}")
        return False


def generate_matrix():
    trends_url = "https://raw.githubusercontent.com/pakwingg-del/Trends-Hub/main/master_trends.json"
    print(f"📡 Fetching latest seeds from Trends-Hub...")
   
    try:
        response = requests.get(trends_url)
        response.raise_for_status()
        data = response.json()
        seeds = data.get("trending_seeds", [])[:80]        # ← 改成 80
        last_updated = data["matrix_metadata"]["last_updated_hkt"]
    except Exception as e:
        print(f"❌ Error fetching trends: {e}")
        sys.exit(1)

    all_articles = []
    MAX_WORKERS = 30
    
    print(f"🚀 Starting US Market Generation: 80 trends × 5 personas = 400 articles")

    tasks = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for round_idx, persona in enumerate(PERSONA_MATRIX):
            for seed in seeds:
                tasks.append(executor.submit(fetch_single_article, (round_idx, persona), seed, last_updated))
       
        completed_count = 0
        for future in as_completed(tasks):
            result = future.result()
            if result:
                all_articles.append(result)
           
            completed_count += 1
            if completed_count % 50 == 0 or completed_count == len(tasks):
                print(f"📦 Progress: {completed_count}/{len(tasks)} articles processed...")

    # ==================== D1 Injection (保持不變) ====================
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
        print("🎉 MISSION COMPLETE: All articles stored in D1!")

    # 生成 sitemap
    generate_sitemap()


if __name__ == "__main__":
    generate_matrix()
