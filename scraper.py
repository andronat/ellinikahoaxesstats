import logging
import os
import os.path as path
import pickle
import re
import requests
import sys

from bs4 import BeautifulSoup
from collections import Counter
from pprint import pformat

LOCAL_DATA_DIR = path.join(path.dirname(path.realpath(__file__)), "cache")
ARTICLE_URL_DB = path.join(LOCAL_DATA_DIR, "all_article_urls.txt")
ARTICLE_DB = path.join(LOCAL_DATA_DIR, "articles.pickle")

logging.basicConfig(format="%(message)s", level=logging.INFO)


def init_cache():
    if not path.isdir(LOCAL_DATA_DIR):
        os.makedirs(LOCAL_DATA_DIR)


def download_page(url):
    page = requests.get(url)
    page.raise_for_status()
    return BeautifulSoup(page.content, "html.parser")


def get_next_page(page):
    tag = page.find("a", attrs={"class": "next page-numbers"})

    if tag:
        next_url = tag.get("href")
        logging.info(f"Going to next page: {next_url}")
        return download_page(next_url)
    else:
        logging.info(f"No more pages")
        return None


def get_all_article_urls(page):
    return list(
        map(
            lambda tag: tag.get("href"),
            page.find_all("a", attrs={"class": "btn btn-secondary"}),
        )
    )


def scrap_article_urls():
    root_url = "https://www.ellinikahoaxes.gr/category/kathgories/"
    logging.info(f"Root page: {root_url}")

    page = download_page(root_url)

    a_urls = []
    while page:
        a_urls += get_all_article_urls(page)

        page = get_next_page(page)

    logging.info(f"Total articles collected: {len(a_urls)}")
    return a_urls


def save_article_urls(a_urls):
    with open(ARTICLE_URL_DB, "w") as f:
        f.write("\n".join(a_urls))


def save_articles(articles):
    sys.setrecursionlimit(100000)

    with open(ARTICLE_DB, "wb") as file:
        pickle.dump(articles, file, protocol=pickle.HIGHEST_PROTOCOL)


def load_article_urls():
    with open(ARTICLE_URL_DB, "r") as f:
        return f.read().splitlines()


def load_articles():
    with open(ARTICLE_DB, "rb") as file:
        return pickle.load(file)


def focus_on_article(tag):
    return tag.find("div", attrs={"id": re.compile("post-*")})


def focus_on_examples(tag):
    needles = ["Παραδείγματα:", "Παράδειγμα:", "Το είδαμε στα", "σε ιστοσελίδες όπως"]
    return tag.find_all(
        lambda t: t.name == "p" and any(needle in t.text for needle in needles)
    )


def collect_fakenewswebsites(tag):
    websites = []
    for a in tag.find_all("a", attrs={"href": True}):
        if a.string:
            websites.append(a.string.strip())
        else:
            logging.warning(f"{a} has no string representation. Ignoring it.")
    return websites


def main():
    init_cache()

    if not path.isfile(ARTICLE_URL_DB):
        logging.info("Looking for article URLs")
        a_urls = scrap_article_urls()
        save_article_urls(a_urls)
    else:
        a_urls = load_article_urls()
        logging.info(f"Article URLs found in DB: {len(a_urls)}")

    if not path.isfile(ARTICLE_DB):
        logging.info("Downloading articles from URLs")
        articles = []
        for a_url in a_urls:
            articles.append(focus_on_article(download_page(a_url)))
        save_articles(articles)

    logging.info(f"Loading articles from {ARTICLE_DB}")
    articles = load_articles()

    logging.info(f"Articles loaded: {len(articles)}")

    no_examples = 0
    fakenews_website_names = []
    for article in articles:
        examples_paragraph = focus_on_examples(article)

        if len(examples_paragraph) == 0:
            no_examples += 1
            logging.debug(f"'{article.title.string.strip()}' has no examples.")
        elif len(examples_paragraph) > 1:
            logging.error(f"'{article.title.string}' has multiple Examples...")

        for exam in examples_paragraph:
            fakenews_website_names += collect_fakenewswebsites(exam)

    logging.info(f"Number of articles without examples: {no_examples}")
    logging.info(f"Fake news websites by article frequency:")

    ranks = Counter(fakenews_website_names).most_common()
    logging.info(pformat(ranks))


if __name__ == "__main__":
    main()
