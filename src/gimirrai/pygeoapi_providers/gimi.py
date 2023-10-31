"""pygeoapi provider for serving GIMI files."""

import logging
from pathlib import Path

import pillow_heif
import pyproj
import rasterio
import rasterio.io
import rasterio.mask
import rio_tiler.errors
import rio_tiler.io
from pygeoapi.models.provider.base import (
    TileMatrixSetEnum, TilesMetadataFormat, TileSetMetadata, LinkType,
    GeospatialDataType)
from pygeoapi.provider import base
from pygeoapi.provider.tile import BaseTileProvider
from pygeoapi.util import read_data

from .. import reader

logger = logging.getLogger(__name__)


class GimiCoverageProvider(base.BaseProvider):
    name: str
    type: str
    data: str  # path to the data file
    editable: bool
    options: dict
    id_field: str
    uri_field: str
    x_field: str
    y_field: str
    time_field: str
    title_field: str
    properties: list
    file_types: list[str]
    fields: dict
    filename: str
    axes: list
    crs: str
    num_bands: int

    _gimi_metadata: reader.GimiMetadata
    _data: rasterio.DatasetReader
    _coverage_properties: dict

    def _get_coverage_properties(self) -> dict:
        return {
            "bbox": [
                self._gimi_metadata.images[0].upper_left_lon,
                self._gimi_metadata.images[0].lower_right_lat,
                self._gimi_metadata.images[0].lower_right_lon,
                self._gimi_metadata.images[0].upper_left_lat,
            ],
            "bbox_crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84",
            "crs_type": "GeographicCRS",
            "bbox_units": "deg",
            "x_axis_label": "Long",
            "y_axis_label": "Lat",
            "axes": ["Long", "Lat"],
            "width": self._gimi_metadata.images[0].width,
            "height": self._gimi_metadata.images[0].height,
            "resx": self._gimi_metadata.images[0].x_resolution,
            "resy": self._gimi_metadata.images[0].y_resolution,
            "tags": {},
        }

    def __init__(self, provider_def):
        """
        Initialize object
        :param provider_def: provider definition
        :returns: pygeoapi.provider.rasterio_.RasterioProvider
        """

        super().__init__(provider_def)
        self.options = self.options if self.options is not None else {}
        try:
            self._gimi_metadata = reader.get_gimi_metadata(self.data)
            self._coverage_properties = self._get_coverage_properties()
            self.axes = self._coverage_properties['axes']
            self.crs = self._coverage_properties['bbox_crs']
            self.num_bands = len(self._gimi_metadata.images[0].bands)
            self.fields = [str(num) for num in range(1, self.num_bands+1)]
            self.native_format = provider_def['format']['name']
        except Exception as err:
            logger.warning(err)
            raise base.ProviderConnectionError(err)

    def get_coverage_domainset(self, *args, **kwargs) -> dict:
        return {
            'type': 'DomainSet',
            'generalGrid': {
                'type': 'GeneralGridCoverage',
                'srsName': self._coverage_properties['bbox_crs'],
                'axisLabels': [
                    self._coverage_properties['x_axis_label'],
                    self._coverage_properties['y_axis_label']
                ],
                'axis': [{
                    'type': 'RegularAxis',
                    'axisLabel': self._coverage_properties['x_axis_label'],
                    'lowerBound': self._coverage_properties['bbox'][0],
                    'upperBound': self._coverage_properties['bbox'][2],
                    'uomLabel': self._coverage_properties['bbox_units'],
                    'resolution': self._coverage_properties['resx']
                }, {
                    'type': 'RegularAxis',
                    'axisLabel': self._coverage_properties['y_axis_label'],
                    'lowerBound': self._coverage_properties['bbox'][1],
                    'upperBound': self._coverage_properties['bbox'][3],
                    'uomLabel': self._coverage_properties['bbox_units'],
                    'resolution': self._coverage_properties['resy']
                }],
                'gridLimits': {
                    'type': 'GridLimits',
                    'srsName': 'http://www.opengis.net/def/crs/OGC/0/Index2D',
                    'axisLabels': ['i', 'j'],
                    'axis': [{
                        'type': 'IndexAxis',
                        'axisLabel': 'i',
                        'lowerBound': 0,
                        'upperBound': self._coverage_properties['width']
                    }, {
                        'type': 'IndexAxis',
                        'axisLabel': 'j',
                        'lowerBound': 0,
                        'upperBound': self._coverage_properties['height']
                    }]
                }
            },
            '_meta': {
                'tags': self._coverage_properties['tags']
            }
        }

    def get_coverage_rangetype(self, *args, **kwargs):
        fields = []
        for index, band_metadata in self._gimi_metadata.images[0].bands.items():
            logger.debug(f'Determing rangetype for band {index}')
            fields.append(
                {
                    'id': band_metadata.index,
                    'type': 'Quantity',
                    'name': None,
                    'encodingInfo': {
                        'dataType': f'http://www.opengis.net/def/dataType/OGC/0/{band_metadata.dtype}'  # noqa
                    },
                    'nodata': band_metadata.no_data_value,
                }
            )
        return {
            "type": "DataRecord",
            "fields": fields
        }

    def query(
            self,
            properties=None,
            subsets=None,
            bbox: list[float] = None,
            bbox_crs=4326,
            datetime_=None,
            format_: str = 'json',
            **kwargs
    ):
        """
        Extract data from collection collection
        :param properties: list of bands
        :param subsets: dict of subset names with lists of ranges
        :param bbox: bounding box [minx,miny,maxx,maxy]
        :param datetime_: temporal (datestamp or extent)
        :param format_: data format of output

        :returns: coverage data as dict of CoverageJSON or native format
        """

        bands = properties if properties is not None else []
        subsets = subsets if subsets is not None else {}
        bbox = bbox if bbox is not None else []
        shapes = []

        if all([not bands, not subsets, not bbox, format_ != "json"]):
            logger.debug("No parameters specified, returning native data")
            return read_data(self.data)

        if all([self._coverage_properties['x_axis_label'] in subsets,
                self._coverage_properties['y_axis_label'] in subsets,
                len(bbox) > 0]):
            msg = 'bbox and subsetting by coordinates are exclusive'
            logger.warning(msg)
            raise base.ProviderQueryError(msg)

        if len(bbox) > 0:
            minx, miny, maxx, maxy = bbox
            crs_src = pyproj.CRS.from_epsg(bbox_crs)
            if (dest_crs_string := self.options.get("crs")) is not None:
                crs_dest = pyproj.CRS.from_string(dest_crs_string)
            else:
                crs_dest = crs_src

            if crs_src == crs_dest:
                logger.debug('source bbox CRS and data CRS are the same')
                shapes = [{
                    'type': 'Polygon',
                    'coordinates': [[
                        [minx, miny],
                        [minx, maxy],
                        [maxx, maxy],
                        [maxx, miny],
                        [minx, miny],
                    ]]
                }]
            else:
                logger.debug('source bbox CRS and data CRS are different')
                logger.debug('reprojecting bbox into native coordinates')

                t = pyproj.Transformer.from_crs(crs_src, crs_dest, always_xy=True)
                minx2, miny2 = t.transform(minx, miny)
                maxx2, maxy2 = t.transform(maxx, maxy)

                logger.debug(f'Source coordinates: {minx}, {miny}, {maxx}, {maxy}')  # noqa
                logger.debug(f'Destination: {minx2}, {miny2}, {maxx2}, {maxy2}')  # noqa

                shapes = [{
                    'type': 'Polygon',
                    'coordinates': [[
                        [minx2, miny2],
                        [minx2, maxy2],
                        [maxx2, maxy2],
                        [maxx2, miny2],
                        [minx2, miny2],
                    ]]
                }]

        elif (self._coverage_properties['x_axis_label'] in subsets and
              self._coverage_properties['y_axis_label'] in subsets):
            logger.debug('Creating spatial subset')

            x = self._coverage_properties['x_axis_label']
            y = self._coverage_properties['y_axis_label']

            shapes = [{
                'type': 'Polygon',
                'coordinates': [[
                    [subsets[x][0], subsets[y][0]],
                    [subsets[x][0], subsets[y][1]],
                    [subsets[x][1], subsets[y][1]],
                    [subsets[x][1], subsets[y][0]],
                    [subsets[x][0], subsets[y][0]]
                ]]
            }]

        args = {
            'indexes': None
        }
        if bands:
            logger.debug('Selecting bands')
            args['indexes'] = list(map(int, bands))

        logger.debug('Creating output coverage metadata')
        out_meta = {
            "bbox": [
                self._gimi_metadata.images[0].upper_left_lon,
                self._gimi_metadata.images[0].lower_right_lat,
                self._gimi_metadata.images[0].lower_right_lon,
                self._gimi_metadata.images[0].upper_left_lat,
            ],
            "driver": self.native_format,
            "dtype": self._gimi_metadata.images[0].bands[0].dtype,
            "nodata": self._gimi_metadata.images[0].bands[0].no_data_value,
            "units": self._gimi_metadata.images[0].bands[0].units,
            "width": self._gimi_metadata.images[0].width,
            "height": self._gimi_metadata.images[0].height,
            "count": len(self._gimi_metadata.images[0].bands),
            "crs": self._gimi_metadata.images[0].crs,
            "transform": self._gimi_metadata.images[0].affine,
        }
        for key, value in self.options.items():
            out_meta[key] = value

        with rasterio.open(self.data) as _data:
            if shapes:  # spatial subset
                try:
                    logger.debug('Clipping data with bbox')
                    out_image, out_transform = rasterio.mask.mask(
                        _data,
                        filled=False,
                        shapes=shapes,
                        crop=True,
                        indexes=args['indexes'])
                except ValueError as err:
                    raise base.ProviderQueryError(err)

                out_meta.update(
                    {
                        'height': out_image.shape[1],
                        'width': out_image.shape[2],
                        'transform': out_transform
                    }
                )
            else:  # no spatial subset
                logger.debug('Creating data in memory with band selection')
                out_image = _data.read(indexes=args['indexes'])

            if bbox:
                out_meta['bbox'] = bbox[:4]
            elif shapes:
                out_meta['bbox'] = [
                    subsets[x][0], subsets[y][0],
                    subsets[x][1], subsets[y][1]
                ]
            logger.debug('Serializing data in memory')
            with rasterio.io.MemoryFile() as memfile:
                with memfile.open(**out_meta) as dest:
                    dest.write(out_image)
                if format_ == 'json':
                    logger.debug('Creating output in CoverageJSON')
                    out_meta['bands'] = args['indexes']
                    return self.gen_covjson(out_meta, out_image)

                else:  # return data in native format
                    logger.debug('Returning data in native format')
                    return memfile.read()

    def gen_covjson(self, metadata: dict, data: rasterio.DatasetReader):
        """
        Generate coverage as CoverageJSON representation
        :param metadata: coverage metadata
        :param data: rasterio DatasetReader object
        :returns: dict of CoverageJSON representation
        """

        logger.debug('Creating CoverageJSON domain')
        minx, miny, maxx, maxy = metadata['bbox']

        cj = {
            'type': 'Coverage',
            'domain': {
                'type': 'Domain',
                'domainType': 'Grid',
                'axes': {
                    'x': {
                        'start': minx,
                        'stop': maxx,
                        'num': metadata['width']
                    },
                    'y': {
                        'start': maxy,
                        'stop': miny,
                        'num': metadata['height']
                    }
                },
                'referencing': [{
                    'coordinates': ['x', 'y'],
                    'system': {
                        'type': self._coverage_properties['crs_type'],
                        'id': self._coverage_properties['bbox_crs']
                    }
                }]
            },
            'parameters': {},
            'ranges': {}
        }

        if metadata['bands'] is None:  # all bands
            bands_select = list(self._gimi_metadata.images[0].bands.items())
        else:
            bands_select = metadata['bands']

        logger.debug(f'bands selected: {bands_select}')
        for band_index in bands_select:
            pm = _get_parameter_metadata(
                self._data.profile['driver'], self._data.tags(band_index))

            parameter = {
                'type': 'Parameter',
                'description': None,
                'unit': {
                    'symbol': None
                },
                'observedProperty': {
                    'id': None,
                    'label': {
                        'en': None
                    }
                }
            }

            cj['parameters'][band_index] = parameter

        try:
            for key in cj['parameters'].keys():
                cj['ranges'][key] = {
                    'type': 'NdArray',
                    # 'dataType': metadata.dtypes[0],
                    'dataType': 'float',
                    'axisNames': ['y', 'x'],
                    'shape': [metadata['height'], metadata['width']],
                }
                # TODO: deal with multi-band value output
                cj['ranges'][key]['values'] = data.flatten().tolist()
        except IndexError as err:
            logger.warning(err)
            raise base.ProviderQueryError('Invalid query parameter')

        return cj


def _get_parameter_metadata(driver, band) -> dict:
    """
    Helper function to derive parameter name and units
    :param driver: rasterio/GDAL driver name
    :param band: int of band number
    :returns: dict of parameter metadata
    """

    return {
        'id': None,
        'description': None,
        'unit_label': None,
        'unit_symbol': None,
        'observed_property_id': None,
        'observed_property_name': None
    }


class GimiTileProvider(BaseTileProvider):
    """A pygeoapi tiles provider that reads GIMI files."""

    def get_layer(self) -> str:
        return Path(self.data).name

    def get_tiling_schemes(self):
        tile_matrix_set_links_list = [
            TileMatrixSetEnum.WORLDCRS84QUAD.value,
            TileMatrixSetEnum.WEBMERCATORQUAD.value
        ]
        tile_matrix_set_links = [
            item for item in tile_matrix_set_links_list
            if item.tileMatrixSet in self.options['schemes']]
        return tile_matrix_set_links

    def get_tiles_service(
            self,
            baseurl=None,
            servicepath=None,
            dirpath=None,
            tile_type=None
    ):
        """
        Gets mvt service description

        :param baseurl: base URL of endpoint
        :param servicepath: base path of URL
        :param dirpath: directory basepath (equivalent of URL)
        :param tile_type: tile format type

        :returns: `dict` of item tile service
        """

        return {
            "links": []
        }

    def get_tiles(
            self,
            layer=None,
            tileset=None,
            z: str | None = None,
            y: str | None = None,
            x: str | None = None,
            format_: str = None
    ):
        """
        Gets tile

        :param layer: mvt tile layer
        :param tileset: mvt tileset
        :param z: z index
        :param y: y index
        :param x: x index
        :param format_: tile format

        :returns: an encoded mvt tile
        """
        # for now we will ignore the requested format
        gimi_metadata = reader.get_gimi_metadata(self.data)
        vrt_definition = reader.get_vrt(gimi_metadata)
        with rio_tiler.io.Reader(vrt_definition) as dataset:
            try:
                tile = dataset.tile(tile_x=int(x), tile_y=int(y), tile_z=(z))
            except rio_tiler.errors.TileOutsideBounds as err:
                logger.info(f"Tile {z=} - {x=} - {y=} outside bounds")
            else:
                return tile.render(img_format="PNG")

    def get_metadata(
            self,
            dataset,
            server_url,
            layer=None,
            tileset=None,
            metadata_format=None,
            title=None,
            description=None,
            keywords=None,
            **kwargs
    ):
        return {}