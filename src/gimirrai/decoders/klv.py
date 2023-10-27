"""Decoder for KLV metadata of the sample files."""

import io
import struct

import pillow_heif


def get_klv_metadata(heif_ds: pillow_heif.HeifImage):
    raw_klv_meta = heif_ds.info["metadata"][0]["data"]
    buff = io.BytesIO(raw_klv_meta)


def decode_metadata_item(buff: io.BytesIO):
    # read the tag and size first
    # we expect contents to be in big-endian
    # moreover, for now we can only read:
    # - size in BER short form (i.e. expect a single byte, which means size value < 128)
    # - tag in BER-OID short form (i.e. expect a single byte, which means tag value < 128)
    tag, size = struct.unpack(">BB", buff.read(2))
    tag_formats = {
        2: "Q",  # precision time stamp, size: 8, type: uint64
        3: "s",  # mission id, size: variable, type: char[]
        82: "i",  # corner lat pt1, size: 4, type: int32
        83: "i",  # corner lon pt1, size: 4, type: int32
        84: "i",  # corner lat pt2, size: 4, type: int32
        85: "i",  # corner lon pt2, size: 4, type: int32
        86: "i",  # corner lat pt3, size: 4, type: int32
        87: "i",  # corner lon pt3, size: 4, type: int32
        88: "i",  # corner lat pt4, size: 4, type: int32
        89: "i",  # corner lon pt4, size: 4, type: int32
    }
    format_ = tag_formats.get(tag)
    if format_ == "s":
        format_ = f"{size}s"
    value = struct.unpack(f">{format_}", buff.read(size))