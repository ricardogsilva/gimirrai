from pathlib import Path

from .vendorized.isobmff import MediaFile


def read_file(path: Path, debug: bool):
    # need to get:
    # - security information metadata, which is stored as XML
    # - klv metadata
    # - image contents
    isobmff_media_file = MediaFile(path, debug=debug)
    infe_box = isobmff_media_file.find_subbox("/meta/iinf/infe")
    security_information_media_type = infe_box.content_type.replace("\x00", "")
    security_information_item_id = infe_box.item_id
