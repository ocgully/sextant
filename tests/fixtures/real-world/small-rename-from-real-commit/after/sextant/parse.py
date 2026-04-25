def detect_language(path):
    suffix = path.rsplit('.', 1)[-1] if '.' in path else ''
    return EXT_TO_LANG.get('.' + suffix.lower())

def parse_src(source, language):
    return _parse_impl(source, language)
