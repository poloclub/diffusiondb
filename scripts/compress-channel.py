from glob import glob
from os.path import exists, join, basename
from tqdm import tqdm
from json import load, dump
from multiprocessing import Pool
from functools import partial

import re
import os
import shutil
import time
import random

PART_DIR = "/project/zwang3049/diffusiondb/images"
SHARE_PART_DIR = "/project/zwang3049/diffusiondb-hugging/images"
N_PROC = 36

if not exists(SHARE_PART_DIR):
    os.makedirs(SHARE_PART_DIR)


def zip_dir(cur_part):
    """
    Zip a image part folder.
    Args:
        cur_part (int): The id of the image part folder
    """
    cur_part_path = join(PART_DIR, f"part-{cur_part:06}")
    cur_zip_path = join(SHARE_PART_DIR, f"part-{cur_part:06}")
    shutil.make_archive(cur_zip_path, "zip", cur_part_path)


def main():
    """
    Main function
    """

    start_time = time.time()
    part_ids = list(range(1741, 2001))

    # Zip files in parallel
    print(part_ids)
    with Pool(N_PROC) as p:
        result = list(tqdm(p.imap(zip_dir, part_ids), total=len(part_ids)))

    print("Finished in", (time.time() - start_time) / 60, "minutes")


if __name__ == "__main__":
    main()
