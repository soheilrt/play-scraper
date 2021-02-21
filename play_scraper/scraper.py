# -*- coding: utf-8 -*-

import logging

try:
    from urllib import quote_plus
    from urlparse import urljoin
except ImportError:
    from urllib.parse import urljoin, quote_plus, urlparse, parse_qs
try:
    basestring
except NameError:
    basestring = str

import requests
from bs4 import BeautifulSoup

from play_scraper import settings as s
from play_scraper.constants import HL_LANGUAGE_CODES, GL_COUNTRY_CODES
from play_scraper.utils import (
    build_url,
    extract_id_query,
    generate_post_data,
    multi_futures_app_request,
    parse_app_details,
    parse_card_info,
    parse_cluster_card_info,
    send_request, build_cluster_url, build_category_url, get_query_params,
)


class PlayScraper(object):
    def __init__(self, hl="en", gl="us"):
        self.language = hl
        if self.language not in HL_LANGUAGE_CODES:
            raise ValueError(
                "{hl} is not a valid language interface code.".format(hl=self.language)
            )
        self.geolocation = gl
        if self.geolocation not in GL_COUNTRY_CODES:
            raise ValueError(
                "{gl} is not a valid geolocation country code.".format(
                    gl=self.geolocation
                )
            )
        self.params = {"hl": self.language, "gl": self.geolocation}

        self._base_url = s.BASE_URL
        self._suggestion_url = s.SUGGESTION_URL
        self._search_url = s.SEARCH_URL
        self._pagtok = s.PAGE_TOKENS
        self._log = logging.getLogger(__name__)
        self.list_item_promo_selector = "div.vU6FJ.HPtqMb > div > div.b8cIId.ReQCgd.KdSQre.fmVS2c > a"
        self.list_item_selector = "div.ZmHEEd > div > c-wiz > div > div > div.uzcko > div > div > a"

    def _parse_multiple_apps(self, list_response):
        """Extracts app ids from a list's Response object, sends GET requests to
        each app, parses detailed info and returns all apps in a list.

        :param list_response: the Response object from a list request
        :return: a list of app dictionaries
        """
        # TODO: refactor to better handle multiple possible list HTMLs and selectors
        # to extract out app ids
        soup = BeautifulSoup(list_response.content, "lxml", from_encoding="utf8")

        app_ids = [
            x.attrs["data-docid"] for x in soup.select("span.preview-overlay-container")
        ]
        if not app_ids:
            app_ids = [
                extract_id_query(x.attrs.get("href"))
                for x in soup.select("div.p63iDd > a")
            ]

        return multi_futures_app_request(app_ids, params=self.params)

    def details(self, app_id):
        """Sends a GET request and parses an application's details.

        :param app_id: the app to retrieve details, e.g. 'com.nintendo.zaaa'
        :return: a dictionary of app details
        """
        url = build_url("details", app_id)

        try:
            response = send_request("GET", url, params=self.params)
            soup = BeautifulSoup(response.content, "lxml", from_encoding="utf8")
        except requests.exceptions.HTTPError as e:
            raise ValueError(
                "Invalid application ID: {app}. {error}".format(app=app_id, error=e)
            )

        app_json = parse_app_details(soup)
        app_json.update({"app_id": app_id, "url": url})
        return app_json

    def developer(self, developer, results=None, page=None, detailed=False):
        """Sends a POST request and retrieves a list of the developer's
        published applications on the Play Store.

        :param developer: developer name to retrieve apps from, e.g. 'Disney'
        :param results: the number of app results to retrieve
        :param page: the page number to retrieve
        :param detailed: if True, sends request per app for its full detail
        :return: a list of app dictionaries
        """
        if not isinstance(developer, basestring) or developer.isdigit():
            raise ValueError(
                "Parameter 'developer' must be the developer name, not the developer id."
            )

        results = s.DEV_RESULTS if results is None else results
        page = 0 if page is None else page
        page_num = (results // 20) * page
        if not 0 <= page_num <= 12:
            raise ValueError(
                "Page out of range. (results // 20) * page must be between 0 - 12"
            )
        pagtok = self._pagtok[page_num]

        url = build_url("developer", developer)
        data = generate_post_data(results, 0, pagtok)
        response = send_request("POST", url, data, self.params)

        if detailed:
            apps = self._parse_multiple_apps(response)
        else:
            soup = BeautifulSoup(response.content, "lxml", from_encoding="utf8")
            apps = [
                parse_card_info(app) for app in soup.select('div[data-uitype="500"]')
            ]

        return apps

    def suggestions(self, query):
        """Sends a GET request and retrieves a list of autocomplete suggestions
        matching the query term(s).

        :param query: search query term(s) to retrieve autocomplete suggestions
        :return: a list of suggested search queries, up to 5
        """
        if not query:
            raise ValueError("Cannot get suggestions for an empty query.")

        self.params.update({"json": 1, "c": 0, "query": query})

        response = send_request("GET", self._suggestion_url, params=self.params)
        suggestions = [q["s"] for q in response.json()]
        return suggestions

    def search(self, query, page=None, detailed=False):
        """Sends a POST request and retrieves a list of applications matching
        the query term(s).

        :param query: search query term(s) to retrieve matching apps
        :param page: the page number to retrieve. Max is 12.
        :param detailed: if True, sends request per app for its full detail
        :return: a list of apps matching search terms
        """
        page = 0 if page is None else int(page)
        if page > len(self._pagtok) - 1:
            raise ValueError(
                "Parameter 'page' ({page}) must be between 0 and 12.".format(page=page)
            )

        pagtok = self._pagtok[page]
        data = generate_post_data(0, 0, pagtok)

        self.params.update({"q": quote_plus(query), "c": "apps"})

        response = send_request("POST", self._search_url, data, self.params)
        soup = BeautifulSoup(response.content, "lxml", from_encoding="utf8")

        if detailed:
            apps = self._parse_multiple_apps(response)
        else:
            apps = [parse_cluster_card_info(app) for app in soup.select("div.Vpfmgd")]

        return apps

    def similar(self, app_id, detailed=False, **kwargs):
        """Sends a GET request, follows the redirect, and retrieves a list of
        applications similar to the specified app.

        :param app_id: app to retrieve details from, e.g. 'com.nintendo.zaaa'
        :param detailed: if True, sends request per app for its full detail
        :return: a list of similar apps
        """
        url = build_url("similar", app_id)
        response = send_request("GET", url, params=self.params, allow_redirects=True)
        soup = BeautifulSoup(response.content, "lxml", from_encoding="utf8")

        if detailed:
            apps = self._parse_multiple_apps(response)
        else:
            apps = [parse_cluster_card_info(app) for app in soup.select("div.Vpfmgd")]

        return apps

    def categories(self, ignore_promotions=True):
        """Sends a GET request to the front page (app store base url), parses
        and returns a list of all available categories.
        """
        categories = {}

        response = send_request("GET", s.BASE_URL, params=self.params)
        soup = BeautifulSoup(response.content, "lxml", from_encoding="utf8")

        category_links = soup.select(
            'div[id*="action-dropdown-children"] a[href*="category"]'
        )
        age_query = "?age="

        for cat in category_links:
            url = urljoin(s.BASE_URL, cat.attrs["href"])
            category_id = url.split("/")[-1]
            name = cat.string.strip()

            if age_query in category_id:
                category_id = "FAMILY"
                url = url.split("?")[0]
                name = "Family"

            if category_id not in categories:
                if ignore_promotions and "/store/apps/category/" not in url:
                    continue

                categories[category_id] = {
                    "name": name,
                    "url": url,
                    "category_id": category_id,
                }

        return categories

    def category_clusters(self, category):
        """

        :param category:
        :return:
        """

        clusters = {}
        cluster_selector = "c-wiz > c-wiz > div > div.Z3lOXb > div.xwY9Zc > a"

        category_url = build_category_url(category=category)
        response = send_request("GET", category_url)

        soup = BeautifulSoup(response.content, 'lxml', from_encoding='utf8')
        cluster_elements = soup.select(cluster_selector)

        for element in cluster_elements:
            title = element.h2.text
            gsr = get_query_params(element['href'])['gsr'][0]

            clusters[title] = gsr

        return clusters

    def cluster_items(self, gsr, detailed=False):
        """
        Get cluster page items
        https://play.google.com/store/apps/collection/cluster?clp=0g4cChoKFHRvcHNlbGxpbmdfZnJlZV9HQU1FEAcYAw%3D%3D:S:ANO1ljJ_Y5U&gsr=Ch_SDhwKGgoUdG9wc2VsbGluZ19mcmVlX0dBTUUQBxgD:S:ANO1ljL4b8c
        :param gsr: cluster id
        :return: list of app details
        """
        cluster_url = build_cluster_url(gsr=gsr)
        response = send_request("GET", cluster_url)

        soup = BeautifulSoup(response.content, 'lxml', from_encoding='utf8')
        items_elements = soup.select(self.list_item_selector)

        if not len(items_elements):
            items_elements = soup.select(self.list_item_promo_selector)

        app_ids = [get_query_params(element['href'])['id'][0] for element in items_elements]

        if not detailed:
            return [{'app_id': app_id} for app_id in app_ids]

        return multi_futures_app_request(app_ids=app_ids)

    def category_items(self, category, detailed=False):
        """
        list of apps in category main page
        :param detailed:
        :param category:
        :return:
        """
        category_url = build_category_url(category)
        response = send_request("GET", category_url)

        soup = BeautifulSoup(response.content, 'lxml', from_encoding='utf8')
        items_elements = soup.select(self.list_item_selector)

        if not len(items_elements):
            items_elements = soup.select(self.list_item_promo_selector)

        app_ids = [get_query_params(element['href'])['id'][0] for element in items_elements]

        if not detailed:
            return [{'app_id': app_id} for app_id in app_ids]

        return multi_futures_app_request(app_ids=app_ids)

    def category_tabs(self, category):
        pass  # todo implement me!
