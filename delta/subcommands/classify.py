# Copyright © 2020, United States Government, as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All rights reserved.
#
# The DELTA (Deep Earth Learning, Tools, and Analysis) platform is
# licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Classify input images given a model.
"""
import os.path

import time
import numpy as np
import matplotlib
import tensorflow as tf

from delta.config import config
from delta.config.extensions import custom_objects, image_writer
from delta.ml import predict
from delta.extensions.sources.tiff import write_tiff

matplotlib.use('Agg')
import matplotlib.pyplot as plt #pylint: disable=wrong-import-order,wrong-import-position,ungrouped-imports

def save_confusion(cm, class_labels, filename):
    f = plt.figure()
    ax = f.add_subplot(1, 1, 1)
    image = ax.imshow(cm, interpolation='nearest', cmap=plt.get_cmap('inferno'))
    ax.set_title('Confusion Matrix')
    f.colorbar(image)
    ax.set_xlim(-0.5, cm.shape[0] - 0.5)
    ax.set_ylim(-0.5, cm.shape[0] - 0.5)
    ax.set_xticks(range(cm.shape[0]))
    ax.set_yticks(range(cm.shape[0]))
    ax.set_xticklabels(class_labels)
    ax.set_yticklabels(class_labels)
    m = cm.max()
    total = cm.sum()

    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, '%d\n%.2g%%' % (cm[i, j], cm[i, j] / total * 100), horizontalalignment='center',
                    color='white' if cm[i, j] < m / 2 else 'black')
    ax.set_ylabel('True Label')
    ax.set_xlabel('Predicted Label')
    f.savefig(filename)

def ae_convert(data):
    r = np.clip((data[:, :, [4, 2, 1]]  * np.float32(100.0)), 0.0, 255.0).astype(np.uint8)
    return r

def main(options):

    # TODO: Share the way this is done with in ml/train.py
    cpuOnly = (config.general.gpus()==0)

    if cpuOnly:
        with tf.device('/cpu:0'):
            model = tf.keras.models.load_model(options.model, custom_objects=custom_objects(), compile=False)
    else:
        model = tf.keras.models.load_model(options.model, custom_objects=custom_objects(), compile=False)

    colors = list(map(lambda x: x.color, config.dataset.classes))
    error_colors = np.array([[0x0, 0x0, 0x0],
                             [0xFF, 0x00, 0x00]], dtype=np.uint8)
    if options.noColormap:
        colors=None # Forces raw one channel output

    start_time = time.time()
    images = config.dataset.images()
    labels = config.dataset.labels()
    net_name = os.path.splitext(os.path.basename(options.model))[0]

    full_cm = None
    if options.autoencoder:
        labels = None
    for (i, path) in enumerate(images):
        image = images.load(i)
        base_name = os.path.splitext(os.path.basename(path))[0]
        writer = image_writer('tiff')
        prob_image = writer(net_name + '_' + base_name + '.tiff') if options.prob else None
        output_image = writer(net_name + '_' + base_name + '.tiff') if not options.prob else None

        error_image = None
        label = None
        if labels:
            error_image = writer('errors_' + base_name + '.tiff')
            label = labels.load(i)
            assert image.size() == label.size(), 'Image and label do not match.'

        ts = config.io.tile_size()
        if options.autoencoder:
            label = image
            predictor = predict.ImagePredictor(model, ts, output_image, True,
                                               None if options.noColormap else (ae_convert, np.uint8, 3))
        else:
            predictor = predict.LabelPredictor(model, ts, output_image, True, colormap=colors,
                                               prob_image=prob_image, error_image=error_image,
                                               error_colors=error_colors)

        overlap = (options.overlap, options.overlap)
        try:
            if cpuOnly:
                with tf.device('/cpu:0'):
                    predictor.predict(image, label, overlap=overlap)
            else:
                predictor.predict(image, label, overlap=overlap)
        except KeyboardInterrupt:
            print('\nAborted.')
            return 0

        if labels:
            cm = predictor.confusion_matrix()
            if full_cm is None:
                full_cm = np.copy(cm).astype(np.int64)
            else:
                full_cm += cm
            for j in range(cm.shape[0]):
                print('%s--- Precision: %.2f%%    Recall: %.2f%%      Pixels: %d / %d' % \
                      (config.dataset.classes[j].name,
                       100 * cm[j,j] / np.sum(cm[:, j]),
                       100 * cm[j,j] / np.sum(cm[j, :]),
                       int(np.sum(cm[j, :])), int(np.sum(cm))))
            print('%.2f%% Correct: %s' % (float(np.sum(np.diag(cm)) / np.sum(cm) * 100), path))
            save_confusion(cm, map(lambda x: x.name, config.dataset.classes), 'confusion_' + base_name + '.pdf')

        if options.autoencoder:
            write_tiff('orig_' + base_name + '.tiff', image.read() if options.noColormap else ae_convert(image.read()),
                       metadata=image.metadata())
    stop_time = time.time()
    if labels:
        for i in range(full_cm.shape[0]):
            print('%s--- Precision: %.2f%%    Recall: %.2f%%        Pixels: %d / %d' % \
                    (config.dataset.classes[i].name,
                     100 * full_cm[i,i] / np.sum(full_cm[:, i]),
                     100 * full_cm[i,i] / np.sum(full_cm[i, :]),
                     int(np.sum(cm[j, :])), int(np.sum(cm))))
    print('Elapsed time = ', stop_time - start_time)
    return 0
