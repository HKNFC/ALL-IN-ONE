import anthropic
import json
import os
from config import BIST100_COMPANIES

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ANALYSIS_PROMPT = """Aşağıdaki Türkiye ekonomi haberini analiz et:

HABER BAŞLIĞI: {title}
HABER İÇERİĞİ: {content}

Aşağıdaki formatta JSON olarak yanıt ver (başka hiçbir şey yazma, sadece JSON):

{{
  "simple_explanation": "Bu haberi 10 yaşındaki bir çocuğun anlayabileceği şekilde 2-3 cümleyle açıkla. Türkçe yaz.",
  "action_suggestion": {{
    "headline": "Bu haberden yatırımcı olarak ne çıkarmalısın? (1 güçlü cümle, doğrudan hitap et, 'Bu gelişme...' diye başla)",
    "watch_list": [
      {{
        "ticker": "BIST kodu",
        "name": "Şirket adı",
        "action": "Al|Sat|İzle|Dikkat",
        "reason": "Neden? Hangi mekanizma ile etkileniyor? (örn: maliyet artışı, döviz kuru, talep artışı)"
      }},
      {{
        "ticker": "BIST kodu",
        "name": "Şirket adı",
        "action": "Al|Sat|İzle|Dikkat",
        "reason": "Neden etkileniyor?"
      }},
      {{
        "ticker": "BIST kodu",
        "name": "Şirket adı",
        "action": "Al|Sat|İzle|Dikkat",
        "reason": "Neden etkileniyor?"
      }}
    ],
    "risk_warning": "Bu analizde dikkat edilmesi gereken en önemli risk faktörü nedir?",
    "opportunity": "Bu gelişmede gözden kaçan ya da beklenmedik bir fırsat var mı?"
  }},
  "time_effects": {{
    "short_term": {{
      "period": "Kısa Vade (1-7 gün)",
      "effect": "Piyasaya ve hisselere kısa vadeli etkisi nedir?",
      "direction": "positive|negative|neutral"
    }},
    "medium_term": {{
      "period": "Orta Vade (1-3 ay)",
      "effect": "Piyasaya ve hisselere orta vadeli etkisi nedir?",
      "direction": "positive|negative|neutral"
    }},
    "long_term": {{
      "period": "Uzun Vade (1 yıl+)",
      "effect": "Piyasaya ve hisselere uzun vadeli etkisi nedir?",
      "direction": "positive|negative|neutral"
    }}
  }},
  "affected_companies": [
    {{
      "ticker": "BIST kodu (ör: THYAO)",
      "name": "Şirket adı",
      "impact": "positive|negative|neutral",
      "reason": "Neden etkileniyor? Kısa açıkla."
    }},
    {{
      "ticker": "BIST kodu",
      "name": "Şirket adı",
      "impact": "positive|negative|neutral",
      "reason": "Neden etkileniyor? Kısa açıkla."
    }},
    {{
      "ticker": "BIST kodu",
      "name": "Şirket adı",
      "impact": "positive|negative|neutral",
      "reason": "Neden etkileniyor? Kısa açıkla."
    }}
  ],
  "affected_sectors": [
    {{
      "name": "Sektör adı",
      "impact": "positive|negative|neutral",
      "reason": "Neden etkileniyor?"
    }},
    {{
      "name": "Sektör adı",
      "impact": "positive|negative|neutral",
      "reason": "Neden etkileniyor?"
    }}
  ],
  "sentiment_score": 0,
  "sentiment_label": "Çok Olumsuz|Olumsuz|Nötr|Olumlu|Çok Olumlu",
  "key_takeaway": "Yatırımcı için tek cümlelik en önemli çıkarım."
}}

Önemli kurallar:
- action_suggestion gerçekten AKSIYON odaklı olmalı — "izle", "araştır" değil; "şu nedenle dikkat et", "şu mekanizma çalışıyor" gibi somut
- action.action değerleri: Al (fiyat yükselir beklentisi), Sat (fiyat düşer riski), İzle (belirsiz ama takipte), Dikkat (olumsuz baskı var)
- sentiment_score -10 ile +10 arasında tam sayı olmalı (-10: çok kötü, 0: nötr, +10: çok iyi)
- affected_companies içinde tercihen BIST-100 hisseleri kullan: {bist_list}
- Tüm açıklamalar Türkçe olmalı
- Sadece JSON döndür, başka metin ekleme
"""


CORRELATION_PROMPT = """Sen Türkiye borsası (BIST) konusunda uzman bir makro ekonomi analistisin.

Makro ekonomik gösterge: {indicator}
Yön: {direction}
Kullanıcının portföyü: {portfolio}

Aşağıdaki formatta JSON olarak yanıt ver (başka hiçbir şey yazma, sadece JSON):

{{
  "indicator_explanation": "Bu göstergenin {direction} yönünde hareket etmesinin ne anlama geldiğini 2 cümleyle açıkla.",
  "best_sectors": [
    {{
      "sector": "Sektör adı",
      "performance": "+X% ile +Y% arası tarihsel getiri",
      "reason": "Neden olumlu etkileniyor? Tarihsel korelasyona dayalı açıkla."
    }},
    {{
      "sector": "Sektör adı",
      "performance": "+X% ile +Y% arası tarihsel getiri",
      "reason": "Neden olumlu etkileniyor?"
    }},
    {{
      "sector": "Sektör adı",
      "performance": "+X% ile +Y% arası tarihsel getiri",
      "reason": "Neden olumlu etkileniyor?"
    }}
  ],
  "worst_sectors": [
    {{
      "sector": "Sektör adı",
      "performance": "-X% ile -Y% arası tarihsel kayıp",
      "reason": "Neden olumsuz etkileniyor? Tarihsel korelasyona dayalı açıkla."
    }},
    {{
      "sector": "Sektör adı",
      "performance": "-X% ile -Y% arası tarihsel kayıp",
      "reason": "Neden olumsuz etkileniyor?"
    }},
    {{
      "sector": "Sektör adı",
      "performance": "-X% ile -Y% arası tarihsel kayıp",
      "reason": "Neden olumsuz etkileniyor?"
    }}
  ],
  "portfolio_risks": [
    {{
      "ticker": "Hisse kodu",
      "risk_level": "Yüksek|Orta|Düşük",
      "reason": "Bu hisse neden risk altında? Hangi rasyolar (F/K, borç/özkaynak, döviz kuru hassasiyeti vb.) bu riski artırıyor?",
      "action": "Sat|Azalt|Tut|Artır"
    }}
  ],
  "safe_havens": ["Bu ortamda güvenli liman olabilecek 3 BIST hissesi veya varlık sınıfı"],
  "summary": "Yatırımcı için tek paragraf özet: Ne olacak, portföyünü nasıl koruyabilir?"
}}

Önemli kurallar:
- portfolio_risks sadece kullanıcının girdiği hisseleri içermeli. Portföy boşsa boş liste döndür.
- Tüm açıklamalar Türkçe olmalı
- Tarihsel verilere ve makro ekonomi teorisine dayalı gerçekçi tahminler ver
- Sadece JSON döndür
"""


TOP_NEWS_PROMPT = """Sen Türkiye borsası uzmanı bir analistsin. Aşağıdaki haber listesinden BIST piyasası için en kritik 3 haberi seç ve analiz et.

Haberler:
{news_list}

Sadece JSON döndür (başka hiçbir şey yazma):

{{
  "top_news": [
    {{
      "index": 0,
      "title": "Haberin başlığı (orijinal)",
      "simple": "Bu haberi 10 yaşındaki birine 1 cümleyle anlat",
      "light": "green|red|yellow",
      "light_reason": "Neden bu renk? Max 10 kelime.",
      "impact_score": 8,
      "affected_tickers": ["TICKER1", "TICKER2"],
      "emoji_summary": "Haberi özetleyen 1-2 emoji"
    }},
    {{
      "index": 1,
      "title": "Haberin başlığı",
      "simple": "1 cümle açıklama",
      "light": "green|red|yellow",
      "light_reason": "Neden bu renk?",
      "impact_score": 7,
      "affected_tickers": ["TICKER1"],
      "emoji_summary": "emoji"
    }},
    {{
      "index": 2,
      "title": "Haberin başlığı",
      "simple": "1 cümle açıklama",
      "light": "green|red|yellow",
      "light_reason": "Neden bu renk?",
      "impact_score": 6,
      "affected_tickers": ["TICKER1"],
      "emoji_summary": "emoji"
    }}
  ],
  "market_mood": "Piyasanın bugünkü genel havası 1 cümlede",
  "mood_score": 5
}}

Kurallar:
- light: green = piyasa için olumlu, red = olumsuz, yellow = belirsiz/nötr
- impact_score: 1-10 arası piyasa etkisi (10 = çok kritik)
- Sadece gerçekten kritik, piyasayı etkileyecek haberleri seç
- Tüm açıklamalar Türkçe
"""


async def get_top_news_analysis(news_items: list) -> dict:
    news_list = "\n".join([
        f"{i+1}. {item['title']} (Kaynak: {item['source']})"
        for i, item in enumerate(news_items[:20])
    ])

    prompt = TOP_NEWS_PROMPT.format(news_list=news_list)

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    result = json.loads(raw)
    for item in result["top_news"]:
        idx = item["index"]
        if 0 <= idx < len(news_items):
            item["url"] = news_items[idx]["url"]
            item["source"] = news_items[idx]["source"]
            item["published_at"] = news_items[idx]["published_at"]
            item["id"] = news_items[idx]["id"]
    return result


async def run_correlation_engine(indicator: str, direction: str, portfolio: list) -> dict:
    portfolio_str = ", ".join(portfolio) if portfolio else "Portföy girilmedi"
    prompt = CORRELATION_PROMPT.format(
        indicator=indicator,
        direction=direction,
        portfolio=portfolio_str
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)


async def analyze_news(title: str, content: str) -> dict:
    bist_sample = ", ".join(BIST100_COMPANIES[:30])
    prompt = ANALYSIS_PROMPT.format(
        title=title,
        content=content,
        bist_list=bist_sample
    )

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    return json.loads(raw)
