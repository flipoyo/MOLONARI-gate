from molosite import marker


def test_roundtrip_and_hash_covers_content_above():
    page = marker.write("<p>hi</p>\n\n", "MOLONARI1D@abc")
    body, m = marker.split(page)
    assert body == "<p>hi</p>" and m.src == "MOLONARI1D@abc" and m.sha256 == marker.digest("<p>hi</p>")
    assert marker.intact(page)


def test_hand_edit_breaks_the_marker():
    assert not marker.intact(marker.write("<p>hi</p>", "s").replace("hi", "ho"))


def test_no_marker_or_garbled_marker():
    assert marker.split("<p>x</p>") == ("<p>x</p>", None)
    assert marker.split("a\n<!-- molosite {not json} -->")[1] is None
    assert not marker.intact("<p>x</p>")
