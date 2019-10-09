from collections import defaultdict
from functools import partial, update_wrapper
from itertools import chain, count
import json
from operator import itemgetter
import os
from typing import TYPE_CHECKING, Callable, Dict, Generator, Iterable, List, Tuple

from github import Github, UnknownObjectException
import requests

if TYPE_CHECKING:
    from github.repository import Repository
    from github.ContentFile import ContentFile


USER_AGENT = 'instawow (https://github.com/layday/instawow)'

curseforge_slugs_name = 'curseforge-slugs-v2'      # v2
combined_folders_name = 'combined-folders'         # v1
combined_names_name = 'combined-names-v2'          # v2

dump = partial(json.dumps, separators=(',', ':'))
dump_indented = partial(json.dumps, indent=2)


def tuplefy(fn: Callable) -> Callable:
    return update_wrapper((lambda *a, **kw: tuple(fn(*a, **kw))), fn)


@tuplefy
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


def upload(repo: 'Repository', contents: List['ContentFile'], filename: str, data: str) -> None:
    try:
        sha = next(f for f in contents if f.path == filename).sha
    except StopIteration:
        mutate_file = partial(repo.create_file, filename)
    else:
        mutate_file = partial(repo.update_file, filename, sha=sha)
    mutate_file(f'Update {filename}', data, branch='data')


# def upload(repo: 'Repository', contents: List['ContentFile'], filename: str, data: str) -> None:
#     with open(filename, 'w') as file:
#         file.write(data)


@tuplefy
def get_curseforge_compatibility(latest_files: List[dict]) -> Generator[str, None, None]:
    if any(v.startswith('8.') for f in latest_files for v in f['gameVersion']):
        yield 'retail'
    if any(f['gameVersionFlavor'] == 'wow_classic' for f in latest_files):
        yield 'classic'


@tuplefy
def get_wowi_compatibility(addon: dict) -> Generator[str, None, None]:
    compatibility = addon['UICompatibility']
    if compatibility:
        if any(v['version'].startswith('8.') for v in compatibility):
            yield 'retail'
        if any(v['name'] == 'WoW Classic' for v in compatibility):
            yield 'classic'


def smoosh_curseforge_folders(it: Iterable) -> Iterable:
    smooshed_addons = defaultdict(set)        # type: ignore
    for addon in it:
        defn, compat, folders = addon
        smooshed_addons[defn, folders] |= set(compat)
    return ((d, sorted(c, key=('retail', 'classic').index), f)
            for (d, f), c in smooshed_addons.items())


def main() -> None:
    token = os.environ['MORPH_GITHUB_ACCESS_TOKEN']
    github = Github(token, user_agent=USER_AGENT)
    repo = github.get_repo('layday/instascrape')
    # The contents API has a 1 MB cap on file contents.  However if the
    # path doesn't point to a file, the contents aren't actually included in the
    # response body
    contents = repo.get_contents('', ref='data')

    curseforge_catalogue = scrape_curseforge_catalogue()
    (tukui_retail_catalogue,
     tukui_classic_catalogue) = scrape_tukui_catalogue()
    wowi_catalogue = scrape_wowi_catalogue()

    curseforge_slugs = {a['slug']: str(a['id']) for a in curseforge_catalogue}
    upload(repo, contents, curseforge_slugs_name + '.json',
           dump_indented(curseforge_slugs))
    upload(repo, contents, curseforge_slugs_name + '.compact.json',
           dump(curseforge_slugs))

    folders = chain(
        smoosh_curseforge_folders(
            (('curse', str(f['projectId'])),
             get_curseforge_compatibility([f]),
             tuple(m['foldername'] for m in f['modules']))
            for a in curseforge_catalogue
            for f in a['latestFiles']
            # Ignore lib-less uploads
            if not f['exposeAsAlternative']
            # Ignore files predating BfA or Classic
            and get_curseforge_compatibility([f])),
        ((('wowi', a['UID']),
          get_wowi_compatibility(a) or ['retail'],
          a['UIDir'])
         for a in wowi_catalogue),)
    combined_folders = list(folders)
    upload(repo, contents, combined_folders_name + '.json',
           dump_indented(combined_folders))
    upload(repo, contents, combined_folders_name + '.compact.json',
           dump(combined_folders))

    names = chain(
        ((a['name'], ('curse', str(a['id'])), get_curseforge_compatibility(a['latestFiles']))
         for a in curseforge_catalogue),
        ((a['name'], ('tukui', a['id']), ['retail'])
         for a in tukui_retail_catalogue),
        ((a['name'], ('tukui', a['id']), ['classic'])
         for a in tukui_classic_catalogue),
        ((a['UIName'], ('wowi', a['UID']), get_wowi_compatibility(a))
         for a in wowi_catalogue),)
    combined_names = list(filter(itemgetter(2), names))
    upload(repo, contents, combined_names_name + '.json',
           dump_indented(combined_names))
    upload(repo, contents, combined_names_name + '.compact.json',
           dump(combined_names))


if __name__ == '__main__':
    main()
