# -*- coding: utf-8 -*-
"""
"""
# python 3 imports
from __future__ import absolute_import, unicode_literals

# python imports
import hashlib
import os

# django imports
from django.core.files.base import ContentFile
from django.db.models.fields.files import ImageFieldFile
from django.utils import six
from django.utils.encoding import force_str


def image_field_file_factory(*args, **kwargs):
    field_file = kwargs.get('field_file', ImageFieldFile)
    return type(force_str('CustomImageFieldFile'),
                args + (field_file, ), {})


def md5_checksum(content):
    """Returns the md5 checksum for the content of a given image.

    Args:
        content: a file to be used to calculate the md5 checksum.

    Returns:
        A string with the md5 checksum result of the content of the image.
    """
    md5 = hashlib.md5()
    for chunk in content.chunks():
        md5.update(chunk)
    return md5.hexdigest()


def get_ext(path):
    """Returns the file extension for a given file path.

    This function returns a file extension that PIL will understand as `jpg`
    is not a format valid for PIL.

    Args:
        path: a string with the file path.

    Returns:
        A string with an extensions understable for PIL.
    """
    path_name, ext = os.path.splitext(path)
    ext = ext.strip('.').lower()
    if ext == 'jpg':
        return 'jpeg'
    else:
        return ext


def save_pilimage(image, path, storage):
    """Save a pil image using django storage system.

    As a PIL image does not inherit from django file class it can not be saved
    using django storage system. So we have to load the image content to a
    django file and the save it using django storage.

    Args:
        image: a PIL image to be saved in the host.
        path: a string that indicates the file path where the image should be
            saved.
        storage: a django storage instance.

    Returns:
        A string with the path of the stored file.
    """
    tmp_file = six.BytesIO()
    image.save(tmp_file, format=get_ext(path))
    image_file = ContentFile(tmp_file.getvalue())
    return storage.save(path, image_file)
