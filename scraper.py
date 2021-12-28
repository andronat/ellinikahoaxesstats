import dill as pickle
import gc
import logging
import os
import os.path as path
import re
import requests
import sys
import time

from bs4 import BeautifulSoup
from bs4.element import PageElement, ResultSet
from collections import Counter, defaultdict
from dataclasses import dataclass
from pprint import pformat
from tqdm import tqdm
from typing import Any, List, Set

LOCAL_DATA_DIR = path.join(path.dirname(path.realpath(__file__)), "cache")
ARTICLE_URL_DB = path.join(LOCAL_DATA_DIR, "all_article_urls.txt")
ARTICLE_DB = path.join(LOCAL_DATA_DIR, "articles.pickle")

logging.basicConfig(format="%(message)s", level=logging.INFO)

# Pickle doesn't support local lambdas. We had to do this ugly hack.
def keep_articles_that_have_examples(t):
    needles = [
        "Παραδείγματα:",
        "Παράδειγμα:",
        "Το είδαμε στα",
        "σε ιστοσελίδες όπως",
    ]
    return t.name == "p" and any(needle in t.text for needle in needles)


@dataclass
class Article:
    url: str
    examples: ResultSet[PageElement]
    bs_source: BeautifulSoup

    @staticmethod
    def _focus_on_article(raw):
        return raw.find("div", attrs={"id": re.compile("post-*")})

    @staticmethod
    def _find_all_examples(tag):
        return tag.find_all(keep_articles_that_have_examples)

    @staticmethod
    def from_raw(url, raw):
        article = Article._focus_on_article(raw)
        examples = Article._find_all_examples(article)
        return Article(url, examples, article)

    @staticmethod
    def _filter_link(link):
        def is_irrelevant_url(url: str) -> bool:
            needles = [
                "https://archive",
                "https://perma",
                "archive.org",
                "health.gov",
                "ellinikahoaxes.gr",
                "bit.ly",
                "facebook.com",
                "twitter.com",
                "youtube.com",
            ]
            return any(needle in url for needle in needles)

        # Sometimes an <a> tag has some generic string as data. We need to check
        # then if the underlying href is interesting.
        def should_check_href_instead_of_data(data):
            if re.search("[α-ωΑ-Ω]", data) or " " in data:
                return True
            else:
                needles = [
                    "1",
                    "2",
                    "3",
                    "4",
                    ",",
                    "#",
                    "facebook",
                    "Facebook",
                    "Twitter",
                    "twitter",
                    "twitter.com",
                    "YouTube",
                ]
                return any(data.startswith(needle) for needle in needles)

        # We are looking for .string as it is visible to the web representation.
        if not link.string:
            logging.debug(f"{link} has no data. Ignoring it.")
            return None

        tag_data = link.string.strip()
        check_href = should_check_href_instead_of_data(tag_data)

        if check_href:
            if is_irrelevant_url(link["href"]):
                # We skip examples that 'probably' point to evidence and not
                # fakenews websites.
                return None
            else:
                logging.debug(f"Found 'special' link: {link.prettify()}")
                try:
                    url = link["href"].split("/")[2:3][0]
                    return str(url)
                except IndexError:
                    logging.error(f"Failed to parse 'special' link: {link.prettify()}")
        else:
            return tag_data

    def has_examples(self) -> bool:
        return len(self.examples) > 0

    def find_all_links(self):
        return self.bs_source.find_all("a", attrs={"href": True})

    def find_all_links_in_examples(self):
        all = []
        for example in self.examples:
            all.extend(example.find_all("a", attrs={"href": True}))
        return all

    # Return a set with all websites that have been spotted to have fake news.
    # e.g. {'katohika.gr', 'pronews.gr'}
    def unique_fnns_in_examples(self) -> Set[str]:
        # Sometimes articles reference the same website in multiples areas. We
        # sound count them all as 1 occurrence.
        fnns = set()
        for link in self.find_all_links_in_examples():
            fnns.add(Article._filter_link(link))
        # TODO: Remove None. Why None exists?
        fnns = set(filter(None, fnns))
        return fnns


def init_cache() -> None:
    if not path.isdir(LOCAL_DATA_DIR):
        os.makedirs(LOCAL_DATA_DIR)


def download_page(url: str):
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


def scrap_article_urls() -> List[str]:
    root_url = "https://www.ellinikahoaxes.gr/category/kathgories/"
    logging.info(f"Root page: {root_url}")

    page = download_page(root_url)

    a_urls = []
    while page:
        a_urls += get_all_article_urls(page)

        page = get_next_page(page)

    logging.info(f"Total articles collected: {len(a_urls)}")
    return a_urls


def save_article_urls(a_urls: List[str]) -> None:
    with open(ARTICLE_URL_DB, "w") as f:
        f.write("\n".join(a_urls))


def save_articles(articles) -> None:
    sys.setrecursionlimit(100000)

    with open(ARTICLE_DB, "wb") as file:
        pickle.dump(articles, file, protocol=pickle.HIGHEST_PROTOCOL)


def load_article_urls() -> List[str]:
    with open(ARTICLE_URL_DB, "r") as f:
        return f.read().splitlines()


def load_articles():
    with open(ARTICLE_DB, "rb") as file:
        # This is a perf optimization from: https://stackoverflow.com/a/41733927/1067688
        gc.disable()
        out = pickle.load(file)
        gc.enable()
        return out


def merge_similar_fnns(fnns) -> List[str]:
    similar_names = {"pro-news.gr": "pronews.gr", "pronews": "pronews.gr"}

    hits = 0
    merged_names = []
    for fnn in fnns:
        if fnn in similar_names:
            fnn = similar_names[fnn]
            hits += 1
        merged_names.append(fnn)

    logging.info(f"Number of merged fnns: {hits}")

    return merged_names


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
        for a_url in tqdm(a_urls):
            article = Article.from_raw(a_url, download_page(a_url))
            articles.append(article)

        logging.info(f"Storing arcticles in: {ARTICLE_DB}")
        save_articles(articles)
        logging.info("All articles are now stored")

    logging.info(f"Loading articles from {ARTICLE_DB}")
    start_time = time.time()
    articles = load_articles()

    logging.info(
        f"Articles loaded: {len(articles)}. ({round(time.time() - start_time, 3)}s)"
    )

    no_examples_articles = []
    fnns = []  # fnn = Fake news name
    for article in articles:
        if not article.has_examples():
            # no_examples_articles.append(set(collect_relevant_names_from_urls(article)))
            no_examples_articles.append(article)
        else:
            fnns.extend(article.unique_fnns_in_examples())

    logging.info(f"Number of articles without examples: {len(no_examples_articles)}")

    fnns = merge_similar_fnns(fnns)

    # Q1: Top20 websites.
    fnw_names_freq = Counter(fnns)
    ranks = fnw_names_freq.most_common(20)
    logging.info(f"Fake news websites by article frequency:")
    logging.info(pformat(ranks))

    # Q2: Inverse search and then Top20.
    needles = fnw_names_freq.keys()
    from_inverse_search = defaultdict(int)
    articles_we_found_nothing = []

    # Preprocess all article as sets of words.
    no_examples_articles_as_sets = []
    for no_examples_article in no_examples_articles:
        no_examples_articles_as_sets.append(set(str(no_examples_article).split(" ")))

    logging.info(f"Conducting inverse-search with {len(needles)} keys.")

    for no_examples_article_as_set in no_examples_articles_as_sets:
        we_found_something = False

        for needle in needles:
            if needle in no_examples_article_as_set:
                from_inverse_search[needle] += 1
                we_found_something = True

        if not we_found_something:
            # TODO: keep a link maybe?
            articles_we_found_nothing.append(no_examples_article_as_set)

    fnw_names_freq.update(from_inverse_search)

    ranks_with_inverse = fnw_names_freq.most_common(20)
    logging.info(f"Fake news websites by article frequency (after inverse-search):")
    logging.info(pformat(ranks_with_inverse))

    logging.info(
        f"Number of articles without examples (after inverse-search): {len(articles_we_found_nothing)}"
    )

    # Assumption: Every article is a fake news article.
    # Q3: From Top20 when is the most recent post.
    # Q4: From Top20 when is the oldest post.
    # Q5: Find new trending website that is not in Top20 but has very recent posts.
    # Q6: In how many post we couldn't find info for websites. Are those fb posts?
    # Q7: Authors with most posts.
    # Q8: Honorable mentions: TV channels, newspapers


if __name__ == "__main__":
    main()
