# !/usr/bin/env python
# encoding: utf-8
#
# This file is part of ckanext-doi
# Created by the Natural History Museum in London, UK

from datetime import datetime
import urllib.parse

import dateutil.parser as parser
from ckan.plugins import toolkit
from ckantools.config import get_debug, get_setting


def package_get_year(pkg_dict):
    """
    Helper function to return the package year published.

    :param pkg_dict: return:
    """
    release_date = pkg_dict.get('release_date', '')
    if not isinstance(release_date, datetime) and release_date:
        release_date = parser.parse(release_date)
    return release_date.year if release_date else None


def get_site_title():
    """
    Helper function to return the config site title, if it exists.

    :returns: str site title
    """
    return toolkit.config.get('ckanext.doi.site_title')


def get_site_url():
    """
    Get the site URL.

    Try and use ckanext.doi.site_url but if that's not set use ckan.site_url.
    """
    site_url = toolkit.config.get(
        'ckanext.doi.site_url', toolkit.config.get('ckan.site_url', '')
    )
    return site_url.rstrip('/')


def date_or_none(date_object_or_string):
    """
    Try and convert the given object into a datetime; if not possible, return None.

    :param date_object_or_string: a datetime or date string
    :return: datetime or None
    """
    if isinstance(date_object_or_string, datetime):
        return date_object_or_string
    elif isinstance(date_object_or_string, str):
        return parser.parse(date_object_or_string)
    else:
        return None


def doi_test_mode():
    """
    Determines whether we're running in test mode.

    :return: bool
    """
    return toolkit.asbool(get_setting('ckanext.doi.test_mode', default=get_debug()))


def get_authors(creator_list):
    """
    Get the authors of the package, handling both persons and organizations.

    :param creator_list: list of dicts (person/organisation)
    :return: authors string
    """
    if not creator_list:
        return None

    authors = []
    for entry in creator_list:
        if entry.get('type') == 'person':
            last = entry.get('last_name', '')
            first = entry.get('first_name', '')
            formatted = f"{last}, {first[:1]}." if last or first else ''
            if formatted:
                authors.append(formatted)
        elif entry.get('type') == 'organisation':
            name = entry.get('name') or entry.get('acronym', '')
            if name:
                authors.append(name)
    return ', '.join(authors) if authors else None


def get_doi_metadata(pkg_dict):
    """
    Get the DOI metadata for the current package.

    :return: dict
    """
    metadata = {
        'identifier': pkg_dict['doi'],
        'title': pkg_dict['title'],
        'publisher': pkg_dict['publisher'],
        'publicationYear': package_get_year(pkg_dict),
        'doi_uri': 'https://doi.org/' + pkg_dict['doi'],
        'creators': get_authors(pkg_dict.get('creators', [])),
        'subjects': pkg_dict['tags'],
        'description': pkg_dict['notes'],
        'resourceType': "Data set",
    }

    return metadata


def url_encode(string):
    """
    Convert the identifier to a URL.

    :param identifier: the identifier
    :return: the URL
    """
    string = urllib.parse.quote(string, safe='')
    return string
