import glob
import logging
import os.path as path
import re
import requests

from bs4 import BeautifulSoup
from collections import Counter
from pprint import pformat

DB_FILENAME = "all_article_urls.txt"

logging.basicConfig(format="%(message)s", level=logging.INFO)


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
    with open(DB_FILENAME, "w") as f:
        f.write("\n".join(a_urls))


def create_name_from_url(url):
    year, month, day, title = url.split("/")[3:7]
    # In order to avoid date collisions but still been able to read the dates
    # let's hash the title.
    salt = str(abs(hash(title)) % (10 ** 8))
    return "-".join([year, month, day, salt])


def save_page(page, filename):
    with open(f"page-{filename}.html", "w", encoding="utf-8") as file:
        file.write(str(page.prettify()))


def load_article_urls():
    with open(DB_FILENAME, "r") as f:
        return f.read().splitlines()


def load_pages():
    pages = []
    for pagefile in glob.glob("page-*.html"):
        with open(pagefile, "r", encoding="utf-8") as file:
            pages.append(BeautifulSoup(file.read(), "html.parser"))
    return pages


def focus_on_article(tag):
    return tag.find("div", attrs={"id": re.compile("post-*")})


def focus_on_examples(tag):
    needles = ["Παραδείγματα:", "Παράδειγμα:"]
    return tag.find_all(
        lambda t: t.name == "p" and any(needle in t.text for needle in needles)
    )


def collect_fakenewswebsites(tag):
    websites = []
    for a in tag.find_all("a", attrs={"href": True}):
        websites.append(a.string.strip())
    return websites


def main():
    db_path = path.join(path.dirname(path.realpath(__file__)), DB_FILENAME)
    if not path.isfile(db_path):
        logging.info(f"Looking for article URLs")
        a_urls = scrap_article_urls()
        save_article_urls(a_urls)
    else:
        a_urls = load_article_urls()
        logging.info(f"Article URLs found in DB: {len(a_urls)}")

    if len(glob.glob("page-*.html")) == 0:
        for a_url in a_urls:
            page = download_page(a_url)
            save_page(page, create_name_from_url(a_url))

    pages = load_pages()
    logging.info(f"Articles loaded: {len(pages)}")

    no_examples = 0
    fakenews_website_names = []
    for page in pages:
        article = focus_on_article(page)
        examples_paragraph = focus_on_examples(article)

        if len(examples_paragraph) == 0:
            no_examples += 1
            logging.debug(f"'{page.title.string.strip()}' has no examples.")
        elif len(examples_paragraph) > 1:
            logging.error(f"'{page.title.string}' has multiple Examples...")

        for exam in examples_paragraph:
            fakenews_website_names += collect_fakenewswebsites(exam)

    logging.info(f"Number of articles without examples: {no_examples}")
    logging.info(f"Fake news websites by article frequency:")

    ranks = Counter(fakenews_website_names).most_common()
    logging.info(pformat(ranks))


if __name__ == "__main__":
    main()
