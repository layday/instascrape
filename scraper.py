from functools import partial
from itertools import count
import json
import os
from typing import Generator, Tuple

from github import Github
import requests


user_agent = 'instawow (https://github.com/layday/instawow)'


def scrape() -> Generator[Tuple[str, int], None, None]:
    get = partial(requests.get,
                  'https://addons-ecs.forgesvc.net/api/v2/addon/search',
                  headers={'User-Agent': user_agent})
    step = 1000

    for index in count(0, step):
        data = get(params={'gameId': '1', 'pageSize': step, 'index': index}).json()
        if not data:
            break
        for addon in data:
            yield (addon['slug'], addon['id'])


def upload(data: str) -> None:
    filename = 'curseforge-slugs.json'
    github = Github(os.environ['MORPH_GITHUB_ACCESS_TOKEN'], user_agent=user_agent)
    repo = github.get_repo('layday/intascrape')
    file = repo.get_contents(filename, ref='data')
    repo.update_file(file.path, 'Update data', data, file.sha, branch='data')


def main() -> None:
    data = json.dumps(dict(scrape()))
    upload(data)


if __name__ == '__main__':
    main()
