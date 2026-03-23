import feedparser
import httpx
import hashlib
from datetime import datetime
from typing import List, Dict
from bs4 import BeautifulSoup
from config import NEWS_SOURCES


def clean_html(html_text: str) -> str:
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "lxml")
    return soup.get_text(separator=" ", strip=True)[:500]


def generate_id(url: str, title: str) -> str:
    return hashlib.md5(f"{url}{title}".encode()).hexdigest()[:12]


async def fetch_news(limit: int = 50) -> List[Dict]:
    all_news = []

    for source in NEWS_SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = clean_html(entry.get("summary", entry.get("description", "")))
                published = entry.get("published", entry.get("updated", ""))

                if not title or not link:
                    continue

                try:
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat() if hasattr(entry, 'published_parsed') and entry.published_parsed else datetime.now().isoformat()
                except Exception:
                    pub_date = datetime.now().isoformat()

                all_news.append({
                    "id": generate_id(link, title),
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source": source["name"],
                    "category": source["category"],
                    "published_at": pub_date,
                    "logo": source.get("logo", "")
                })
        except Exception as e:
            print(f"Error fetching {source['name']}: {e}")
            continue

    all_news.sort(key=lambda x: x["published_at"], reverse=True)
    return all_news[:limit]
