import concurrent
import json
import os
from concurrent.futures.thread import ThreadPoolExecutor
from datetime import datetime

import play_scraper
import play_scraper.utils
import play_scraper.settings
from play_scraper.scraper import PlayScraper

scraper = PlayScraper()
play_scraper.settings.CONCURRENT_REQUESTS = 25
base_addr = "/"
stats = {
    'details-checked': set(),
    'developers-not-checked': set(),
    'developers-checked': set(),
    'similars-checked': set(),
    'similars-not-checked': set(),
    'categories-checked': set(),
}


def load_stats():
    log('loading stats....')
    for file in stats:
        addr = os.path.join(base_addr, f'stats/{file}.txt')
        try:
            with open(addr, 'r+') as d:
                stats[file] = set(d.read().split('\n'))
        except:
            log("file: {} not found!".format(addr))
    log("Done")


def set_stat(kind, info):
    if info in stats[kind]:
        return

    addr = os.path.join(base_addr,f'stats/{kind}.txt')
    with open(addr, 'a+') as f:
        f.write(info + '\n')

    stats[kind].add(info)


def set_new_app_stats(app_info):
    set_stat('details-checked', app_info['app_id'])

    if app_info['app_id'] not in stats['similars-checked']:
        set_stat('similars-not-checked', app_info['app_id'])

    if app_info['developer_id'] not in stats['developers-checked'] and app_info['developer_id'] != '':
        set_stat('developers-not-checked', app_info['developer_id'])


def save_app_details(app_info):
    addr = os.path.join(base_addr,f'apps/{app_info["app_id"]}.json')

    with open(addr, 'w', encoding='utf-8') as app_file:
        info_json = json.dumps(app_info, indent=4, )
        app_file.write(info_json)

    set_new_app_stats(app_info)


def get_and_save_app_details(app_ids):
    not_exists = [i for i in app_ids if i not in stats['details-checked']]
    app_details = play_scraper.utils.multi_futures_app_request(not_exists)

    for detail in app_details:
        save_app_details(detail)


def get_and_save_similar(app_id):
    try:
        similars = scraper.similar(app_id)
        new_app_ids = [i['app_id'] for i in similars if i['app_id'] not in stats['details-checked']]
        log("New Apps: {}({})".format(len(new_app_ids), len(similars)))
        get_and_save_app_details(app_ids=new_app_ids)
    except Exception as e:
        log("Error: {}".format(str(e)))


def get_and_save_developer_apps(developer_id):
    set_stat("developers-checked", developer_id)
    apps_details = scraper.developer(developer=developer_id, results=120, detailed=True)
    for detail in apps_details:
        save_app_details(detail)


def get_categories_apps():
    log("Getting Categories Apps ....")
    categories = scraper.categories()
    log("Total Categories: {}".format(len(categories)))
    for i, category in enumerate(categories):
        if category in stats['categories-checked']:
            continue

        log(f"{i} - Category: {category}")
        category_items = [i['app_id'] for i in scraper.category_items(category)]
        get_and_save_app_details(category_items)

        category_clusters = scraper.category_clusters(category)
        log("Category Clusters: {} - {}".format(category, len(category_clusters)))
        for key in category_clusters:
            log("Cluster: {} - {}".format(category, key))
            cluster_items = [i['app_id'] for i in scraper.cluster_items(category_clusters[key])]
            get_and_save_app_details(cluster_items)

        set_stat('categories-checked', category)
        log_stats()


def get_similar_apps():
    while len(stats['similars-not-checked']):
        app_id = stats['similars-not-checked'].pop()
        if app_id != '':
            log("Similar Apps For: {}".format(app_id))
            get_and_save_similar(app_id)
            set_stat('similars-checked', app_id)
            log_stats()


def get_developers_apps():
    while len(stats['developers-not-checked']):
        developer_id = stats['developers-not-checked'].pop()
        if developer_id != '':
            get_and_save_developer_apps(developer_id)


def main():
    load_stats()
    get_categories_apps()
    # get_developers_apps()
    get_similar_apps()


def log_stats():
    log("Apps Stat: {}".format(" - ".join([f'{key}: {len(stats[key])}' for key in stats])))


def log(text, end='\n'):
    print("[{date}] - {log}".format(date=datetime.now(), log=text), end=end)


if __name__ == '__main__':
    main()