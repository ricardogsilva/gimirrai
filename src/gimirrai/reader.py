"""Reader utilities for working with sample GIMI data files."""

import dataclasses
import xml.etree.ElementTree as etree
from pathlib import Path
from xml.dom import minidom

import shapely.geometry
import pillow_heif
import rasterio
import rasterio.control
import rasterio.crs
import rasterio.vrt

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
    bbox: shapely.geometry.Polygon
    begin_position: str | None
    crs: int
    gcps: list[rasterio.control.GroundControlPoint]
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
    path: Path
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
                bbox=shapely.geometry.box(
                    minx=klv_meta.get("pt1_west_bound_longitude"),
                    miny=klv_meta.get("pt1_north_bound_latitude"),
                    maxx=klv_meta.get("pt3_east_bound_longitude"),
                    maxy=klv_meta.get("pt3_south_bound_latitude"),
                ),
                begin_position=klv_meta.get("begin_position"),
                crs=4326,
                gcps=[
                    rasterio.control.GroundControlPoint(
                        row=0,
                        col=0,
                        y=klv_meta.get("pt1_north_bound_latitude"),
                        x=klv_meta.get("pt1_west_bound_longitude"),
                    ),
                    rasterio.control.GroundControlPoint(
                        row=0,
                        col=width,
                        y=klv_meta.get("pt1_north_bound_latitude"),
                        x=klv_meta.get("pt3_east_bound_longitude"),
                    ),
                    rasterio.control.GroundControlPoint(
                        row=height,
                        col=width,
                        y=klv_meta.get("pt3_south_bound_latitude"),
                        x=klv_meta.get("pt3_east_bound_longitude"),
                    ),
                    rasterio.control.GroundControlPoint(
                        row=height,
                        col=0,
                        y=klv_meta.get("pt3_south_bound_latitude"),
                        x=klv_meta.get("pt1_west_bound_longitude"),
                    ),
                ],
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
    return GimiMetadata(
        images=gimi_images,
        path=gimi_file,
    )


def get_vrt(metadata: GimiMetadata) -> str:
    """Generate a VRT string to open the GIMI file with rasterio."""
    # inspired by: https://github.com/cogeotiff/rio-tiler/issues/564#issuecomment-1375675886
    # generate a VRT string, add GCPs, override the geotransform and then use that
    crs_wkt = rasterio.crs.CRS.from_epsg(metadata.images[0].crs).wkt
    with rasterio.open(metadata.path) as ds:
        vrt_xml_tree = etree.fromstring(
            rasterio.vrt._boundless_vrt_doc(ds))
        vrt_xml_tree.find("SRS").text = crs_wkt
        vrt_xml_tree.find("GeoTransform").text = (
            ",".join(str(i) for i in metadata.images[0].affine.to_gdal()))
        gcp_list = etree.SubElement(vrt_xml_tree, 'GCPList')
        gcp_list.attrib['Projection'] = crs_wkt
        for gcp in metadata.images[0].gcps:
            g = etree.SubElement(gcp_list, 'GCP')
            g.attrib["Id"] = gcp.id
            g.attrib['Pixel'] = str(gcp.col)
            g.attrib['Line'] = str(gcp.row)
            g.attrib['X'] = str(gcp.x)
            g.attrib['Y'] = str(gcp.y)
    return etree.tostring(vrt_xml_tree).decode("utf-8")


def _show_vrt(vrt: str):
    print(minidom.parseString(vrt).toprettyxml(indent="\t"))