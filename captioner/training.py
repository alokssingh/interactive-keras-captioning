# -*- coding: utf-8 -*-
from __future__ import print_function
from six import iteritems
import copy
import sys
import time
import codecs
from timeit import default_timer as timer

import logging
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
logger = logging.getLogger(__name__)

from keras_wrapper.model_ensemble import BeamSearchEnsemble
from keras_wrapper.cnn_model import saveModel, updateModel
from keras_wrapper.dataset import loadDataset, saveDataset
from keras_wrapper.extra.read_write import dict2pkl, file2list
from data_engine.prepare_data import build_dataset
from captioner.model_zoo import Captioning_Model
from captioner.build_callbacks import buildCallbacks


def train_model(params):
    """
    Training function. Sets the training parameters from params. Build or loads the model and launches the training.
    :param params: Dictionary of network hyperparameters.
    :return: None
    """

    if params['RELOAD'] > 0:
        logging.info('Resuming training.')

    # Load data
    dataset = build_dataset(params)
    params['OUTPUT_VOCABULARY_SIZE'] = dataset.vocabulary_len[params['OUTPUTS_IDS_DATASET'][0]]

    # Build model
    if (params['RELOAD'] == 0):  # build new model
        video_model = Captioning_Model(params,
                                       model_type=params['MODEL_TYPE'],
                                       verbose=params['VERBOSE'],
                                       model_name=params['MODEL_NAME'],
                                       vocabularies=dataset.vocabulary,
                                       store_path=params['STORE_PATH'])
        dict2pkl(params, params['STORE_PATH'] + '/config')

        # Define the inputs and outputs mapping from our Dataset instance to our model
        inputMapping = dict()
        for i, id_in in enumerate(params['INPUTS_IDS_DATASET']):
            if len(video_model.ids_inputs) > i:
                pos_source = dataset.ids_inputs.index(id_in)
                id_dest = video_model.ids_inputs[i]
                inputMapping[id_dest] = pos_source
        video_model.setInputsMapping(inputMapping)

        outputMapping = dict()
        for i, id_out in enumerate(params['OUTPUTS_IDS_DATASET']):
            if len(video_model.ids_outputs) > i:
                pos_target = dataset.ids_outputs.index(id_out)
                id_dest = video_model.ids_outputs[i]
                outputMapping[id_dest] = pos_target
        video_model.setOutputsMapping(outputMapping)

    else:  # resume from previously trained model
        video_model = loadModel(params['STORE_PATH'], params['RELOAD'])
        video_model.setOptimizer()

    # Callbacks
    callbacks = buildCallbacks(params, video_model, dataset)

    # Training
    total_start_time = timer()

    logger.debug('Starting training!')
    training_params = {'n_epochs': params['MAX_EPOCH'],
                       'batch_size': params['BATCH_SIZE'],
                       'homogeneous_batches': params['HOMOGENEOUS_BATCHES'],
                       'maxlen': params['MAX_OUTPUT_TEXT_LEN'],
                       'joint_batches': params['JOINT_BATCHES'],
                       'lr_decay': params.get('LR_DECAY', None),  # LR decay parameters
                       'initial_lr': params.get('LR', 1.0),
                       'reduce_each_epochs': params.get('LR_REDUCE_EACH_EPOCHS', True),
                       'start_reduction_on_epoch': params.get('LR_START_REDUCTION_ON_EPOCH', 0),
                       'lr_gamma': params.get('LR_GAMMA', 0.9),
                       'lr_reducer_type': params.get('LR_REDUCER_TYPE', 'linear'),
                       'lr_reducer_exp_base': params.get('LR_REDUCER_EXP_BASE', 0),
                       'lr_half_life': params.get('LR_HALF_LIFE', 50000),
                       'lr_warmup_exp': params.get('WARMUP_EXP', -1.5),
                       'min_lr': params.get('MIN_LR', 1e-9),
                       'epochs_for_save': params['EPOCHS_FOR_SAVE'],
                       'verbose': params['VERBOSE'],
                       'eval_on_sets': params['EVAL_ON_SETS_KERAS'],
                       'n_parallel_loaders': params['PARALLEL_LOADERS'],
                       'extra_callbacks': callbacks,
                       'reload_epoch': params['RELOAD'],
                       'epoch_offset': params.get('EPOCH_OFFSET', 0),
                       'data_augmentation': params['DATA_AUGMENTATION'],
                       'patience': params.get('PATIENCE', 0),  # early stopping parameters
                       'metric_check': params.get('STOP_METRIC', None) if params.get('EARLY_STOP', False) else None,
                       'eval_on_epochs': params.get('EVAL_EACH_EPOCHS', True),
                       'each_n_epochs': params.get('EVAL_EACH', 1),
                       'start_eval_on_epoch': params.get('START_EVAL_ON_EPOCH', 0),
                       'tensorboard': params.get('TENSORBOARD', False),
                       'n_gpus': params.get('N_GPUS', 1),
                       'tensorboard_params': {'log_dir': params.get('LOG_DIR', 'tensorboard_logs'),
                                              'histogram_freq': params.get('HISTOGRAM_FREQ', 0),
                                              'batch_size': params.get('TENSORBOARD_BATCH_SIZE', params['BATCH_SIZE']),
                                              'write_graph': params.get('WRITE_GRAPH', True),
                                              'write_grads': params.get('WRITE_GRADS', False),
                                              'write_images': params.get('WRITE_IMAGES', False),
                                              'embeddings_freq': params.get('EMBEDDINGS_FREQ', 0),
                                              'embeddings_layer_names': params.get('EMBEDDINGS_LAYER_NAMES', None),
                                              'embeddings_metadata': params.get('EMBEDDINGS_METADATA', None),
                                              'label_word_embeddings_with_vocab': params.get('LABEL_WORD_EMBEDDINGS_WITH_VOCAB', False),
                                              'word_embeddings_labels': params.get('WORD_EMBEDDINGS_LABELS', None),
                                              }
                       }
    video_model.trainNet(dataset, training_params)

    total_end_time = timer()
    time_difference = total_end_time - total_start_time
    logging.info('In total is {0:.2f}s = {1:.2f}m'.format(time_difference, time_difference / 60.0))
