#!/usr/bin/env python3
# encoding: utf-8
#
# This file is part of ckanext-doi
# Created by the Natural History Museum in London, UK

import logging

from ckan.lib.helpers import lang as ckan_lang
from ckan.model import Package
from ckan.plugins import PluginImplementations, toolkit

from ckanext.doi.interfaces import IDoi
from ckanext.doi.lib import xml_utils
from ckanext.doi.lib.errors import DOIMetadataException
from ckanext.doi.lib.helpers import date_or_none, get_site_url, package_get_year

log = logging.getLogger(__name__)

ROR_URL_PREFIX = 'http://ror.org/'
ROR_SCHEME_URI = 'https://ror.org/'

# fields that must be present for a DOI to be minted; extraction failures here are fatal
REQUIRED_FIELD_DEFAULTS = {
    'creators': [],
    'titles': [],
    'publisher': None,
    'publicationYear': None,
    'resourceType': None,
    'contributors': [],
}

# fields that are nice to have; extraction failures here are logged and ignored
OPTIONAL_FIELD_DEFAULTS = {
    'subjects': [],
    'dates': [],
    'language': '',
    'alternateIdentifiers': [],
    'relatedIdentifiers': [],
    'sizes': [],
    'formats': [],
    'version': '',
    'rightsList': [],
    'descriptions': [],
    'geolocations': [],
    'fundingReferences': [],
}

# optional keys copied from the metadata dict into the xml dict, in order
XML_OPTIONAL_KEYS = [
    'subjects',
    'contributors',
    'dates',
    'language',
    'alternateIdentifiers',
    'relatedIdentifiers',
    'sizes',
    'formats',
    'version',
    'rightsList',
    'descriptions',
    'geolocations',
    'fundingReferences',
]


def _ror_affiliation_identifier(ror):
    """
    Build the "nameIdentifiers" entry for a ROR ID, as used in creator affiliations.

    :param ror: the ROR ID
    :return: a dict
    """
    return {
        'nameIdentifier': f'{ROR_URL_PREFIX}{ror}',
        'nameIdentifierScheme': 'ROR',
        'schemeURI': ROR_SCHEME_URI,
    }


def _extract_creators(pkg_dict):
    """
    Extract the creators from the package, handling both people and organisations.

    Entries with an unrecognised type are skipped.

    :param pkg_dict: dict of package details
    :return: a list of creator dicts
    """
    creators = []

    for creator in pkg_dict.get('creators') or []:
        creator_type = creator.get('type')

        if creator_type == 'person':
            creators.append(
                {
                    'name': f"{creator.get('first_name')} {creator.get('last_name')}",
                    'given_name': creator.get('first_name'),
                    'family_name': creator.get('last_name'),
                    'affiliations': [{'affiliation': creator.get('organisation')}],
                    'nameType': 'Personal',
                }
            )
        elif creator_type == 'organisation':
            affiliation = {'affiliation': creator.get('name')}
            if creator.get('ror'):
                affiliation['nameIdentifiers'] = [
                    _ror_affiliation_identifier(creator['ror'])
                ]
            creators.append(
                {
                    'name': creator.get('name') or creator.get('acronym'),
                    'affiliations': [affiliation],
                    'nameType': 'Organizational',
                }
            )

    return creators


def _extract_contributors(pkg_dict):
    """
    Extract the contributors from the package.

    This combines the package's contributors with its contact points, the latter being
    marked up with the appropriate contributor type.

    :param pkg_dict: dict of package details
    :return: a list of contributor dicts, ready to be passed to
             xml_utils.create_contributor
    """
    contributors = [
        {
            'given_name': contributor.get('first_name'),
            'family_name': contributor.get('last_name'),
            'affiliations': contributor.get('organisation'),
            'contributor_type': contributor.get('type', 'Other'),
        }
        for contributor in pkg_dict.get('contributors', []) or []
    ]

    for contact_point in pkg_dict.get('contact_points', []) or []:
        contact_type = contact_point.get('type')

        if contact_type == 'person':
            contributors.append(
                {
                    'given_name': contact_point.get('first_name'),
                    'family_name': contact_point.get('last_name'),
                    'affiliations': contact_point.get('organisation'),
                    'contributor_type': 'ContactPerson',
                }
            )
        elif contact_type == 'organisation':
            identifiers = []
            if contact_point.get('ror'):
                identifiers.append(
                    {
                        'identifier': f"{ROR_URL_PREFIX}{contact_point['ror']}",
                        'scheme': 'ROR',
                        'scheme_uri': ROR_SCHEME_URI,
                    }
                )
            if contact_point.get('homepage_url'):
                identifiers.append(
                    {
                        'identifier': contact_point.get('homepage_url'),
                        'scheme': 'URL',
                    }
                )

            contributors.append(
                {
                    'full_name': contact_point.get('name')
                    or contact_point.get('acronym'),
                    'is_org': True,
                    'contributor_type': 'Other',
                    'affiliations': [contact_point.get('name')],
                    'identifiers': identifiers if identifiers else None,
                }
            )

    return contributors


def _extract_subjects(pkg_dict):
    """
    Extract a sorted, deduplicated list of subjects from the package's tags.

    :param pkg_dict: dict of package details
    :return: a list of subject dicts
    """
    tags = pkg_dict.get('tag_string', '').split(',')
    tags += [
        tag['name'] if isinstance(tag, dict) else tag for tag in pkg_dict.get('tags', [])
    ]
    return [{'subject': tag} for tag in sorted({t for t in tags if t != ''})]


def _get_version_doi(package_id):
    """
    Look up the DOI of a related package.

    :param package_id: the id or name of the package
    :return: the DOI, or an empty string if no id was given, or None if the related
             package has no DOI
    """
    if not package_id:
        return ''
    data_dict = toolkit.get_action('package_show')(
        {'ignore_auth': True}, {'id': package_id}
    )
    if data_dict.get('doi'):
        return data_dict.get('doi')


def _extract_related_identifiers(pkg_dict):
    """
    Extract identifiers for the versions this package relates to.

    :param pkg_dict: dict of package details
    :return: a list of related identifier dicts
    """
    related_identifiers = []

    for field, relation_type in (
        ('has_version', 'HasVersion'),
        ('is_version_of', 'IsVersionOf'),
    ):
        if pkg_dict.get(field):
            related_identifiers.append(
                {
                    'relatedIdentifier': _get_version_doi(pkg_dict.get(field)),
                    'relatedIdentifierType': 'DOI',
                    'relationType': relation_type,
                }
            )

    return related_identifiers


def _extract_permalink(pkg_dict):
    """
    Build a permalink back to this site for the given package.

    :param pkg_dict: dict of package details
    :return: a list containing a single alternate identifier dict
    """
    base_url = toolkit.config.get('ckanext.frontend_url') or get_site_url()
    permalink = f'{base_url}/dataset/{pkg_dict["name"]}'
    return [{'alternateIdentifierType': 'URL', 'alternateIdentifier': permalink}]


def _extract_total_size(pkg_dict):
    """
    Sum the sizes of the package's resources, converted from bytes to kilobytes.

    :param pkg_dict: dict of package details
    :return: a list containing a single size string
    """
    resource_sizes = [r.get('size') or 0 for r in pkg_dict.get('resources', []) or []]
    return [f'{int(sum(resource_sizes) / 1024)} kb']


def _extract_formats(pkg_dict):
    """
    List the unique formats used by the package's resources.

    :param pkg_dict: dict of package details
    :return: a list of format strings
    """
    return list(
        set(filter(None, [r.get('format') for r in pkg_dict.get('resources', []) or []]))
    )


def _extract_rights_list(pkg_dict):
    """
    Look up the package's license in CKAN's license register.

    :param pkg_dict: dict of package details
    :return: a list of rights dicts, empty if the package has no usable license
    """
    license_id = pkg_dict.get('license_id', 'notspecified')
    if license_id == 'notspecified' or license_id is None:
        return []

    license = Package.get_license_register().get(license_id)
    if license is None:
        return []

    return [{'url': license.url, 'identifier': license.id}]


def _extract_dates(pkg_dict, errors):
    """
    Extract the created, updated, and (if present) release dates from the package.

    Each date is extracted independently so that one bad date doesn't lose the others.

    :param pkg_dict: dict of package details
    :param errors: a dict to collect per-date extraction errors into
    :return: a list of date dicts
    """
    date_sources = [
        ('created', 'Created', 'metadata_created'),
        ('updated', 'Updated', 'metadata_modified'),
    ]
    # only include the release date if the package actually has one
    if 'releaseDate' in pkg_dict:
        date_sources.append(('releaseDate', 'Issued', 'releaseDate'))

    dates = []
    for error_key, date_type, pkg_key in date_sources:
        try:
            dates.append(
                {'dateType': date_type, 'date': date_or_none(pkg_dict.get(pkg_key))}
            )
        except Exception as e:
            errors[error_key] = e

    return dates


def build_metadata_dict(pkg_dict):
    """
    Build/extract a basic dict of metadata that can then be passed to build_xml_dict.

    :param pkg_dict: dict of package details
    """
    # collect errors instead of throwing them immediately; some data may not be correctly
    # handled by this base method but will be handled correctly by plugins that implement
    # IDoi
    errors = {}

    def _extract(target, key, get_func):
        """
        Run an extractor, storing its result under key or recording the error it raised.
        """
        try:
            target[key] = get_func()
        except Exception as e:
            errors[key] = e

    # required fields first (identifier will be added later)
    required = dict(REQUIRED_FIELD_DEFAULTS)
    _extract(required, 'creators', lambda: _extract_creators(pkg_dict))
    _extract(required, 'contributors', lambda: _extract_contributors(pkg_dict))
    _extract(required, 'titles', lambda: [{'title': pkg_dict.get('title')}])
    _extract(
        required, 'publisher', lambda: toolkit.config.get('ckanext.doi.publisher')
    )
    _extract(required, 'publicationYear', lambda: package_get_year(pkg_dict))
    _extract(required, 'resourceType', lambda: pkg_dict.get('type'))

    # now the optional fields
    optional = dict(OPTIONAL_FIELD_DEFAULTS)

    # SUBJECTS: use the tag list
    _extract(optional, 'subjects', lambda: _extract_subjects(pkg_dict))

    # RELATED IDENTIFIERS: versions of this package
    optional['relatedIdentifiers'] = _extract_related_identifiers(pkg_dict)

    # DATES: created, updated, and doi publish date
    date_errors = {}
    optional['dates'] = _extract_dates(pkg_dict, date_errors)

    # LANGUAGE: use language set in CKAN
    optional['language'] = pkg_dict.get('language', 'en')

    # ALTERNATE IDENTIFIERS: add permalink back to this site
    _extract(optional, 'alternateIdentifiers', lambda: _extract_permalink(pkg_dict))

    # SIZES: sum up given sizes from resources in the package
    _extract(optional, 'sizes', lambda: _extract_total_size(pkg_dict))

    # FORMATS: list unique formats from package resources
    _extract(optional, 'formats', lambda: _extract_formats(pkg_dict))

    # VERSION: doesn't matter if there's no version, it'll get filtered out later
    optional['version'] = str(pkg_dict.get('version'))

    # RIGHTS: use the package license and get details from CKAN's license register
    _extract(optional, 'rightsList', lambda: _extract_rights_list(pkg_dict))

    # DESCRIPTIONS: use package notes
    optional['descriptions'] = [
        {'descriptionType': 'Other', 'description': pkg_dict.get('notes', '')}
    ]

    # GEOLOCATIONS: nothing relevant in default schema

    # FUNDING: nothing relevant in default schema

    metadata_dict = {}
    metadata_dict.update(required)
    metadata_dict.update(optional)

    for plugin in PluginImplementations(IDoi):
        # implementations should remove relevant errors from the errors dict if they
        # successfully handle an item
        metadata_dict, errors = plugin.build_metadata_dict(
            pkg_dict, metadata_dict, errors
        )

    for k in required:
        if metadata_dict.get(k) is None and errors.get(k) is None:
            errors[k] = DOIMetadataException('Required field cannot be None')

    required_errors = {k: e for k, e in errors.items() if k in required}
    if len(required_errors) > 0:
        error_msg = (
            f'Could not extract metadata for the following required keys: '
            f'{", ".join(required_errors)}'
        )
        log.exception(error_msg)
        for k, e in required_errors.items():
            log.exception(f'{k}: {e}')
        raise DOIMetadataException(error_msg)

    optional_errors = {k: e for k, e in errors.items() if k in optional}
    if len(required_errors) > 0:
        error_msg = (
            f'Could not extract metadata for the following optional keys: '
            f'{", ".join(optional_errors)}'
        )
        log.debug(error_msg)
        for k, e in optional_errors.items():
            log.debug(f'{k}: {e}')
    return metadata_dict


def _has_value(value):
    """
    Determine whether a value is worth including in the xml dict.

    Anything that is None, or that is sized and empty, is excluded.

    :param value: the value to check
    :return: True if the value should be included
    """
    try:
        return value is not None and (not hasattr(value, '__len__') or len(value) > 0)
    except Exception:
        return False


def _stringify_dates(dates):
    """
    Convert the "date" field of each date entry to a string.

    :param dates: a list of date dicts
    :return: a new list of date dicts with stringified dates
    """
    return [{**date_entry, 'date': str(date_entry['date'])} for date_entry in dates]


def build_xml_dict(metadata_dict):
    """
    Builds a dictionary that can be passed directly to datacite.schema42.tostring() to
    generate xml. Previously named metadata_to_xml but renamed as it's not actually
    producing any xml, it's just formatting the metadata so a separate function can then
    generate the xml.

    :param metadata_dict: a dict of metadata generated from build_metadata_dict
    :return: dict that can be passed directly to datacite.schema42.tostring()
    """
    # required fields first (DOI will be added later)
    xml_dict = {
        'creators': metadata_dict.get('creators', []),
        'titles': metadata_dict.get('titles', []),
        'publisher': metadata_dict.get('publisher'),
        'publicationYear': str(metadata_dict.get('publicationYear')),
        'types': {
            'resourceType': metadata_dict.get('resourceType'),
            'resourceTypeGeneral': 'Dataset',
        },
        'schemaVersion': 'http://datacite.org/schema/kernel-4',
    }

    for k in XML_OPTIONAL_KEYS:
        v = metadata_dict.get(k)
        if not _has_value(v):
            continue

        if k == 'contributors':
            xml_dict[k] = [
                xml_utils.create_contributor(**contributor) for contributor in v
            ]
        elif k == 'dates':
            xml_dict[k] = _stringify_dates(v)
        else:
            xml_dict[k] = v

    for plugin in PluginImplementations(IDoi):
        xml_dict = plugin.build_xml_dict(metadata_dict, xml_dict)
    return xml_dict
