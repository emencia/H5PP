

def join_url(segment_list: list, delimiter: str = '/') -> str:
    """
    Segments may lead and trail with one or more delimiters
    The result has exactly one delimiter (including leading and trailing delimiters) at the location the segments
    are merged. Leading and/or trailing delimiters are removed when needed to accomplish this.

    :param segment_list: A list of 1 or more segments to join
    :param delimiter: the delimiter, defaults to '/'
    :return: The joined URL
    """
    while segment_list[0].endswith('//'):
        segment_list[0] = segment_list[0][:-1]

    if len(segment_list) == 1:
        return segment_list[0]

    if not segment_list[0].endswith('/'):
        segment_list[0] += '/'

    while segment_list[1].startswith('/'):
        segment_list[1] = segment_list[1][1:]

    segment_list[0] += segment_list[1]
    del segment_list[1]

    return join_url(segment_list, delimiter)
