# !/usr/bin/env python
# encoding: utf-8
#
# This file is part of ckanext-doi
# Created by the Natural History Museum in London, UK

from datetime import datetime

import dateutil.parser as parser
from ckan.plugins import toolkit
from ckantools.config import get_debug, get_setting


def package_get_year(pkg_dict):
    """
    Helper function to return the package year published.

    :param pkg_dict: return:
    """
    release_date = pkg_dict.get('releaseDate', '')
    if not isinstance(release_date, datetime) and release_date:
        release_date = parser.parse(release_date)
    return release_date.year or datetime.now().year


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
    Get the authors of the package.

    :param creator_list: package dictionary
    :return: authors string
    """
    if not creator_list:
        return None

    apa_doi_citation = ""
    for i, entry in enumerate(creator_list):
        # Format the author's name according to APA style
        formatted_author = (
            entry.get('last_name', '') + ', ' + entry.get('first_name', '')[:1] + '.'
        )
        # Append the formatted author to the citation
        apa_doi_citation += formatted_author
        # Add comma if there are more authors
        if i < len(creator_list) - 1:
            apa_doi_citation += ', '

    return apa_doi_citation


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
        'creators': get_authors(pkg_dict['creators']),
        'subjects': pkg_dict['tags'],
        'description': pkg_dict['notes'],
        'resourceType': "Data set",
    }

    return metadata
