from functools import partial
from itertools import chain, count
import json
from operator import itemgetter
import os
from typing import TYPE_CHECKING, Dict, Generator, List, Tuple

from github import Github, UnknownObjectException
import requests

if TYPE_CHECKING:
    from github.repository import Repository


USER_AGENT = 'instawow (https://github.com/layday/instawow)'

curseforge_slugs_name = 'curseforge-slugs.json'     # v1
curseforge_folders_name = 'curseforge-folders.json' # v1
combined_names_name = 'combined-names.json'         # v1

dump_indented = partial(json.dumps, indent=2)


def scrape_curseforge_catalogue() -> Generator[dict, None, None]:
    get = partial(requests.get,
                  'https://addons-ecs.forgesvc.net/api/v2/addon/search',
                  headers={'User-Agent': USER_AGENT})
    step = 1000

    for index in count(0, step):
        data = get(params={'gameId': '1',
                           'sort': '3',     # Alphabetical
                           'pageSize': step, 'index': index}).json()
        if not data:
            break
        yield from iter(data)


def scrape_tukui_catalogue() -> Generator[list, None, None]:
    urls = ('https://www.tukui.org/api.php?addons=all',
            'https://www.tukui.org/api.php?classic-addons=all',)
    for url in urls:
        response = requests.get(url, headers={'User-Agent': USER_AGENT})
        yield response.json()


def scrape_wowi_catalogue() -> List[dict]:
    url = 'https://api.mmoui.com/v3/game/WOW/filelist.json'
    response = requests.get(url, headers={'User-Agent': USER_AGENT})
    return response.json()


def upload(repo: 'Repository', filename: str, data: str) -> None:
    try:
        file = repo.get_contents(filename, ref='data')
    except UnknownObjectException:
        mutate_file = partial(repo.create_file, filename)
    else:
        mutate_file = partial(repo.update_file, file.path, sha=file.sha)
    mutate_file(f'Update {filename}', data, branch='data')


def main() -> None:
    curseforge_catalogue = list(scrape_curseforge_catalogue())
    tukui_retail_catalogue, tukui_classic_catalogue = scrape_tukui_catalogue()
    wowi_catalogue = scrape_wowi_catalogue()

    curseforge_slugs = {a['slug']: a['id'] for a in curseforge_catalogue}
    curseforge_folders = [
        (f['projectId'],
         f['gameVersionFlavor'],
         [m['foldername'] for m in f['modules']])
        for a in curseforge_catalogue
        for f in a['latestFiles']
        # Ignore lib-less uploads
        if not f['isAlternate']
        # Ignore files predating BfA or Classic
        and f['gameVersionFlavor'] == 'wow_classic'
        or any(v.startswith('8.') for v in f['gameVersion'])]

    def get_curseforge_compatibility(addon):
        if any(v['gameVersion'].startswith('8.') for v in addon['gameVersionLatestFiles']):
            yield 'retail'
        if any(v['gameVersionFlavor'] == 'wow_classic' for v in addon['gameVersionLatestFiles']):
            yield 'classic'

    def get_wowi_compatibility(addon):
        if addon['UICompatibility']:
            if any(v['version'].startswith('8.') for v in addon['UICompatibility']):
                yield 'retail'
            if any(v['name'] == 'WoW Classic' for v in addon['UICompatibility']):
                yield 'classic'

    names = chain(
        ((a['name'], ('curse', a['id']), list(get_curseforge_compatibility(a)))
         for a in curseforge_catalogue),
        ((a['name'], ('tukui', a['id']), ['retail'])
         for a in tukui_retail_catalogue),
        ((a['name'], ('tukui', a['id']), ['classic'])
         for a in tukui_classic_catalogue),
        ((a['UIName'], ('wowi', a['UID']), list(get_wowi_compatibility(a)))
         for a in wowi_catalogue),)
    combined_names = list(filter(itemgetter(2), names))

    github = Github(os.environ['MORPH_GITHUB_ACCESS_TOKEN'], user_agent=USER_AGENT)
    repo = github.get_repo('layday/instascrape')
    upload(repo, curseforge_slugs_name, dump_indented(curseforge_slugs))
    upload(repo, curseforge_folders_name, dump_indented(curseforge_folders))
    upload(repo, combined_names_name, dump_indented(combined_names))


if __name__ == '__main__':
    main()
