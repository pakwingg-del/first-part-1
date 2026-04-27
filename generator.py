import os, json, re, time, requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("DEEPSEEK_API_KEY"), base_url="https://api.deepseek.com")
TRENDS_JSON_URL = "https://raw.githubusercontent.com/pakwingg-del/Trends-Hub/main/master_trends.json"

def fetch_trends():
    r = requests.get(TRENDS_JSON_URL, timeout=30)
    return r.json().get("trends", [])

def clean_slug(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')

def save_md(data, target_dir, slug):
    path = os.path.join(target_dir, f"{slug}.md")
    fm = {
        "title": data.get('title', slug),
        "date": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00'),
        "summary": data.get('summary', ''),
        "categories": data.get('categories', ["News"]),
        "tags": data.get('tags', ["Viral"]),
        "draft": False
    }
    content = "---\n" + "\n".join([f'{k}: {json.dumps(v)}' for k, v in fm.items()]) + "\n---\n\n"
    content += data.get('content', '')
    if data.get('faq'):
        content += "\n\n---\n## 💡 FAQ\n" + "\n".join([f"#### {f['question']}\n> {f['answer']}" for f in data['faq']])
    with open(path, "w", encoding="utf-8") as f: f.write(content)

def process(item, target_dir):
    topic = item.get("query") or item.get("title")
    try:
        res = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": f"Write a viral news about '{topic}' in JSON format."}],
            response_format={'type': 'json_object'}
        )
        data = json.loads(res.choices[0].message.content)
        save_md(data, target_dir, clean_slug(topic))
        return True
    except: return False

def main():
    trends = fetch_trends()
    repo_idx = int(os.environ.get("REPO_INDEX", 0))
    total = int(os.environ.get("TOTAL_REPOS", 2))
    my_tasks = trends[repo_idx::total] # 均勻分片
    
    target_dir = f"content/posts/{datetime.now().strftime('%Y-%m-%d')}"
    os.makedirs(target_dir, exist_ok=True)
    
    with ThreadPoolExecutor(max_workers=10) as exe:
        exe.map(lambda x: process(x, target_dir), my_tasks)

if __name__ == "__main__": main()