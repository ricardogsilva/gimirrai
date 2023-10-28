"""Decoder for KLV metadata of the sample files."""

import dataclasses
import datetime as dt
import io
import logging
import struct
from typing import Optional

import pillow_heif

logger = logging.getLogger(__name__)


def decode_string(value: bytes) -> str:
    return value.decode("utf-8")


def decode_latitude_coordinate(lat_value: int) -> float:
    """Decode the parsed KLV latitude coordinate.

    Calculations implement the description in MISB ST0601 section 8.82
    """
    latitude_degrees = (180 / 4_294_967_294) * lat_value
    return latitude_degrees


def decode_longitude_coordinate(lon_value: int) -> float:
    """Decode the parsed KLV longitude coordinate.

    Calculations implement the description in MISB ST0601 section 8.83
    """
    longitude_degrees = (360 / 4_294_967_294) * lon_value
    return longitude_degrees


def decode_timestamp(microsecond_value: int) -> Optional[dt.datetime]:
    """Decode the parsed KLV precision time stamp.

    Calculations implement the description in MISB ST0601 section 8.2.

    Precision time stamp is given as the number of microseconds elapsed since
    midnight, January 1st, 1970 not including leap seconds.
    """
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    try:
        return epoch + dt.timedelta(microseconds=microsecond_value)
    except OverflowError:
        logger.exception(f"Could not decode timestamp {microsecond_value=}")
        return None


# tags, description, size, type gotten from the MISB ST0601 document
TAG_FORMATS = {
    2: ("begin_position", "Q", decode_timestamp),  # precision time stamp, size: 8, type: uint64
    3: ("title", "s", decode_string),  # mission id, size: variable, type: char[]
    82: ("pt1_north_bound_latitude", "i", decode_latitude_coordinate),  # corner lat pt1, size: 4, type: int32
    83: ("pt1_west_bound_longitude", "i", decode_longitude_coordinate),  # corner lon pt1, size: 4, type: int32
    84: ("pt2_north_bound_latitude", "i", decode_latitude_coordinate),  # corner lat pt2, size: 4, type: int32
    85: ("pt2_east_bound_longitude", "i", decode_longitude_coordinate),  # corner lon pt2, size: 4, type: int32
    86: ("pt3_south_bound_latitude", "i", decode_latitude_coordinate),  # corner lat pt3, size: 4, type: int32
    87: ("pt3_east_bound_longitude", "i", decode_longitude_coordinate),  # corner lon pt3, size: 4, type: int32
    88: ("pt4_south_bound_latitude", "i", decode_latitude_coordinate),  # corner lat pt4, size: 4, type: int32
    89: ("pt4_west_bound_longitude", "i", decode_longitude_coordinate),  # corner lon pt4, size: 4, type: int32
    65: ("st0601_version", "B", None),  # UAS Datalink LS Version Number, size: 1, type: uint8
    1: ("checksum", "H", None),  #  Checksum, size: 2, type: uint16
}


@dataclasses.dataclass
class GimiKlvMetadata:
    title: str
    begin_position: str | None
    upper_left_lon: float
    upper_left_lat: float
    lower_right_lon: float
    lower_right_lat: float


def get_metadata(heif_ds: pillow_heif.HeifImage):
    """Decode KLV metadata from GIMI HEIF file image."""
    klv_packet_items = heif_ds.info["metadata"][0]["data"]
    buff = io.BytesIO(klv_packet_items)
    meta = decode_metadata(buff)
    return GimiKlvMetadata(
        title=meta.get("title", ""),
        begin_position=meta.get("begin_position"),
        upper_left_lon=meta.get("pt1_west_bound_longitude"),
        upper_left_lat=meta.get("pt1_north_bound_latitude"),
        lower_right_lon=meta.get("pt3_east_bound_longitude"),
        lower_right_lat=meta.get("pt3_south_bound_latitude")
    )


def decode_metadata(buff: io.BytesIO) -> dict:
    """Decode KLV metadata coming from a GIMI file.

    This function makes some assumptions about the nature of the KLV bytestream:

    - contents to have big-endian order

    - KLV size to be in BER short form (i.e. expect a single byte, which
    means size value < 128)

    - tag value to be in BER-OID short form (i.e. expect a single byte,
    which means tag value < 128)
    """
    result = {}
    num_iterations = 0
    max_iterations = 1_000
    while ("checksum" not in result) and (num_iterations < max_iterations):
        tag = struct.unpack(">B", buff.read(1))[0]
        if tag < 128:
            try:
                name, format_, decoder = TAG_FORMATS[tag]
            except KeyError:
                logger.debug(f"Found unknown tag: {tag}, skipping...")
            else:
                logger.info(f"found {name!r}")
                size = struct.unpack(">B", buff.read(1))[0]
                if size < 128:
                    if format_ == "s":
                        # format becomes char[] of the size we just read
                        format_ = f"{size}s"
                    value = struct.unpack(format_, buff.read(size))[0]
                    if decoder is not None:
                        logger.debug(f"decoding {name} - before: {value}")
                        result[name] = decoder(value)
                    else:
                        result[name] = value
                else:
                    logger.warning(
                        "Found a size bigger than 127, reading is not "
                        "implemented yet, skipping..."
                    )
        else:
            logger.warning(
                "Found a tag number bigger than 127, reading is not "
                "implemented yet, skipping..."
            )
        num_iterations += 1
        logger.debug(f"{result=}")
    if "checksum" not in result:
        logger.warning(
            "Could not find value for checksum - Might have not read all values")
    return result
