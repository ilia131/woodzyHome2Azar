from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from PIL import Image, UnidentifiedImageError


def validate_image(file):
    FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])(file)
    if file.size > 5 * 1024 * 1024:
        raise ValidationError('Image must be at most 5 MiB.')
    try:
        with Image.open(file) as image:
            formats = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.webp': 'WEBP'}
            if image.format != formats[Path(file.name).suffix.lower()]:
                raise ValidationError('The file extension must match the image format.')
            if image.width * image.height > 20_000_000:
                raise ValidationError('Use JPEG, PNG or WebP up to 20 megapixels.')
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise ValidationError('Invalid image.') from error
    finally:
        file.seek(0)


def image_key(directory, filename):
    return f'{directory}/{uuid4().hex}{Path(filename).suffix.lower()}'


def product_image_path(instance, filename):
    return image_key('products', filename)


def gallery_image_path(instance, filename):
    return image_key('gallery', filename)


def category_image_path(instance, filename):
    return image_key('categories', filename)


def seo_image_path(instance, filename):
    return image_key('seo', filename)
