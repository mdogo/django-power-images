# -*- coding: utf-8 -*-
"""
"""
# python 3 imports
from __future__ import absolute_import, unicode_literals

# python imports
import logging

logger = logging.getLogger(__name__)


def make_remove_function(image_field):
    def remove_unused_files(instance, sender, **kwargs):
        try:
            old_instance = instance._default_manager.get(pk=instance.pk)
        except instance.DoesNotExist:
            old_instance = None
        if old_instance:
            db_image = getattr(old_instance, image_field)
            current_image = getattr(instance, image_field)
            if db_image != current_image:
                db_image.delete(save=False)
    return remove_unused_files
