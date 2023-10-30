"""Reader utilities for working with sample GIMI data files."""

import dataclasses
from pathlib import Path

import pillow_heif
import rasterio

from .decoders import klv


@dataclasses.dataclass
class GimiBandData:
    index: int
    dtype: str
    no_data_value: int | None
    units: str | None


@dataclasses.dataclass
class GimiImageMetadata:
    affine: rasterio.Affine
    bands: dict[int, GimiBandData]
    begin_position: str | None
    crs: int
    height: int
    lower_right_lon: float
    lower_right_lat: float
    title: str
    upper_left_lon: float
    upper_left_lat: float
    width: int
    x_resolution: float
    y_resolution: float


@dataclasses.dataclass
class GimiMetadata:
    images: list[GimiImageMetadata]


def get_gimi_metadata(gimi_file: Path) -> GimiMetadata:
    bands = {}
    with rasterio.open(gimi_file) as rasterio_dataset:
        band_data = zip(
            rasterio_dataset.indexes,
            rasterio_dataset.dtypes,
            rasterio_dataset.nodatavals
        )
        for index, dtype, no_data in band_data:
            bands[index] = GimiBandData(
                index=index,
                dtype=dtype,
                no_data_value=no_data,
                units=None
            )
    if not pillow_heif.is_supported(gimi_file):
        raise RuntimeError(f"file {gimi_file} is not supported")
    heif_file = pillow_heif.open_heif(gimi_file)
    gimi_images = []
    for heif_image in heif_file:
        klv_meta = klv.get_metadata(heif_image)
        width, height = heif_image.size
        x_resolution = (klv_meta["pt3_east_bound_longitude"] - klv_meta["pt1_west_bound_longitude"]) / width
        y_resolution = (klv_meta["pt3_south_bound_latitude"] - klv_meta["pt1_north_bound_latitude"]) / height
        gimi_images.append(
            GimiImageMetadata(
                affine=rasterio.Affine.from_gdal(
                    klv_meta["pt1_west_bound_longitude"],
                    x_resolution,
                    0.,
                    klv_meta["pt1_north_bound_latitude"],
                    0.,
                    y_resolution
                ),
                bands=bands,
                begin_position=klv_meta.get("begin_position"),
                crs=4326,
                height=height,
                lower_right_lon=klv_meta.get("pt3_east_bound_longitude"),
                lower_right_lat=klv_meta.get("pt3_south_bound_latitude"),
                title=klv_meta.get("title", ""),
                upper_left_lon=klv_meta.get("pt1_west_bound_longitude"),
                upper_left_lat=klv_meta.get("pt1_north_bound_latitude"),
                width=width,
                x_resolution=x_resolution,
                y_resolution=y_resolution,
            )
        )
    return GimiMetadata(images=gimi_images)
