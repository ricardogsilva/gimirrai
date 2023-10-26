# gimirrai

Playground for building a web API that serves up GIMI files.

This repository exists in the context of the [2023 October OGC Code Sprint](https://developer.ogc.org/sprints/22/).


## Installation

This code **requires** a custom version of libheif, as the changes needed to read
the sample GIMI files provided by OGC. Therefore, installation is a bit more involved
than usual. There is however a script in `scripts/linux_build_libs.py` which aids
the process somewhat.

You will need to have some dependencies installed:

```sh
sudo apt install \
    build-essential \
    cmake \
    python3-dev
```


Now:

1. Clone this repo

2. Execute the `scripts/linux_build_libs.py` script. As implied in the name, 
   this script only works on linux - actually it has just been tested on 
   ubuntu 22.04, so it may not even work on other distros)

   ```sh
   cd gimirrai
   python3 scripts/linux_build_libs.py
   ```

   This script will:

   - Download `libheif` and other related libs
   - Patch libheif
   - Compile everything
   - Install

3. Ensure you have [poetry](https://python-poetry.org/) installed and use it
   to install the code

   ```sh
   poetry install
   ```

