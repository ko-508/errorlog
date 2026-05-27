import os
import re
import random
import feedparser
import tweepy
import anthropic
from dotenv import load_dotenv

load_dotenv()

twitter = tweepy.Client(
    consumer_key=os.getenv("CONSUMER_KEY"),
    consumer_secret=os.getenv("CONSUMER_SECRET"),
    access_token=os.getenv("ACCESS_TOKEN"),
    access_token_secret=os.getenv("ACCESS_TOKEN_SECRET"),
)

claude = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

ARXIV_FEEDS = [
    "https://arxiv.org/rss/hep-ph",
    "https://arxiv.org/rss/hep-ex",
    "https://arxiv.org/rss/physics.ins-det",
    "https://arxiv.org/rss/cs.LG",
]

CATEGORY_MAP = {
    "hep-ph": "素粒子理論",
    "hep-ex": "素粒子実験",
    "physics.ins-det": "検出器物理",
    "cs.LG": "機械学習",
}

POSTED_FILE = "posted.txt"


def load_posted():
    if not os.path.exists(POSTED_FILE):
        return set()
    with open(POSTED_FILE, "r") as f:
        return set(line.strip() for line in f)


def save_posted(link):
    with open(POSTED_FILE, "a") as f:
        f.write(link + "\n")


def clean_html(text):
    return re.sub(r'<[^>]+>', '', text).strip()


def clean_dollars(text):
    return text.replace('$', '＄')


def fetch_papers():
    posted = load_posted()
    papers = []
    for url in ARXIV_FEEDS:
        feed = feedparser.parse(url)
        cat = url.split("/")[-1]
        for entry in feed.entries:
            if entry.link not in posted:
                papers.append({
                    "title": entry.title,
                    "link": entry.link,
                    "category": cat,
                    "abstract": getattr(entry, "summary", ""),
                })
    return papers


def summarize(abstract, category):
    abstract = clean_html(abstract)
    if not abstract:
        return None
    try:
        messages = [{
            "role": "user",
            "content": (
                f"以下の{category}分野の論文アブストラクトを"
                "学部生でも理解できる優しい語彙で、日本語2〜3行の箇条書き（各行を「・」で始める）で要約してください。"
                "専門用語は使わず平易な言葉で。前置き不要。箇条書きのみ返してください。\n\n"
                f"{abstract[:1500]}"
            ),
        }]
        for attempt in range(3):
            response = claude.messages.create(
                model="claude-haiku-4-5",
                max_tokens=200,
                messages=messages,
            )
            result = response.content[0].text.strip()
            if len(result) <= 140:
                return result
            print(f"要約が{len(result)}文字のため短縮中... (試行{attempt + 1})")
            messages.append({"role": "assistant", "content": result})
            messages.append({
                "role": "user",
                "content": f"140文字以内に収まっていません（現在{len(result)}文字）。同じ箇条書き形式で140文字以内に短くしてください。",
            })
        return result[:139] + "…"
    except Exception as e:
        print(f"要約エラー: {e}")
        return None


def truncate(text, limit=140):
    return text if len(text) <= limit else text[:limit - 1] + "…"


def main():
    papers = fetch_papers()
    if not papers:
        print("新しい論文がありません")
        return

    paper = random.choice(papers)
    cat = CATEGORY_MAP.get(paper["category"], paper["category"])

    # ツイート1: リンク＋ハッシュタグ
    tweet1 = f"【{cat}】\n{paper['link']}\n#素粒子物理 #機械学習 #arXiv"
    print(f"1ツイート目:\n{tweet1}\n")
    res1 = twitter.create_tweet(text=tweet1, user_auth=True)
    id1 = res1.data["id"]

    # リプライ1: タイトル
    title = truncate(paper["title"])
    print(f"リプライ1:\n{title}\n")
    res2 = twitter.create_tweet(text=title, in_reply_to_tweet_id=id1, user_auth=True)
    id2 = res2.data["id"]

    # リプライ2: 要約
    summary = summarize(paper["abstract"], cat)
    if summary:
        summary = truncate(clean_dollars(summary))
        print(f"リプライ2:\n{summary}\n")
        twitter.create_tweet(text=summary, in_reply_to_tweet_id=id2, user_auth=True)

    save_posted(paper["link"])
    print("投稿完了")


if __name__ == "__main__":
    main()
