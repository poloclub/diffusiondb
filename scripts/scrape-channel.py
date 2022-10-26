from bs4 import BeautifulSoup
from urllib.parse import unquote
from glob import glob
from os.path import exists, join, basename
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from copy import deepcopy
from tqdm import tqdm
from json import load, dump
from multiprocessing import Pool
from collections import ChainMap
from sys import argv

import re
import os
import uuid
import shutil
import time
import random
import PIL


# Change WORK_DIR to where the chat logs are stored
WORK_DIR = "/project/zwang3049/prompt/"
N_PROC = 36
CHANNEL = ""

if len(argv) > 1:
    CHANNEL = argv[1]

IMAGE_DIR = join(WORK_DIR, f"{CHANNEL}")
HTML_DIR = join(WORK_DIR, f"{CHANNEL}-htmls")
PROCESSED_DIR = join(WORK_DIR, f"{CHANNEL}-processed")
UNIQUE_PROMPT = True
COPY_FILE = True

if not exists(HTML_DIR):
    os.makedirs(HTML_DIR)

if not exists(PROCESSED_DIR):
    os.makedirs(PROCESSED_DIR)


def split_html():
    """
    Split the html file into k files, where each file has 1k lines
    (~1.7mb per file)
    """
    with open(join(WORK_DIR, f"{CHANNEL}.html"), "r", encoding="utf8") as fp:
        line_count = 0
        line_per_file = 1000
        chunk_count = 1
        cur_chunk = ""

        for line in fp:
            cur_chunk += line
            line_count += 1

            if line_count == line_per_file:
                with open(
                    join(HTML_DIR, f"{CHANNEL}-{chunk_count:03}.html"),
                    "w",
                    encoding="utf8",
                ) as wfp:
                    wfp.write(cur_chunk)
                    line_count = 0
                    chunk_count += 1
                    cur_chunk = ""

        # Save the last file
        if cur_chunk != "":
            with open(
                join(HTML_DIR, f"{CHANNEL}-{chunk_count:03}.html"), "w", encoding="utf8"
            ) as wfp:
                wfp.write(cur_chunk)
            return chunk_count
        else:
            return chunk_count - 1


def parse_bot_command(raw_command):
    """
    Parse meta data from a bot command.
    """

    metadata = {"p": "", "np": "", "se": "", "c": 7.0, "st": 50, "sa": "k_lms", "a": ""}

    command = raw_command.replace("\n", " ")

    # Parse prompt
    metadata["p"] = re.search(r".*\"(.*)\".*", command).group(1)

    # Parse CFG scale
    if "-C " in command:
        metadata["c"] = float(re.search(r".*-C\s(.*?)(\s|$).*", command).group(1))

    if "--cfg_scale " in command:
        metadata["c"] = float(
            re.search(r".*--cfg_scale\s(.*?)(\s|$).*", command).group(1)
        )

    # Parse the sampler
    if "-A " in command:
        metadata["sa"] = re.search(r".*-A\s(.*?)(\s|$).*", command).group(1)

    if "--sampler " in command:
        metadata["sa"] = re.search(r".*--sampler\s(.*?)(\s|$).*", command).group(1)

    # Parse the step
    if "-s " in command:
        metadata["st"] = int(re.search(r".*-s\s(.*?)(\s|$).*", command).group(1))

    if "--steps " in command:
        metadata["st"] = int(re.search(r".*--steps\s(.*?)(\s|$).*", command).group(1))

    # Parse the seed
    if "-S " in command:
        metadata["se"] = int(re.search(r".*-S\s(.*?)(\s|$).*", command).group(1))

    if "--seed " in command:
        metadata["se"] = int(re.search(r".*--seed\s(.*?)(\s|$).*", command).group(1))

    return metadata


def split_image(
    image_real_path,
    image_count,
    artist_name,
    metadata,
    image_index,
    seeds,
    individual_commands,
    only_keep_one,
):
    """Split the grid image into four images. Save each image with prompt and seed
    as metadata. Add each image into the image_index.

    Args:
        image_real_path (string): Image global path
        image_count (int): Number of images
        artist_name (string): Artist username
        metadata (dict): Metadata
        image_index (dict): Global image index
        seeds ([string]): A list of seeds
        individual_commands ([string]): A list of commands
        only_keep_one (bool): True if only extract a random image in the collage
    """

    if len(seeds) != image_count and len(individual_commands) != image_count:
        print("Error: missing seeds and individual_commands")
        return

    try:
        img = Image.open(image_real_path)
    except PIL.UnidentifiedImageError:
        print("Error: PIL.UnidentifiedImageError")
        return

    width, height = img.size

    if image_count == 2:
        new_width = width // 2
        coords = [[0, 0, new_width, height], [new_width, 0, width, height]]

    elif image_count == 3:
        new_width = width // 3
        coords = [
            [0, 0, new_width, height],
            [new_width, 0, new_width * 2, height],
            [new_width * 2, 0, new_width * 3, height],
        ]

    elif image_count == 4:
        new_width, new_height = width // 2, height // 2
        coords = [
            [0, 0, new_width, new_height],
            [new_width, 0, width, new_height],
            [0, new_height, new_width, height],
            [new_width, new_height, width, height],
        ]

    elif image_count == 6:
        new_width, new_height = width // 3, height // 2
        coords = [
            [0, 0, new_width, new_height],
            [new_width, 0, new_width * 2, new_height],
            [new_width * 2, 0, new_width * 3, new_height],
            [0, new_height, new_width, new_height * 2],
            [new_width, new_height, new_width * 2, new_height * 2],
            [new_width * 2, new_height, new_width * 3, new_height * 2],
        ]

    elif image_count == 8:
        new_width, new_height = width // 4, height // 2
        coords = [
            [0, 0, new_width, new_height],
            [new_width, 0, new_width * 2, new_height],
            [new_width * 2, 0, new_width * 3, new_height],
            [new_width * 3, 0, new_width * 4, new_height],
            [0, new_height, new_width, new_height * 2],
            [new_width, new_height, new_width * 2, new_height * 2],
            [new_width * 2, new_height, new_width * 3, new_height * 2],
            [new_width * 3, new_height, new_width * 4, new_height * 2],
        ]

    elif image_count == 9:
        new_width, new_height = width // 3, height // 3
        coords = [
            [0, 0, new_width, new_height],
            [new_width, 0, new_width * 2, new_height],
            [new_width * 2, 0, new_width * 3, new_height],
            [0, new_height, new_width, new_height * 2],
            [new_width, new_height, new_width * 2, new_height * 2],
            [new_width * 2, new_height, new_width * 3, new_height * 2],
            [0, new_height * 2, new_width, new_height * 3],
            [new_width, new_height * 2, new_width * 2, new_height * 3],
            [new_width * 2, new_height * 2, new_width * 3, new_height * 3],
        ]

    def process_one_coord(i, coord):
        """Save one image using one coordinate.

        Args:
            i (int): Index
            coord ([int]): Coordinate
        """
        image_name = f"{str(uuid.uuid4())}.png"
        new_image_path = join(PROCESSED_DIR, image_name)
        new_image = img.crop(coord)

        # Two cases for handling the local meta data
        # Case 1, seeds are given
        if len(seeds) == image_count:
            local_metadata = deepcopy(metadata)
            local_metadata["se"] = seeds[i]
            local_metadata["a"] = artist_name

        # Case 2: individual commands are given
        elif len(individual_commands) == image_count:
            try:
                local_metadata = parse_bot_command(individual_commands[i])
                local_metadata["a"] = artist_name
            except (AttributeError, ValueError, TypeError):
                return

        # Add metadata
        png_info = PngInfo()
        png_info.add_text("prompt", local_metadata["p"])
        png_info.add_text("seed", str(local_metadata["se"]))

        # Save to the new path
        new_image.save(new_image_path, pnginfo=png_info)

        # Add image to the image_index
        image_index[image_name] = local_metadata

    if only_keep_one:
        # Choose a random coordinate to process
        random_i = random.choice(range(len(coords)))
        process_one_coord(random_i, coords[random_i])
    else:
        # Process all coordinates
        for i, coord in enumerate(coords):
            process_one_coord(i, coord)


def copy_one_image(image_attachments, metadata, image_index):
    """
    Copy one image to the processed directory.
    """

    # Get the image path
    try:
        image_path = image_attachments[0].find("img")["src"]
        image_path = unquote(image_path)
    except (AttributeError, ValueError, TypeError):
        return

    image_basename = basename(image_path)
    image_real_path = join(IMAGE_DIR, image_basename)

    image_name = f"{str(uuid.uuid4())}.png"
    new_image_path = join(PROCESSED_DIR, image_name)

    # Copy the image
    if COPY_FILE:
        shutil.copyfile(image_real_path, new_image_path)
    else:
        shutil.move(image_real_path, new_image_path)

    # Add image to the image_index
    image_index[image_name] = metadata


def copy_multiple_images(
    image_attachments,
    artist_name,
    metadata,
    image_index,
    seeds,
    individual_commands,
    only_keep_one,
):
    """Copy separate multiple images with different seeds.

    Args:
        image_attachments ([tag]): Image attachment tags
        artist_name (string): Artist name
        metadata (dict): Metadata
        image_index (dict): Global image index
        seeds ([string]): A list of seeds
        individual_commands ([string]): Individual commands
        only_keep_one (bool): True if only copy a random image of all images
            with the same prompt
    """
    if len(seeds) != len(image_attachments) and len(individual_commands) != len(
        image_attachments
    ):
        print("Error: missing seeds and individual_commands")
        return

    def process_one_image(i, image_tag):
        # Get the image path
        try:
            image_path = image_tag.find("img")["src"]
            image_path = unquote(image_path)
        except (AttributeError, ValueError, TypeError):
            return

        image_basename = basename(image_path)
        image_real_path = join(IMAGE_DIR, image_basename)

        image_name = f"{str(uuid.uuid4())}.png"
        new_image_path = join(PROCESSED_DIR, image_name)

        # Two cases for handling the local meta data
        # Case 1, seeds are given
        if len(seeds) == len(image_attachments):
            local_metadata = deepcopy(metadata)
            local_metadata["se"] = seeds[i]
            local_metadata["a"] = artist_name

        # Case 2: individual commands are given
        elif len(individual_commands) == len(image_attachments):
            try:
                local_metadata = parse_bot_command(individual_commands[i])
                local_metadata["a"] = artist_name
            except (AttributeError, ValueError, TypeError):
                return

        # Copy the image
        if COPY_FILE:
            shutil.copyfile(image_real_path, new_image_path)
        else:
            shutil.move(image_real_path, new_image_path)

        # Add image to the image_index
        image_index[image_name] = local_metadata

    if only_keep_one:
        # Only save one random image
        random_i = random.choice(range(len(image_attachments)))
        process_one_image(random_i, image_attachments[random_i])
    else:
        # Save all images
        for i, image_tag in enumerate(image_attachments):
            process_one_image(i, image_tag)


def is_grid_mode(dream_command, message_group):
    """
    Check if this message has grid image.
    Return one of ['grid', 'non-grid', 'skip']
    """

    if "-g" in dream_command:
        if "-n " not in dream_command:
            return "non-grid"

        try:
            n_count = re.search(r".*-n\s(.*?)(\s|$).*", dream_command).group(1)
            n_count = int(n_count)
            if n_count not in [2, 3, 4, 6, 8, 9]:
                return "skip"
        except (AttributeError, ValueError, TypeError):
            return "skip"

        return "grid"

    if (
        "-n 2" in dream_command
        or "-n 3" in dream_command
        or "-n 4" in dream_command
        or "-n 6" in dream_command
        or "-n 8" in dream_command
        or "-n 9" in dream_command
    ):
        image_attachments = message_group.find_all(
            "div", attrs={"class", "chatlog__attachment"}
        )
        if len(image_attachments) == 1:
            return "grid"

    elif "-n " in dream_command:
        return "skip"

    # Skip the ascii mode
    if (
        "-a" in dream_command
        or "--ascii" in dream_command
        or "-ac" in dream_command
        or "--asciicols" in dream_command
    ):
        return "skip"

    return "non-grid"


def scrape_one_html(cur_file_i):
    """
    Scrape prompts and grid images from one html chunk file.
    """

    cur_html = join(HTML_DIR, f"{CHANNEL}-{cur_file_i:03}.html")

    # Identify the image names
    with open(cur_html, "r", encoding="utf8") as fp:
        soup = BeautifulSoup(fp, "html.parser")

    image_index = {}
    error_count = 0

    for message_group in soup.find_all(
        "div", attrs={"class", "chatlog__message-group"}
    ):
        author_tag = message_group.find("span", attrs={"class", "chatlog__author"})

        if author_tag is None:
            error_count += 1
            break

        # This message is posted by the stable diffusion bot
        if author_tag.text == "DreamBotMothership":

            # Find the artist username
            artist_tag = message_group.find(
                "div", attrs={"class", "chatlog__reference-author"}
            )
            artist_name = ""
            if artist_tag and artist_tag.has_attr("title"):
                artist_name = artist_tag["title"]

            # Parse the command
            inline_md_codes = message_group.find_all(
                "code",
                attrs={"class", "chatlog__markdown-pre chatlog__markdown-pre--inline"},
            )
            for code_i, inline_md_code in enumerate(inline_md_codes):

                if "!dream" not in inline_md_code.text:
                    continue

                # Check if it is grid mode
                message_mode = is_grid_mode(inline_md_code.text, message_group)
                if message_mode == "grid":

                    # Get the grid number. We only handle -n in [2, 3, 4, 6, 8, 9]
                    if "-n 2" in inline_md_code.text:
                        image_count = 2
                    elif "-n 3" in inline_md_code.text:
                        image_count = 3
                    elif "-n 4" in inline_md_code.text:
                        image_count = 4
                    elif "-n 6" in inline_md_code.text:
                        image_count = 6
                    elif "-n 8" in inline_md_code.text:
                        image_count = 8
                    elif "-n 9" in inline_md_code.text:
                        image_count = 9
                    else:
                        # Skip other cases
                        error_count += 1
                        break

                    # Check if we only have one image attachment
                    # It means this image is a collage image
                    image_attachments = message_group.find_all(
                        "div", attrs={"class", "chatlog__attachment"}
                    )
                    if len(image_attachments) != 1:
                        error_count += 1
                        break

                    raw_command = inline_md_code.text
                    raw_command = raw_command.replace("!dream", "")

                    # Need to parse the next text to get the exact seeds
                    seeds = []
                    individual_commands = []
                    next_line = inline_md_code.next_sibling

                    if next_line is None:
                        error_count += 1
                        break

                    if "The seeds for each individual image are" in next_line:
                        seeds = re.sub(r".*\[(.*)\].*", r"\1", next_line)
                        seeds = list(map(int, seeds.split(", ")))

                    # In newer messages, each command is iterated
                    elif "The commands for each individual image are" in next_line:
                        try:
                            for i in range(1, image_count + 1):
                                individual_commands.append(
                                    inline_md_codes[code_i + i].text
                                )
                        except IndexError:
                            # Sometimes the bot only generates 2/3 out of 4 images
                            # Skip these cases
                            error_count += 1
                            break

                    # Get the image path
                    try:
                        image_path = image_attachments[0].find("img")["src"]
                        image_path = unquote(image_path)
                    except (AttributeError, ValueError, TypeError):
                        error_count += 1
                        break

                    image_basename = basename(image_path)
                    image_real_path = join(IMAGE_DIR, image_basename)

                    # Extract meta data
                    try:
                        metadata = parse_bot_command(raw_command)
                    except (AttributeError, ValueError, TypeError):
                        error_count += 1
                        break

                    # Split, save, and index images
                    split_image(
                        image_real_path,
                        image_count,
                        artist_name,
                        metadata,
                        image_index,
                        seeds,
                        individual_commands,
                        UNIQUE_PROMPT,
                    )

                    break

                # Non-grid mode
                elif message_mode == "non-grid":
                    # Check number of image attachments
                    image_attachments = message_group.find_all(
                        "div", attrs={"class", "chatlog__attachment"}
                    )

                    raw_command = inline_md_code.text
                    raw_command = raw_command.replace("!dream", "")

                    # Extract meta data
                    try:
                        metadata = parse_bot_command(raw_command)
                    except (AttributeError, ValueError, TypeError):
                        error_count += 1
                        break

                    metadata["a"] = artist_name

                    if len(image_attachments) == 1:
                        copy_one_image(image_attachments, metadata, image_index)
                        break

                    elif len(image_attachments) > 1:
                        # Need to parse the next text to get the exact seeds
                        seeds = []
                        individual_commands = []
                        next_line = inline_md_code.next_sibling

                        if next_line is None:
                            error_count += 1
                            break

                        if "The seeds for each individual image are" in next_line:
                            seeds = re.search(r".*\[(.*)\].*", next_line).group(1)
                            seeds = list(map(int, seeds.split(", ")))

                        # In newer messages, each command is iterated
                        elif "The commands for each individual image are" in next_line:
                            try:
                                for i in range(1, image_count + 1):
                                    individual_commands.append(
                                        inline_md_codes[code_i + i].text
                                    )
                            except IndexError:
                                # Sometimes the bot only generates 2/3 out of 4 images
                                # Skip these cases
                                error_count += 1
                                break

                        copy_multiple_images(
                            image_attachments,
                            artist_name,
                            metadata,
                            image_index,
                            seeds,
                            individual_commands,
                            UNIQUE_PROMPT,
                        )
                        break

                    else:
                        # Attachment is empty
                        error_count += 1
                        break

                # ASCII mode
                else:
                    error_count += 1
                    break

    print("Parsing error count:", error_count)

    # Save the image index
    image_index_path = join(HTML_DIR, f"{CHANNEL}-{cur_file_i:03}.json")
    dump(image_index, open(image_index_path, "w", encoding="utf8"))
    return image_index


def main():
    """
    Main function
    """

    # Split the html file into chunks
    chunk_count = split_html()
    chunk_is = list(range(1, chunk_count + 1))
    start_time = time.time()

    # Scrape html files in parallel
    with Pool(N_PROC) as p:
        image_indexes = list(
            tqdm(p.imap(scrape_one_html, chunk_is), total=len(chunk_is))
        )

    # Join all image_indexes and save one json file
    flatten_image_indexes = dict(ChainMap(*image_indexes))
    flatten_image_indexes_path = join(WORK_DIR, f"{CHANNEL}-grid.json")
    dump(flatten_image_indexes, open(flatten_image_indexes_path, "w", encoding="utf8"))

    print("Finished in", (time.time() - start_time) / 60, "minutes")


if __name__ == "__main__":
    main()
