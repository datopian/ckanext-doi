#!/usr/bin/env python3
# encoding: utf-8
#
# This file is part of ckanext-doi
# Created by the Natural History Museum in London, UK

from datetime import datetime
from logging import getLogger

from ckan.plugins import SingletonPlugin, implements, interfaces, toolkit

from ckanext.doi import cli
from ckanext.doi.lib.api import DataciteClient
from ckanext.doi.lib.helpers import (
    get_site_title,
    get_site_url,
    package_get_year,
    doi_test_mode,
    get_doi_metadata,
)
from ckanext.doi.model.crud import DOIQuery

log = getLogger(__name__)


class DOIPlugin(SingletonPlugin, toolkit.DefaultDatasetForm):
    """
    CKAN DOI Extension.
    """

    implements(interfaces.IConfigurer)
    implements(interfaces.IPackageController, inherit=True)
    implements(interfaces.ITemplateHelpers, inherit=True)
    implements(interfaces.IClick)

    ## IClick
    def get_commands(self):
        return cli.get_commands()

    ## IConfigurer
    def update_config(self, config):
        """
        Adds templates.
        """
        toolkit.add_template_directory(config, 'theme/templates')

    ## IPackageController
    def after_dataset_create(self, context, pkg_dict):
        """
        A new dataset has been created, so we need to create a new DOI.

        NB: This is called after creation of a dataset, before resources have been
        added, so state = draft.
        """
      
        DOIQuery.read_package(
            pkg_dict['id'],
            version=pkg_dict.get('version'),
            is_version=pkg_dict.get('is_version_of'),
            create_if_none=True,
        )

    ## IPackageController
    def after_dataset_update(self, context, pkg_dict):
        """
        Dataset has been created/updated.

        Check status of the dataset to determine if we should publish DOI to datacite
        network.
        """
        # Is this active and public? If so we need to make sure we have an active DOI
        is_active = pkg_dict.get('state', 'active') == 'active' and not pkg_dict.get(
            'private', False
        )
        if True:

            package_id = pkg_dict['id']

            # remove user-defined update schemas first (if needed)
            context.pop('schema', None)
            client = DataciteClient()
            client.update_doi(package_id)
        return pkg_dict

    # IPackageController
    def after_dataset_show(self, context, pkg_dict):
        """
        Add the DOI details to the pkg_dict so it can be displayed.
        """
        doi = DOIQuery.read_package(pkg_dict['id'])
        if doi:
            pkg_dict['doi'] = doi.identifier
            pkg_dict['doi_status'] = True if doi.published else False
            pkg_dict['domain'] = get_site_url().replace('http://', '')
            pkg_dict['release_date'] = (
                datetime.strftime(doi.published, '%Y-%m-%d') if doi.published else None
            )
            pkg_dict['publisher'] = toolkit.config.get('ckanext.doi.publisher')

    def after_create(self, *args, **kwargs):
        """
        CKAN 2.9 compat version of after_dataset_create.
        """
        return self.after_dataset_create(*args, **kwargs)

    def after_update(self, *args, **kwargs):
        """
        CKAN 2.9 compat version of after_dataset_update.
        """
        return self.after_dataset_update(*args, **kwargs)

    def after_show(self, *args, **kwargs):
        """
        CKAN 2.9 compat version of after_dataset_show.
        """
        return self.after_dataset_show(*args, **kwargs)

    # ITemplateHelpers
    def get_helpers(self):
        return {
            'package_get_year': package_get_year,
            'now': datetime.now,
            'get_site_title': get_site_title,
            'doi_test_mode': doi_test_mode,
            'get_doi_metadata': get_doi_metadata,
        }
