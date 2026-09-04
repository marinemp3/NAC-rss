#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import re
import ssl
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
import urllib3

# 警告を無効化
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定
BASE_URL = "https://www.nacglobal.net"
CATEGORY_URL = "https://www.nacglobal.net/category/cn/"
OUTPUT_FILE = "feed.xml"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# 日本のタイムゾーン（JST）
JST = timezone(timedelta(hours=9))

def get_session():
    """SSLエラーを回避するセッションを作成"""
    session = requests.Session()
    session.verify = False
    session.timeout = 30
    return session

def fetch_html(url):
    """指定URLのHTMLを取得する（SSLエラー対応）"""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        session = get_session()
        response = session.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return response.text
    except requests.exceptions.SSLError as e:
        print(f"SSLエラーが発生しました。証明書検証をスキップして再試行します。", file=sys.stderr)
        try:
            session = requests.Session()
            session.verify = False
            from requests.adapters import HTTPAdapter
            
            class SSLAdapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    kwargs['cert_reqs'] = ssl.CERT_NONE
                    kwargs['assert_hostname'] = False
                    return super().init_poolmanager(*args, **kwargs)
            
            session.mount('https://', SSLAdapter())
            response = session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except Exception as e2:
            print(f"再試行も失敗しました: {e2}", file=sys.stderr)
            raise
    except requests.exceptions.RequestException as e:
        print(f"エラー: HTMLの取得に失敗しました - {e}", file=sys.stderr)
        sys.exit(1)

def parse_articles(html):
    """HTMLから記事情報を抽出する"""
    soup = BeautifulSoup(html, 'html.parser')
    articles = []

    # 記事リストのコンテナを探す
    article_items = soup.select('.archive_item-wrap .post_item')
    if not article_items:
        article_items = soup.select('.post_item')

    if not article_items:
        print("警告: 記事が見つかりませんでした。HTML構造が変更された可能性があります。", file=sys.stderr)

    for item in article_items:
        try:
            # 記事リンクを取得
            link_elem = item.find('a', class_='_item_link')
            if not link_elem:
                link_elem = item.find('a', href=True)
            if not link_elem:
                continue
                
            link = urljoin(BASE_URL, link_elem.get('href', ''))
            if not link or link == BASE_URL:
                continue

            # タイトルを取得
            title_elem = item.select_one('._item_ttl')
            if not title_elem:
                title_elem = item.find('h3')
            title = title_elem.get_text(strip=True) if title_elem else "タイトルなし"

            # 公開日を取得
            date_elem = item.select_one('time.published_time')
            pub_date = None
            if date_elem:
                date_str = date_elem.get_text(strip=True)
                match = re.search(r'(\d{4})-(\d{2})-(\d{2})', date_str)
                if match:
                    year, month, day = map(int, match.groups())
                    pub_date = datetime(year, month, day, 0, 0, 0, tzinfo=JST)
                else:
                    match = re.search(r'(\d{4})/(\d{2})/(\d{2})', date_str)
                    if match:
                        year, month, day = map(int, match.groups())
                        pub_date = datetime(year, month, day, 0, 0, 0, tzinfo=JST)

            # カテゴリを取得（親カテゴリと子カテゴリを結合）
            parent_cat = item.select_one('._item_cat .cat_parent')
            child_cat = item.select_one('._item_cat .cat_child')
            
            categories = []
            if parent_cat:
                cat_text = parent_cat.get_text(strip=True)
                if cat_text:
                    categories.append(cat_text)
            if child_cat:
                cat_text = child_cat.get_text(strip=True)
                if cat_text and cat_text not in categories:
                    categories.append(cat_text)
            
            # カテゴリが見つからない場合はデフォルト
            if not categories:
                categories = ["中国"]

            # サムネイル画像を取得
            thumb_elem = item.select_one('._item_thumb img')
            image_url = None
            if thumb_elem and thumb_elem.get('src'):
                image_url = urljoin(BASE_URL, thumb_elem.get('src'))

            articles.append({
                'title': title,
                'link': link,
                'pub_date': pub_date,
                'categories': categories,  # リストで保持
                'description': f"{title} - {categories[0] if categories else '中国'}",
                'image_url': image_url,
            })
        except Exception as e:
            print(f"警告: 記事の解析中にエラーが発生しました - {e}", file=sys.stderr)
            continue

    return articles

def generate_feed(articles):
    """RSSフィードを生成する"""
    fg = FeedGenerator()
    fg.title("NAC Global アジア法令・ビジネス情報サイト - 中国")
    fg.link(href=CATEGORY_URL, rel="alternate")
    fg.link(href=f"https://{urlparse(BASE_URL).netloc}/feed.xml", rel="self")
    fg.description("中国の最新法令・ビジネス情報")
    fg.language("ja")

    now = datetime.now(JST)
    fg.lastBuildDate(now)

    # 記事を新しい順に並べ替え
    sorted_articles = sorted(
        articles,
        key=lambda x: x['pub_date'] if x['pub_date'] else datetime(2000, 1, 1, tzinfo=JST),
        reverse=True
    )

    for article in sorted_articles[:50]:
        fe = fg.add_entry()
        fe.title(article['title'])
        fe.link(href=article['link'])
        fe.guid(article['link'], permalink=True)

        if article['pub_date']:
            fe.pubDate(article['pub_date'])
        else:
            fe.pubDate(now)

        # カテゴリを辞書形式で追加（修正箇所）
        for cat_name in article.get('categories', ['中国']):
            if cat_name:
                # feedgenのcategoryメソッドは辞書を期待
                fe.category({'term': cat_name})

        fe.description(article['description'])

        if article.get('image_url'):
            try:
                fe.enclosure(article['image_url'], 0, 'image/png')
            except Exception as e:
                print(f"警告: エンクロージャーの追加に失敗 - {e}", file=sys.stderr)

    return fg.rss_str(pretty=True)

def save_feed(feed_content):
    """フィードをファイルに保存する"""
    try:
        with open(OUTPUT_FILE, 'wb') as f:
            f.write(feed_content)
        content_str = feed_content.decode('utf-8')
        item_count = content_str.count('<item>')
        print(f"RSSフィードを {OUTPUT_FILE} に保存しました。")
        print(f"記事数: {item_count}")
    except Exception as e:
        print(f"エラー: フィードの保存に失敗しました - {e}", file=sys.stderr)
        sys.exit(1)

def main():
    print(f"記事取得開始: {CATEGORY_URL}")
    print(f"実行時刻: {datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S JST')}")

    try:
        html = fetch_html(CATEGORY_URL)
        articles = parse_articles(html)
    except Exception as e:
        print(f"致命的エラー: {e}", file=sys.stderr)
        sys.exit(1)

    if not articles:
        print("エラー: 記事が1件も見つかりませんでした。", file=sys.stderr)
        sys.exit(1)

    print(f"記事を {len(articles)} 件取得しました。")

    feed_content = generate_feed(articles)
    save_feed(feed_content)

    print("完了しました。")

if __name__ == "__main__":
    main()
