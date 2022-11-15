from glob import glob
from os.path import exists, join, basename
from tqdm import tqdm
from json import load, dump
from matplotlib import pyplot as plt
from detoxify import Detoxify

import torch
import time
import shutil
import os
import pickle
import cv2

import pandas as pd
import numpy as np

SHARE_DIR = "/project/zwang3049/diffusiondb-hugging"
WORK_DIR = "/nvmescratch/jay/diffusiondb"


def main():
    """
    Main function.
    """

    device = torch.device("cuda:0")
    toxicity_model = Detoxify("multilingual", device=device)

    prompts_2m = pd.read_parquet(
        join(SHARE_DIR, "metadata.parquet"), columns=["prompt"]
    )["prompt"]
    prompts_2m = list(set(prompts_2m))
    batch_size = 256

    lower = 0
    prompt_toxicity_map = {}

    # There are many same prompts, keep a dictionary
    with tqdm(total=len(prompts_2m)) as pbar:
        while lower < len(prompts_2m):
            higher = min(lower + batch_size, len(prompts_2m))
            cur_prompts = prompts_2m[lower:higher]

            result = toxicity_model.predict(cur_prompts)

            for i, p in enumerate(cur_prompts):
                # Prompt => [toxicity, sexual_explicity]
                prompt_toxicity_map[p] = [
                    result["toxicity"][i],
                    result["sexual_explicit"][i],
                ]

            # Next batch
            lower += batch_size
            pbar.update(batch_size)

    # Save the dictionary
    pickle.dump(
        prompt_toxicity_map, open(join(WORK_DIR, "prompt_toxicity_map_2m.pkl"), "wb")
    )


if __name__ == "__main__":
    main()
