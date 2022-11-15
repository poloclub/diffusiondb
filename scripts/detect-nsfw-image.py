from glob import glob
from os.path import exists, join, basename
from tqdm import tqdm
from json import load, dump
from multiprocessing import Process, JoinableQueue

import time
import shutil
import os
import random
import cv2
import multiprocessing

import numpy as np
import tensorflow_io as tfio
import tensorflow_hub as hub

LARGE_MODE = True

BATCH_SIZE = 128
USE_CPU = False
VERBOSE = False

ZIP_DIR1 = "/project/zwang3049/diffusiondb-hugging/diffusiondb-large-part-1/"
ZIP_DIR2 = "/project/zwang3049/diffusiondb-hugging/diffusiondb-large-part-2/"
ZIP_DIR_2M = "/project/zwang3049/diffusiondb-hugging/images/"
WORK_DIR = "/nvmescratch/jay/diffusiondb"

if LARGE_MODE:
    NSFW_SCORE_DIR = "/nvmescratch/jay/diffusiondb/nsfw-scores-large"
else:
    NSFW_SCORE_DIR = "/nvmescratch/jay/diffusiondb/nsfw-scores-2m"


def consumer_detect_nsfw(
    zipped_queue: JoinableQueue,
    unzipped_queue: JoinableQueue,
    part_ids_queue: JoinableQueue,
    gpu_id: int,
):
    """
    Predict NSFW scores for all iamges in the folder.
    """

    import tensorflow as tf

    global tf

    gpus = tf.config.experimental.list_physical_devices("GPU")
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)

    def get_prompt(file_path, json_data):
        """
        Get the image prompt.
        """
        img_name = basename(file_path)
        return json_data[img_name]["p"]

    def get_image(file_path):
        """
        Get the processed image array and its sharpness score.
        """
        # Read the image
        img_file = tf.io.read_file(file_path)
        if ".webp" in file_path:
            img = tfio.image.decode_webp(img_file)[:, :, :3]
        elif ".png" in file_path:
            img = tf.io.decode_image(img_file)[:, :, :3]

        # Blur detection
        # shaprness = cv2.Laplacian(img.numpy(), cv2.CV_64F).var()
        gray = cv2.cvtColor(img.numpy(), cv2.COLOR_RGB2GRAY)
        shaprness = np.max(cv2.convertScaleAbs(cv2.Laplacian(gray, 3)))

        # Rescale to 0-1
        normalizer = tf.keras.layers.Rescaling(1.0 / 255)

        # Resize to fit the NSFW model
        resized_img = tf.image.resize(img, [260, 260], antialias=True)

        return normalizer(resized_img), shaprness

    # Load the model
    with tf.device(f"/device:GPU:{gpu_id}"):
        cache_folder = join(WORK_DIR, "./NSFW-cache")
        model = tf.keras.models.load_model(
            join(cache_folder, "nsfweffnetv2-b02-3epochs.h5"),
            custom_objects={"KerasLayer": hub.KerasLayer},
        )

    while True:
        part_id = zipped_queue.get()
        print("Start consuming", part_id)

        # Tell producer to produce the next batch
        if not part_ids_queue.empty():
            item = part_ids_queue.get()
            unzipped_queue.put(item)
            part_ids_queue.task_done()

        zip_path = join(WORK_DIR, f"part-{part_id:06}.zip")
        data_dir = join(WORK_DIR, f"part-{part_id:06}")
        json_data = load(
            open(join(data_dir, f"part-{part_id:06}.json"), "r", encoding="utf8")
        )

        # We should not loop over images here because the model.predict()'s
        # "computation is done in batches. This method is designed for batch
        # processing of large numbers of inputs. It is not intended for use inside
        # of loops that iterate over your data and process small numbers of inputs
        # at a time."
        names = []
        prompts = []
        images = []
        images_sharpness = []

        try:
            with tf.device(f"/device:GPU:{gpu_id}"):
                for f in tqdm(
                    glob(join(data_dir, "*.webp")), position=gpu_id, disable=not VERBOSE
                ):
                    names.append(basename(f))
                    prompts.append(get_prompt(f, json_data))
                    img, sharpness = get_image(f)
                    images.append(img)
                    images_sharpness.append(sharpness)

                for f in tqdm(
                    glob(join(data_dir, "*.png")), position=gpu_id, disable=not VERBOSE
                ):
                    names.append(basename(f))
                    prompts.append(get_prompt(f, json_data))
                    img, sharpness = get_image(f)
                    images.append(img)
                    images_sharpness.append(sharpness)

                all_images = tf.stack(images)

                # Get the multi-class probability
                nsfw_scores = model.predict(all_images, verbose=0)
                nsfw_scores_prob = tf.nn.softmax(nsfw_scores).numpy()

                # Transfer the multi-class probs to binary
                # Columns are: drawing, hentai, neutral, porn, and sexy
                trans_mat = np.array(
                    [
                        [
                            0.0,
                            1.0,
                            0.0,
                            1.0,
                            1.0,
                        ]
                    ]
                ).transpose()
                nsfw_scores_binary = np.dot(nsfw_scores_prob, trans_mat).reshape(-1)

                # Override the original NSFW scores of blur images as 1.1
                images_sharpness = np.array(images_sharpness)
                nsfw_scores_binary[images_sharpness < 10] = 2.0

                # Save the scores
                cur_score_path = join(NSFW_SCORE_DIR, f"part-{part_id:06}.npz")
                np.savez_compressed(
                    cur_score_path,
                    images_name=names,
                    images_nsfw=nsfw_scores_binary,
                )

                del all_images

        except KeyError:
            print("Key error!", part_id)

        # Remove the zip file and image files
        os.remove(zip_path)
        shutil.rmtree(data_dir)

        print("Finish consuming", part_id)

        zipped_queue.task_done()


def producer_unzip_images(zipped_queue: JoinableQueue, unzipped_queue: JoinableQueue):
    """
    Download and unzip zip files.
    """

    while True:
        part_id = unzipped_queue.get()
        print("Start producing", part_id)

        # Download and extract the zip file
        cur_zip = join(WORK_DIR, f"part-{part_id:06}.zip")

        if LARGE_MODE:
            if part_id > 10000:
                shutil.copyfile(
                    join(ZIP_DIR2, f"part-{part_id:06}.zip"),
                    cur_zip,
                )
            else:
                shutil.copyfile(
                    join(ZIP_DIR1, f"part-{part_id:06}.zip"),
                    cur_zip,
                )
        else:
            shutil.copyfile(join(ZIP_DIR_2M, f"part-{part_id:06}.zip"), cur_zip)

        img_dir = join(WORK_DIR, f"part-{part_id:06}")
        shutil.unpack_archive(cur_zip, img_dir)

        print("Finish producing", part_id)
        zipped_queue.put(part_id)
        unzipped_queue.task_done()


def main():
    """
    Main function.
    """
    start_time = time.time()
    multiprocessing.set_start_method("spawn")
    part_ids = list(range(1, 14001))
    print(part_ids[0], part_ids[-1])

    # Produce NSFW scores in parallel
    zipped_queue = JoinableQueue()
    unzipped_queue = JoinableQueue()
    part_ids_queue = JoinableQueue()

    n_producers = 4
    n_consumers = 4

    # Producer
    for _ in range(n_producers):
        Process(
            target=producer_unzip_images,
            args=(zipped_queue, unzipped_queue),
            daemon=True,
        ).start()

    # Consumer
    for gpu_id in range(n_consumers):
        Process(
            target=consumer_detect_nsfw,
            args=(zipped_queue, unzipped_queue, part_ids_queue, gpu_id % 2 + 2),
            daemon=True,
        ).start()

    for part_id in part_ids:
        part_ids_queue.put(part_id)

    # Start n processes
    for _ in range(n_producers):
        item = part_ids_queue.get()
        unzipped_queue.put(item)
        part_ids_queue.task_done()

    part_ids_queue.join()
    unzipped_queue.join()
    zipped_queue.join()

    print("Finished in", (time.time() - start_time) / 60, "minutes")


if __name__ == "__main__":
    main()
