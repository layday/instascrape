from functools import partial
from itertools import count
import json
import os
from typing import TYPE_CHECKING, Generator, Tuple

from github import Github
import requests

if TYPE_CHECKING:
    from github.repository import Repository


USER_AGENT = 'instawow (https://github.com/layday/instawow)'

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


def update(repo: 'Repository', filename: str, data: str) -> None:
    file = repo.get_contents(filename, ref='data')
    repo.update_file(file.path, f'Update {filename}', data, file.sha, branch='data')


def main() -> None:
    slugs = {a['slug']: a['id'] for a in scrape_catalogue()}
    github = Github(os.environ['MORPH_GITHUB_ACCESS_TOKEN'], user_agent=USER_AGENT)
    repo = github.get_repo('layday/instascrape')
    update(repo, 'curseforge-slugs.json', dump_indented(slugs))


if __name__ == '__main__':
    main()
