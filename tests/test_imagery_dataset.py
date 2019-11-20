#pylint: disable=redefined-outer-name
import os
import random
import shutil
import tempfile

import zipfile
from osgeo import gdal
import pytest
import numpy as np
import tensorflow as tf
from tensorflow import keras

from delta.config import config
from delta.imagery import imagery_dataset
from delta.imagery.sources import tfrecord
from delta.imagery.sources.tiff import TiffWriter
from delta.ml import train

def generate_tile(width=32, height=32, blocks=50):
    """Generate a widthXheightX3 image, with blocks pixels surrounded by ones and the rest zeros in band 0"""
    image = np.zeros((width, height, 1), np.float32)
    label = np.zeros((width, height), np.uint8)
    for _ in range(blocks):
        x = random.randint(2, width - 3)
        y = random.randint(2, height - 3)
        # ensure non-overlapping
        while (image[x + 2, y - 2 : y + 2, 0] > 0.0).any() or (image[x + 2, y - 2 : y + 2, 0] > 0.0).any() or \
              (image[x - 1 : x + 1, y - 2, 0] > 0.0).any() or (image[x - 1 : x + 1, y + 2, 0] > 0.0).any():
            x = random.randint(2, width - 3)
            y = random.randint(2, height - 3)
        image[x + 1, y - 1, 0] = 1.0
        image[x    , y - 1, 0] = 1.0
        image[x - 1, y - 1, 0] = 1.0
        image[x + 1, y    , 0] = 1.0
        image[x - 1, y    , 0] = 1.0
        image[x + 1, y + 1, 0] = 1.0
        image[x    , y + 1, 0] = 1.0
        image[x - 1, y + 1, 0] = 1.0
        label[x, y] = 1
    return (image, label)

@pytest.fixture(scope="module")
def tfrecord_filenames():
    tmpdir = tempfile.mkdtemp()
    image_path = os.path.join(tmpdir, 'test.tfrecord')
    label_path = os.path.join(tmpdir, 'test.tfrecordlabel')
    image_writer = tfrecord.make_tfrecord_writer(image_path)
    label_writer = tfrecord.make_tfrecord_writer(label_path)
    size = 32
    for i in range(2):
        for j in range(2):
            (image, label) = generate_tile(size, size)
            tfrecord.write_tfrecord_image(image, image_writer,
                                          i * size, j * size,
                                          size, size, 1)
            tfrecord.write_tfrecord_image(label, label_writer,
                                          i * size, j * size,
                                          size, size, 1)
    image_writer.close()
    label_writer.close()
    yield (image_path, label_path)

    shutil.rmtree(tmpdir)

@pytest.fixture(scope="module")
def worldview_filenames():
    size = 64
    tmpdir = tempfile.mkdtemp()
    image_name = 'WV02N42_939570W073_2520792013040400000000MS00_GU004003002'
    imd_name = '19MAY13164205-M2AS-503204071020_01_P003.IMD'
    zip_path = os.path.join(tmpdir, image_name + '.zip')
    label_path = os.path.join(tmpdir, image_name + '_label.tiff')
    image_dir = os.path.join(tmpdir, 'image')
    image_path = os.path.join(image_dir, image_name + '.tif')
    vendor_dir = os.path.join(image_dir, 'vendor_metadata')
    imd_path = os.path.join(vendor_dir, imd_name)
    os.mkdir(image_dir)
    os.mkdir(vendor_dir)
    open(imd_path, 'a').close() # only metadata file we use
    image_writer = TiffWriter(image_path, size, size, data_type=gdal.GDT_Float32)
    label_writer = TiffWriter(label_path, size, size, data_type=gdal.GDT_Byte)

    (image, label) = generate_tile(size, size)
    image_writer.write_block(image[:,:,0], 0, 0, 0)
    label_writer.write_block(label, 0, 0, 0)
    del image_writer
    del label_writer

    z = zipfile.ZipFile(zip_path, mode='x')
    z.write(image_path, arcname=image_name + '.tif')
    z.write(imd_path, arcname=os.path.join('vendor_metadata', imd_name))
    z.close()

    yield (zip_path, label_path)

    shutil.rmtree(tmpdir)

NUM_SOURCES = 2
@pytest.fixture(scope="module")
def all_sources(tfrecord_filenames, worldview_filenames):
    return [(tfrecord_filenames, '.tfrecord', 'tfrecord', 'tfrecord', '.tfrecordlabel', 'tfrecord'),
            (worldview_filenames, '.zip', 'worldview', 'worldview', '_label.tiff', 'tiff')]

@pytest.fixture(scope="function", params=range(2))
def dataset(all_sources, request):
    source = all_sources[request.param]
    config.reset() # don't load any user files
    (image_path, label_path) = source[0]
    config.set_value('input_dataset', 'extension', source[1])
    config.set_value('input_dataset', 'image_type', source[2])
    config.set_value('input_dataset', 'file_type', source[3])
    config.set_value('input_dataset', 'label_extension', source[4])
    config.set_value('input_dataset', 'label_file_type', source[5])
    config.set_value('input_dataset', 'data_directory', os.path.dirname(image_path))
    config.set_value('input_dataset', 'label_directory', os.path.dirname(label_path))
    config.set_value('ml', 'chunk_size', 3)
    config.set_value('cache', 'cache_dir', os.path.dirname(image_path))
    dataset = imagery_dataset.ImageryDataset(config.dataset(), config.chunk_size(), config.chunk_stride())
    return dataset

def test_tfrecord_write_read(dataset): #pylint: disable=redefined-outer-name
    """
    Writes and reads from disks, then checks if what is read is valid according to the
    generation procedure.
    """

    ds = dataset.dataset(filter_zero=False)
    iterator = iter(ds.batch(1))
    for (image, label) in iterator:
        try:
            if label:
                assert image[0][0][0][0] == 1
                assert image[0][0][1][0] == 1
                assert image[0][0][2][0] == 1
                assert image[0][1][0][0] == 1
                assert image[0][1][2][0] == 1
                assert image[0][2][0][0] == 1
                assert image[0][2][1][0] == 1
                assert image[0][2][2][0] == 1
            v1 = image[0][0][0][0] == 0
            v2 = image[0][0][1][0] == 0
            v3 = image[0][0][2][0] == 0
            if v1 or v2 or v3:
                assert label == 0
            v4 = image[0][1][0][0] == 0
            v5 = image[0][1][2][0] == 0
            if v4 or v5:
                assert label == 0
            v6 = image[0][2][0][0] == 0
            v7 = image[0][2][1][0] == 0
            v8 = image[0][2][2][0] == 0
            if v6 or v7 or v8:
                assert label == 0
        except tf.errors.OutOfRangeError:
            break


def test_train(dataset): #pylint: disable=redefined-outer-name
    def model_fn():
        return  keras.Sequential([
            keras.layers.Conv2D(1, kernel_size=(3, 3),
                                kernel_initializer=keras.initializers.Zeros(),
                                activation='relu', data_format='channels_last',
                                input_shape=(3, 3, 1))])
    def create_dataset():
        d = dataset.dataset(filter_zero=False)
        d = d.batch(100).repeat(5)
        return d

    # Ignoring returned model training history to keep pylint happy.
    model, _ = train.train(model_fn, create_dataset,
                           optimizer=tf.optimizers.Adam(learning_rate=0.01),
                           loss_fn='mean_squared_logarithmic_error',
                           num_epochs=1,
                           validation_data=None,
                           num_gpus=0)
    ret = model.evaluate(x=create_dataset())
    assert ret[1] > 0.90