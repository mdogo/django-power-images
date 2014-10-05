# -*- coding: utf-8 -*-
"""
"""
# python 3 imports
from __future__ import absolute_import, unicode_literals

# python imports
import logging
import os
import sys

# django imports
from django.db import models
from django.db.models import signals
from django.db.models.fields.files import ImageFieldFile
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.templatetags.staticfiles import static
from django.core.exceptions import ImproperlyConfigured
from django.utils import six

# 3rd. libraries imports
from PIL import Image as PILImage
from pilkit.processors import Thumbnail

# app imports
from .helpers import image_field_file_factory, md5_checksum, save_pilimage

logger = logging.getLogger(__name__)


class ThumbnailsMixin(object):
    """Mixin that links an image with its thumbnails.

    This mixin can generate thumbnails base in the file instance of an
    ImageFielFile and also has methods to return the thumbnail path and url.

    To use this mixin you have to add it to a ImageFieldFile subclass and use
    that subclass as the attr_class of an ImageField. The ImageField should
    have two attributes that defines the behaviour of the thumbnails,
    `thumbnails` that enable the use of thumbnails and `thumbnail_sizes` with
    a list of integers that indicates the width in pixels of the thumbnails
    that will be created on save.
    """
    def save(self, *args, **kwargs):
        super(ThumbnailsMixin, self).save(*args, **kwargs)
        thumbnails = getattr(self.field, 'thumbnails', False)
        if thumbnails:
            self.generate_thumbnails()

    def delete(self, save=True):
        thumbnails = getattr(self.field, 'thumbnails', False)
        if thumbnails:
            self.remove_thumbnails()
        super(ThumbnailsMixin, self).delete(save=save)

    def _require_thumbnail(self):
        """Raise a ValueError if field has not thumbnails enabled.
        """
        thumbnails = getattr(self.field, 'thumbnails', False)
        if not thumbnails:
            raise ValueError(
                '{} has not thumbnails enabled.'.format(self.field.name))

    def get_thumbnail_url(self, size):
        """Returns the url for a given size thumbnail.
        """
        self._require_thumbnail()
        if self.url:
            self.generate_thumbnail(size)
            url_path = self.url.split('/')
            url_path.insert(-1, str(size))
            url = '/'.join(url_path)
            return url

    def get_thumbnail_path(self, size):
        """Returns the relative system path for a given size thumbnail.
        """
        self._require_thumbnail()
        path = [os.path.dirname(self.path)]
        path.append(str(size))
        path.append(os.path.basename(self.name))
        return os.path.join(*path)

    def generate_thumbnail(self, size):
        """Generate a thumbnail for the given size.
        """
        self._require_thumbnail()
        self._require_file()
        path = self.get_thumbnail_path(size)
        if not self.storage.exists(path):
            processor = Thumbnail(size)
            try:
                with PILImage.open(self.path) as image:
                    resized_image = processor.process(image)
                    save_pilimage(resized_image, path, self.storage)
            except IOError as e:
                logger.warning(e.value)

    def generate_thumbnails(self):
        """Generate all thumbnails for the sizes defined as default.
        """
        self._require_thumbnail()
        sizes = getattr(self.field, 'thumbnail_sizes', [])
        for size in sizes:
            self.generate_thumbnail(size)

    def remove_thumbnails(self):
        """Remove all thumbnails related with this image.

        We look for any thumbnail related with this image, those which are in a
        "digit" subfolder and with the same name as the original file.

        As we want to use django storage system, we can not remove empty
        directories.
        """
        root_path = os.path.dirname(self.path)
        thumbnail_dirs = self.storage.listdir(root_path)[0]
        sizes = (item for item in thumbnail_dirs if item.isdigit())
        for size in sizes:
            path = self.get_thumbnail_path(size=size)
            self.storage.delete(path)


class StaticChoiceMixin(object):
    """Mixin that allows a _selectable image_ as fallback for an image file.

    With this mixin a ImageField can declare a _choice field_, another field of
    the ImageField's model, that stores the path to a static image file. When
    the previous ImageField has no file instance, it will return the value of
    the _choice field_.

    As with the TuhmbnailsMixin, to use this mixin you have to add it to a
    ImageFieldFile subclass and use that subclass as the attr_class of an
    ImageField. The ImageField should have an attribute that defines the field
    to be used as a fallback.
    """
    def _get_choice_field(self):
        """Returns the field of the model instance declared as fallback.
        """
        try:
            return getattr(self.instance, self.field.choice_field)
        except AttributeError as e:
            raise six.reraise(
                ImproperlyConfigured,
                ImproperlyConfigured(
                    '{} has no {} field.'.format(self.instance,
                                                 self.field.choice_field),
                    e),
                sys.exc_info()[2])
    choice_field = property(_get_choice_field)

    def _get_url(self):
        if not self and self.choice_field:
            return static(self.choice_field)
        return super(StaticChoiceMixin, self)._get_url()
    url = property(_get_url)

    def _get_path(self):
        if not self and self.choice_field:
            return finders.find(self.choice_field)
        return super(StaticChoiceMixin, self)._get_path()
    path = property(_get_path)


class ThumbnailChoiceMixin(ThumbnailsMixin, StaticChoiceMixin):
    """A mixin that combines the behabiour of both ThumbnailsMixin and
    StaticChoiceMixin.

    As the choice field stores the path for a static file we must prevent the
    generation and cleared of thumbnails.
    """
    def generate_thumbnail(self, size):
        if self:
            super(ThumbnailChoiceMixin, self).generate_thumbnail(size)

    def remove_thumbnails(self):
        if self:
            super(ThumbnailChoiceMixin, self).remove_thumbnails()


class UniqueImageField(models.ImageField):
    """An ImageField that prevents duplicated files and can generate thumbnails

    This field works the same way as ImageField but accepts two additional
    arguments, thumbnails and thumbnail_size. The first one declares if the
    field should generate thumbnails when saving a new file, the second one
    declares the thumbnail sizes to be created.
    """
    attr_class = image_field_file_factory(ThumbnailsMixin)

    def __init__(self, thumbnails=False, thumbnail_sizes=(), **kwargs):
        super(UniqueImageField, self).__init__(**kwargs)
        self.thumbnails = thumbnails
        self.thumbnail_sizes = thumbnail_sizes

    def contribute_to_class(self, cls, name):
        super(UniqueImageField, self).contribute_to_class(cls, name)
        if not cls._meta.abstract:
            signals.pre_save.connect(self.remove_unused_files,
                                      sender=cls)

    def remove_unused_files(self, instance, *args, **kwargs):
        try:
            old_instance = instance._default_manager.get(pk=instance.pk)
        except instance.DoesNotExist:
            old_instance = None
        if old_instance:
            db_image = getattr(old_instance, self.name)
            current_image = getattr(instance, self.name)
            if db_image != current_image:
                db_image.delete(save=False)

    def deconstruct(self):
        name, path, args, kwargs = (
            super(UniqueImageField, self).deconstruct())
        if self.thumbnails:
            kwargs['thumbnails'] = self.thumbnails
            kwargs['thumbnail_sizes'] = self.thumbnail_sizes
        return name, path, args, kwargs


class SelectableUniqueImageField(UniqueImageField):
    """An ImageField that has a selectable fallback image.

    This fields extends the UniqueImageField but it has an additional argument,
    choice_field. This argument is a literal with the name of a field that
    store a relative static path for a image that is used when the ImageField
    has no image itself.
    """
    attr_class = image_field_file_factory(ThumbnailChoiceMixin)

    def __init__(self, choice_field, **kwargs):
        super(SelectableUniqueImageField, self).__init__(**kwargs)
        self.choice_field = choice_field

    def deconstruct(self):
        name, path, args, kwargs = (
            super(SelectableUniqueImageField, self).deconstruct())
        kwargs['choice_field'] = self.choice_field
        return name, path, args, kwargs
