import requests
from flask import Blueprint, Response
from ckan.plugins import toolkit as tk

doi = Blueprint('doi', __name__)


def view_doi(identifier, format):
    doi_domain = 'api.test.datacite.org' if tk.h.doi_test_mode() else 'api.datacite.org'

    url = (
        f'https://{doi_domain}/dois/application/{format}/{identifier}'
    )

    def fetch_content(url):
        response = requests.get(url)
        if response.status_code == 200:
            return response.text
        else:
            return tk.redirect_to(url)

    content = fetch_content(url)
    response = Response(content)
    response.headers['Content-Type'] = f'text/{format}'
    response.headers['Content-Disposition'] = 'inline'
    return response


doi.add_url_rule('/dataset/doi/<identifier>/<format>', 'view_doi', view_doi)


def registred_views():
    return [doi]
