#!/usr/bin/env python3
# encoding: utf-8
#
# This file is part of ckanext-doi
# Created by the Natural History Museum in London, UK


def _split_full_name(full_name):
    """
    Split a full name into its family and given name parts.

    Names are expected in the format "FamilyName, GivenName"; if there's no comma we
    assume the name was formatted incorrectly and fall back to splitting on spaces,
    treating the last word as the family name. If that doesn't work either then there
    isn't much we can do.

    :param full_name: the name to split
    :return: a (family_name, given_name) tuple
    """
    family_name, comma, given_name = full_name.partition(',')
    if comma:
        return family_name.strip(), given_name.strip()

    name_parts = full_name.split(' ')
    return name_parts[-1].strip(), ' '.join(name_parts[0:-1]).strip()


def _name_identifier(identifier):
    """
    Convert an identifier dict into its xml_dict "nameIdentifiers" representation.

    :param identifier: a dict with "identifier", "scheme", and (optionally) "scheme_uri"
    :return: a dict, or None if the identifier is missing required keys
    """
    if 'identifier' not in identifier or 'scheme' not in identifier:
        return None
    id_dict = {
        'nameIdentifier': identifier['identifier'],
        'nameIdentifierScheme': identifier['scheme'],
    }
    if 'scheme_uri' in identifier:
        id_dict['schemeURI'] = identifier['scheme_uri']
    return id_dict


def create_contributor(
    full_name=None,
    family_name=None,
    given_name=None,
    is_org=False,
    contributor_type=None,
    affiliations=None,
    identifiers=None,
):
    """
    Create a dictionary representation of a contributing entity (either a person or an
    organisation) for use in an xml_dict.

    :param full_name: the full name of the creator, in the format "FamilyName, GivenName";
    can be omitted if family_name and given_name are provided
    :param family_name: family name of the creator; will be ignored if given_name is None
    :param given_name: given name(s) or initials of the creator; will be ignored if
    family_name is None
    :param is_org: sets name type to Organizational if true
    :param contributor_type: the contributor type to set
    :param affiliations: affiliations of the contributor, either a string or list of strings
    :param identifiers: a list of dicts with "identifier", "scheme", and (optionally) "scheme_uri"
    :return: a dict
    """
    if is_org and full_name is None:
        raise ValueError('Creator name must be supplied as full_name="Org Name"')
    if full_name is None and (family_name is None or given_name is None):
        raise ValueError(
            'Creator name must be supplied, either as full_name="FamilyName, '
            'GivenName" or separately as family_name and given_name'
        )

    if full_name is None:
        full_name = f'{family_name}, {given_name}'
    elif not is_org and (family_name is None or given_name is None):
        # we have a full name but not both parts, so extract them from the full name
        family_name, given_name = _split_full_name(full_name)

    contributor = {
        'name': full_name,
        'nameType': 'Organizational' if is_org else 'Personal',
    }

    if not is_org:
        contributor['familyName'] = family_name
        contributor['givenName'] = given_name

    if contributor_type is not None:
        contributor['contributorType'] = contributor_type

    if affiliations is not None:
        if isinstance(affiliations, str):
            affiliations = [affiliations]
        contributor['affiliations'] = [
            {'affiliation': affiliation} for affiliation in affiliations
        ]

    if identifiers:
        contributor['nameIdentifiers'] = [
            id_dict
            for id_dict in map(_name_identifier, identifiers)
            if id_dict is not None
        ]

    return contributor
