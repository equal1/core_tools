from core_tools.data.sqdl.export import data_export

import pytest


@pytest.mark.parametrize(
    "data, result",
    [
        ("", ""),
        (r'*/\<>:"|?', "_________"),
        ("some text", "some text"),
        ("so*e o/her?t:xt", "so_e o_her_t_xt"),
    ],
)
def test_fix_filename_with_regex(data, result):
    assert data_export.fix_filename(data) == result


@pytest.mark.parametrize(
    "data, result",
    [
        ("", ""),
        (r'*/\<>:"|?', "_________"),
        ("some text", "some text"),
        ("so*e o/her?t:xt", "so_e o_her_t_xt"),
    ],
)
def test_fix_filename_original(data, result):
    import re
    invalid_chars = re.compile(r'[*/\\<>:"|?]')
    m = invalid_chars.search(data)
    while m:
        data = data[:m.start()] + "_" * (m.end() - m.start()) + data[m.end():]
        m = invalid_chars.search(data)

    assert data == result
