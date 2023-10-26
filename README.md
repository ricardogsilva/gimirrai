# gimirrai

Playground for building a web API that serves up GIMI files.

This repository exists in the context of the [2023 October OGC Code Sprint](https://developer.ogc.org/sprints/22/).


## Installation

This code **requires** a custom version of libheif, as the changes needed to read
the sample GIMI files provided by OGC. Because of this, the code also **requires**
a locally built version of GDAL (which we then use to also compile rasterio from 
sources). Therefore, installation is a bit more involved than usual. There is 
however a set of scripts in the `scripts` directory which aid the process somewhat.

You will need to have some dependencies installed:

```sh
sudo apt install \
    build-essential \
    cmake \
    libgeotiff-dev \
    libopenjp2-7-dev \
    libpng-dev \
    libproj-dev \
    libspatialite-dev \
    libwebp-dev \
    libxml2-dev \
    python3-dev
```


Now:

1. Clone this repo

2. Execute the `scripts/linux_build_libs.py` script. This will build `libheif `.
   As implied in the name, this script only works on linux - actually it has 
   just been tested on ubuntu 22.04, so it may not even work on other distros)

   ```sh
   cd gimirrai
   python3 scripts/linux_build_libs.py
   ```

   This script will:

   - Download `libheif` and other related libs
   - Patch libheif
   - Compile everything
   - Install

3. Now execute the `scripts/build_gdal.py` script in order to build `GDAL`.

   ```shell
   python3 scripts/build_gdal.py
   ```

4. Ensure you have [poetry](https://python-poetry.org/) installed and use it
   to install the code with the following:

   ```sh
   GDAL_CONFIG=$(which gdal-config) poetry install
   ```
   
   This will install the project's requirements, including both `pillow-heif` and 
   `rasterio`, which will get built from sources (_i.e._ not using pre-built 
   binary wheels)

