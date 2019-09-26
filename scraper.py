from functools import partial
from itertools import count
import json
import os
from typing import TYPE_CHECKING, Generator, Tuple

from github import Github, UnknownObjectException
import requests

if TYPE_CHECKING:
    from github.repository import Repository


USER_AGENT = 'instawow (https://github.com/layday/instawow)'

slugs_name = 'curseforge-slugs.json'        # v1
folders_name = 'curseforge-folders.json'        # v1

dump_indented = partial(json.dumps, indent=2)


def scrape_catalogue() -> Generator[dict, None, None]:
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


def upload(repo: 'Repository', filename: str, data: str) -> None:
    try:
        file = repo.get_contents(filename, ref='data')
    except UnknownObjectException:
        mutate_file = partial(repo.create_file, filename)
    else:
        mutate_file = partial(repo.update_file, file.path, sha=file.sha)
    mutate_file(f'Update {filename}', data, branch='data')


def main() -> None:
    catalogue = list(scrape_catalogue())
    slugs = {a['slug']: a['id'] for a in catalogue}
    folders = [(f['projectId'],
                f['gameVersionFlavor'],
                [m['foldername'] for m in f['modules']])
               for a in catalogue
               for f in a['latestFiles']
               # Ignore lib-less uploads
               if not f['isAlternate']
               # Ignore files predating BfA or Classic
               and f['gameVersionFlavor'] == 'wow_classic'
               or any(v.startswith('8.') for v in f['gameVersion'])]

    github = Github(os.environ['MORPH_GITHUB_ACCESS_TOKEN'], user_agent=USER_AGENT)
    repo = github.get_repo('layday/instascrape')
    upload(repo, slugs_name, dump_indented(slugs))
    upload(repo, folders_name, dump_indented(folders))


if __name__ == '__main__':
    main()
