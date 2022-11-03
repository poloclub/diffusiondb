# DiffusionDB  <a href="https://huggingface.co/datasets/poloclub/diffusiondb"><img align="right" src="favicon.ico" height="40"></img></a>

[![hugging](https://img.shields.io/badge/🤗%20Hugging%20Face-Datasets-yellow)](https://huggingface.co/datasets/poloclub/diffusiondb)
[![license](https://img.shields.io/badge/License-CC0/MIT-blue)](#licensing)
[![arxiv badge](https://img.shields.io/badge/arXiv-2210.14896-red)](https://arxiv.org/abs/2210.14896)
[![datasheet](https://img.shields.io/badge/Data%20Sheet-Available-success)](https://poloclub.github.io/diffusiondb/datasheet.html)
<!-- [![DOI:10.1145/3491101.3519653](https://img.shields.io/badge/DOI-10.1145/3491101.3519653-blue)](https://doi.org/10.1145/3491101.3519653) -->
<!-- ![](https://i.imgur.com/OJtU5zv.png) -->

<img width="100%" src="https://user-images.githubusercontent.com/15007159/198505835-bcc3a34f-a782-4064-989b-135e32b577a7.gif">

DiffusionDB is the first  large-scale text-to-image prompt dataset. It contains 2 million images generated by Stable Diffusion using prompts and hyperparameters specified by real users. The unprecedented scale and diversity of this human-actuated dataset provide exciting research opportunities in understanding the interplay between prompts and generative models, detecting deepfakes, and designing human-AI interaction tools to help users more easily use these models.

## Get Started

DiffusionDB is available at [🤗 Hugging Face Datasets](https://huggingface.co/datasets/poloclub/diffusiondb).

## Dataset Structure

We use a modularized file structure to distribute DiffusionDB. The 2 million images in DiffusionDB are split into 2,000 folders, where each folder contains 1,000 images and a JSON file that links these 1,000 images to their prompts and hyperparameters.

```bash
./
├── images
│   ├── part-000001
│   │   ├── 3bfcd9cf-26ea-4303-bbe1-b095853f5360.png
│   │   ├── 5f47c66c-51d4-4f2c-a872-a68518f44adb.png
│   │   ├── 66b428b9-55dc-4907-b116-55aaa887de30.png
│   │   ├── 99c36256-2c20-40ac-8e83-8369e9a28f32.png
│   │   ├── f3501e05-aef7-4225-a9e9-f516527408ac.png
│   │   ├── [...]
│   │   └── part-000001.json
│   ├── part-000002
│   ├── part-000003
│   ├── part-000004
│   ├── [...]
│   └── part-002000
└── metadata.parquet
```

These sub-folders have names `part-00xxxx`, and each image has a unique name generated by [UUID Version 4](https://en.wikipedia.org/wiki/Universally_unique_identifier). The JSON file in a sub-folder has the same name as the sub-folder. Each image is a PNG file. The JSON file contains key-value pairs mapping image filenames to their prompts and hyperparameters. For example, below is the image of `f3501e05-aef7-4225-a9e9-f516527408ac.png` and its key-value pair in `part-000001.json`.

<img width="300" src="https://i.imgur.com/gqWcRs2.png">

```json
{
  "f3501e05-aef7-4225-a9e9-f516527408ac.png": {
    "p": "geodesic landscape, john chamberlain, christopher balaskas, tadao ando, 4 k, ",
    "se": 38753269,
    "c": 12.0,
    "st": 50,
    "sa": "k_lms"
  },
}
```

The data fields are:

- key: Unique image name
- `p`: Prompt
- `se`: Random seed
- `c`: CFG Scale (guidance scale)
- `st`: Steps
- `sa`: Sampler

At the top level folder of DiffusionDB, we include a metadata table in Parquet format `metadata.parquet`.
This table has seven columns: `image_name`, `prompt`, `part_id`, `seed`, `step`, `cfg`, and `sampler`, and it has 2 million rows where each row represents an image. `seed`, `step`, and `cfg` are We choose Parquet because it is column-based: researchers can efficiently query individual columns (e.g., prompts) without reading the entire table. Below are the five random rows from the table.

| image_name                               | prompt                                                                                                                                                                                                  | part_id | seed       | step | cfg | sampler |
|------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------|------------|------|-----|---------|
| 49f1e478-ade6-49a8-a672-6e06c78d45fc.png | ryan gosling in fallout 4 kneels near a nuclear bomb                                                                                                                                                    | 1643    | 2220670173 | 50   | 7.0 | 8       |
| b7d928b6-d065-4e81-bc0c-9d244fd65d0b.png | A beautiful robotic woman dreaming, cinematic lighting, soft bokeh, sci-fi, modern, colourful, highly detailed, digital painting, artstation, concept art, sharp focus, illustration, by greg rutkowski | 87      | 51324658   | 130  | 6.0 | 8       |
| 19b1b2f1-440e-4588-ba96-1ac19888c4ba.png | bestiary of creatures from the depths of the unconscious psyche, in the style of a macro photograph with shallow dof                                                                                    | 754     | 3953796708 | 50   | 7.0 | 8       |
| d34afa9d-cf06-470f-9fce-2efa0e564a13.png | close up portrait of one calico cat by vermeer. black background, three - point lighting, enchanting, realistic features, realistic proportions.                                                        | 1685    | 2007372353 | 50   | 7.0 | 8       |
| c3a21f1f-8651-4a58-a4d4-7500d97651dc.png | a bottle of jack daniels with the word medicare replacing the word jack daniels                                                                                                                         | 243     | 1617291079 | 50   | 7.0 | 8       |

To save space, we use an integer to encode the `sampler` in the table above.

|Sampler|Integer Value|
|:--|--:|
|ddim|1|
|plms|2|
|k_euler|3|
|k_euler_ancestral|4|
|ddik_heunm|5|
|k_dpm_2|6|
|k_dpm_2_ancestral|7|
|k_lms|8|
|others|9|

## Loading DiffusionDB

DiffusionDB is large (1.6TB)! However, with our modularized file structure, you can easily load a desirable number of images and their prompts and hyperparameters. In the [`example-loading.ipynb`](https://github.com/poloclub/diffusiondb/blob/main/notebooks/example-loading.ipynb) notebook, we demonstrate three methods to load a subset of DiffusionDB. Below is a short summary.

### Method 1: Use Hugging Face Datasets Loader

You can use the Hugging Face [`Datasets`](https://huggingface.co/docs/datasets/quickstart) library to easily load prompts and images from DiffusionDB. We pre-defined 16 DiffusionDB subsets (configurations) based on the number of instances. You can see all subsets in the [Dataset Preview](https://huggingface.co/datasets/poloclub/diffusiondb/viewer/all/train).

```python
import numpy as np
from datasets import load_dataset

# Load the dataset with the `random_1k` subset
dataset = load_dataset('poloclub/diffusiondb', 'random_1k')
```

### Method 2. Use a downloader script

This repo includes a Python downloader [`download.py`](https://github.com/poloclub/diffusiondb/blob/main/scripts/download.py) that allows you to download and load DiffusionDB. You can use it from your command line. Below is an example of loading a subset of DiffusionDB.

#### Usage/Examples

The script is run using command-line arguments as follows:

- `-i` `--index` - File to download or lower bound of a range of files if `-r` is also set.
- `-r` `--range` - Upper bound of range of files to download if `-i` is set.
- `-o` `--output` - Name of custom output directory. Defaults to the current directory if not set.
- `-z` `--unzip` - Unzip the file/files after downloading

##### Downloading a single file

The specific file to download is supplied as the number at the end of the file on HuggingFace. The script will automatically pad the number out and generate the URL.

```bash
python download.py -i 23
```

##### Downloading a range of files

The upper and lower bounds of the set of files to download are set by the `-i` and `-r` flags respectively.

```bash
python download.py -i 1 -r 2000
```

Note that this range will download the entire dataset. The script will ask you to confirm that you have 1.7Tb free at the download destination.

##### Downloading to a specific directory

The script will default to the location of the dataset's `part` .zip files at `images/`. If you wish to move the download location, you should move these files as well or use a symbolic link.

```bash
python download.py -i 1 -r 2000 -o /home/$USER/datahoarding/etc
```

Again, the script will automatically add the `/` between the directory and the file when it downloads.

##### Setting the files to unzip once they've been downloaded

The script is set to unzip the files _after_ all files have downloaded as both can be lengthy processes in certain circumstances.

```bash
python download.py -i 1 -r 2000 -z
```

### Method 3. Use `metadata.parquet` (Text Only)

If your task does not require images, then you can easily access all 2 million prompts and hyperparameters in the `metadata.parquet` table.

```python
from urllib.request import urlretrieve
import pandas as pd

# Download the parquet table
table_url = f'https://huggingface.co/datasets/poloclub/diffusiondb/resolve/main/metadata.parquet'
urlretrieve(table_url, 'metadata.parquet')

# Read the table using Pandas
metadata_df = pd.read_parquet('metadata.parquet')
```

## Dataset Creation

We collected all images from the official Stable Diffusion Discord server. Please read our [research paper](https://arxiv.org/abs/2210.14896) for details. The code is included in [`./scripts/`](./scripts/).

## Data Removal

If you find any harmful images or prompts in DiffusionDB, you can use [this Google Form](https://forms.gle/GbYaSpRNYqxCafMZ9) to report them. Similarly, if you are a creator of an image included in this dataset, you can use the [same form](https://forms.gle/GbYaSpRNYqxCafMZ9) to let us know if you would like to remove your image from DiffusionDB. We will closely monitor this form and update DiffusionDB periodically.

## Credits

DiffusionDB is created by [Jay Wang](https://zijie/wang), [Evan Montoya](https://www.linkedin.com/in/evan-montoya-b252391b4/), [David Munechika](https://www.linkedin.com/in/dmunechika/), [Alex Yang](https://alexanderyang.me), [Ben Hoover](https://www.bhoov.com), [Polo Chau](https://faculty.cc.gatech.edu/~dchau/).

## Citation

```bibtex
@article{wangDiffusionDBLargescalePrompt2022,
  title = {{{DiffusionDB}}: {{A}} Large-Scale Prompt Gallery Dataset for Text-to-Image Generative Models},
  author = {Wang, Zijie J. and Montoya, Evan and Munechika, David and Yang, Haoyang and Hoover, Benjamin and Chau, Duen Horng},
  year = {2022},
  journal = {arXiv:2210.14896 [cs]},
  url = {https://arxiv.org/abs/2210.14896}
}
```

## Licensing

The DiffusionDB dataset is available under the [CC0 1.0 License](https://creativecommons.org/publicdomain/zero/1.0/).
The Python code in this repository is available under the [MIT License](./LICENSE).

## Contact

If you have any questions, feel free to [open an issue](https://github.com/poloclub/diffusiondb/issues/new) or contact [Jay Wang](https://zijie.wang).
