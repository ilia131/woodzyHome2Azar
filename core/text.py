import unicodedata

TRANSLATIONS = str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', '‌': ' ', 'ـ': ''})


def normalize(value):
    value = unicodedata.normalize('NFKC', value).translate(TRANSLATIONS).casefold()
    return ' '.join(''.join(char for char in value if unicodedata.category(char) != 'Mn').split())
