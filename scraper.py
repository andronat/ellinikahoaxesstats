import logging
import os.path as path
import requests

from bs4 import BeautifulSoup

DB_FILENAME = "all_article_urls.txt"

logging.basicConfig(format="%(message)s", level=logging.INFO)


def download_page(url):
    page = requests.get(url)
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


def load_article_urls():
    with open(DB_FILENAME, "r") as f:
        return f.read().splitlines()


def main():
    db_path = path.join(path.dirname(path.realpath(__file__)), DB_FILENAME)
    if not path.isfile(db_path):
        logging.info(f"Looking for article URLs")
        a_urls = scrap_article_urls()
        save_article_urls(a_urls)
    else:
        a_urls = load_article_urls()
        logging.info(f"Article URLs found in DB: {len(a_urls)}")


if __name__ == "__main__":
    main()
