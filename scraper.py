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

curseforge_slugs_name = 'curseforge-slugs-v2.json'      # v2
# curseforge_folders_name = 'curseforge-folders.json'   # removed
combined_folders_name = 'combined-folders.json'         # v1
combined_names_name = 'combined-names-v2.json'          # v2

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


def get_curseforge_compatibility(latest_files: List[dict]) -> Generator[str, None, None]:
    if any(v.startswith('8.') for f in latest_files for v in f['gameVersion']):
        yield 'retail'
    if any(f['gameVersionFlavor'] == 'wow_classic' for f in latest_files):
        yield 'classic'


def get_wowi_compatibility(addon: dict) -> Generator[str, None, None]:
    compatibility = addon['UICompatibility']
    if compatibility:
        if any(v['version'].startswith('8.') for v in compatibility):
            yield 'retail'
        if any(v['name'] == 'WoW Classic' for v in compatibility):
            yield 'classic'


def main() -> None:
    github = Github(os.environ['MORPH_GITHUB_ACCESS_TOKEN'], user_agent=USER_AGENT)
    repo = github.get_repo('layday/instascrape')

    curseforge_catalogue = list(scrape_curseforge_catalogue())
    (tukui_retail_catalogue,
     tukui_classic_catalogue) = scrape_tukui_catalogue()
    wowi_catalogue = scrape_wowi_catalogue()

    curseforge_slugs = {a['slug']: str(a['id']) for a in curseforge_catalogue}
    upload(repo, curseforge_slugs_name, dump_indented(curseforge_slugs))

    folders = chain(
        ((('curse', str(f['projectId'])),
          list(get_curseforge_compatibility([f])) or ['retail'],
          [m['foldername'] for m in f['modules']])
         for a in curseforge_catalogue
         for f in a['latestFiles']
         # Ignore lib-less uploads
         if not f['exposeAsAlternative']
         # Ignore files predating BfA or Classic
         and f['gameVersionFlavor'] == 'wow_classic'
         or any(v.startswith('8.') for v in f['gameVersion'])),
        ((('wowi', a['UID']),
          list(get_wowi_compatibility(a)) or ['retail'],
          a['UIDir'])
         for a in wowi_catalogue),)
    combined_folders = list(folders)
    upload(repo, combined_folders_name, dump_indented(combined_folders))

    names = chain(
        ((a['name'], ('curse', str(a['id'])), list(get_curseforge_compatibility(a['latestFiles'])))
         for a in curseforge_catalogue),
        ((a['name'], ('tukui', a['id']), ['retail'])
         for a in tukui_retail_catalogue),
        ((a['name'], ('tukui', a['id']), ['classic'])
         for a in tukui_classic_catalogue),
        ((a['UIName'], ('wowi', a['UID']), list(get_wowi_compatibility(a)))
         for a in wowi_catalogue),)
    combined_names = list(filter(itemgetter(2), names))
    upload(repo, combined_names_name, dump_indented(combined_names))


if __name__ == '__main__':
    main()
