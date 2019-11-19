"""
Support for TIFF imagery.
"""

from abc import ABC, abstractmethod
import math

from delta.config import config
from delta.imagery import rectangle

def horizontal_split(image_size, region, num_splits):
    """Return the ROI of an image to load given the region.
       Each region represents one horizontal band of the image.
    """

    assert region < num_splits, 'Input region ' + str(region) \
           + ' is greater than num_splits: ' + str(num_splits)

    min_x = 0
    max_x = image_size[0]

    # Fractional height here is fine
    band_height = image_size[1] / num_splits

    # TODO: Check boundary conditions!
    min_y = math.floor(band_height*region)
    max_y = math.floor(band_height*(region+1.0))

    return rectangle.Rectangle(min_x, min_y, max_x, max_y)

def tile_split(image_size, region, num_splits):
    """Return the ROI of an image to load given the region.
       Each region represents one tile in a grid split.
    """
    num_tiles = num_splits*num_splits
    assert region < num_tiles, 'Input region ' + str(region) \
           + ' is greater than num_tiles: ' + str(num_tiles)

    # Convert region index to row and column index
    tile_row = math.floor(region / num_splits)
    tile_col = region % num_splits

    # Fractional sizes are fine here
    tile_width  = math.floor(image_size[0] / num_splits)
    tile_height = math.floor(image_size[1] / num_splits)

    # TODO: Check boundary conditions!
    min_x = math.floor(tile_width  * tile_col)
    max_x = math.floor(tile_width  * (tile_col+1.0))
    min_y = math.floor(tile_height * tile_row)
    max_y = math.floor(tile_height * (tile_row+1.0))

    return rectangle.Rectangle(min_x, min_y, max_x, max_y)


class DeltaImage(ABC):
    """Base class used for wrapping input images in a way that they can be passed
       to Tensorflow dataset objects.
    """
    @abstractmethod
    def read(self, roi=None, band=None, buf=None):
        """
        Read the image of the given data type. An optional roi specifies the boundaries.
        """

    @abstractmethod
    def size(self):
        """Return the size of this image in pixels"""

    def width(self):
        return self.size()[1]

    def height(self):
        return self.size()[0]

    @abstractmethod
    def num_bands(self):
        """Return the number of bands in the image"""

    def tiles(self):
        """Generator to yield ROIs for the image."""
        max_block_bytes = config.dataset().max_block_size() * 1024 * 1024
        s = self.size()
        # TODO: account for image type
        image_bytes = s[0] * s[1] * self.num_bands() * 4
        num_regions = math.ceil(image_bytes / max_block_bytes)
        for i in range(num_regions):
            yield horizontal_split(s, i, num_regions)
