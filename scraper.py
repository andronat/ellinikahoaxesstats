import logging
import requests

from bs4 import BeautifulSoup

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


def main():
    root_url = "https://www.ellinikahoaxes.gr/category/kathgories/"
    logging.info(f"Root page: {root_url}")

    page = download_page(root_url)

    while page:
        page = get_next_page(page)


if __name__ == "__main__":
    main()
