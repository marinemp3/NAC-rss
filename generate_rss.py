import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from datetime import datetime
import urllib3

# SSL検証をスキップした際の警告を非表示にする
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://www.nacglobal.net"
CATEGORY_URL = "https://www.nacglobal.net/category/cn/"

def fetch_articles():
    """一覧ページから記事を取得する"""
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; RSS-Generator/1.0)"
    }
    # verify=False でSSL証明書の検証をスキップ
    resp = requests.get(CATEGORY_URL, headers=headers, timeout=30, verify=False)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles = []
    # 記事カードの article タグを取得
    for card in soup.select("article.post_item"):
        a_tag = card.select_one("a._item_link")
        if not a_tag:
            continue
        link = a_tag.get("href", "").strip()
        title_tag = card.select_one("h3._item_ttl")
        title = title_tag.get_text(strip=True) if title_tag else ""

        # 公開日を取得
        pub_time = card.select_one("time.published_time")
        pub_date = None
        if pub_time and pub_time.get("datetime"):
            try:
                pub_date = datetime.fromisoformat(pub_time["datetime"])
            except ValueError:
                pass

        if link and title:
            # 相対URLを絶対URLに
            if link.startswith("/"):
                link = BASE_URL + link
            articles.append({
                "title": title,
                "link": link,
                "pub_date": pub_date,
            })

    return articles

def generate_feed(articles, output_file="feed.xml"):
    """RSSフィードを生成する"""
    fg = FeedGenerator()
    fg.title("NAC Global 中国カテゴリ")
    fg.link(href=CATEGORY_URL, rel="alternate")
    fg.description("NAC Global アジア法令・ビジネス情報サイトの中国カテゴリ記事一覧")
    fg.language("ja")

    for art in articles:
        fe = fg.add_entry()
        fe.title(art["title"])
        fe.link(href=art["link"])
        fe.guid(art["link"], permalink=True)
        if art["pub_date"]:
            fe.pubDate(art["pub_date"])

    fg.rss_file(output_file)
    print(f"RSS feed generated: {output_file} ({len(articles)} articles)")

if __name__ == "__main__":
    articles = fetch_articles()
    if not articles:
        print("記事が見つかりませんでした。セレクタを確認してください。")
    else:
        generate_feed(articles)
