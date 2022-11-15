from bs4 import BeautifulSoup
from urllib.parse import unquote
from glob import glob
from os.path import exists, join, basename
from copy import deepcopy
from tqdm import tqdm
from json import load, dump
from multiprocessing import Pool
from collections import ChainMap
from datetime import datetime, timezone

import re
import os
import time
import pickle

import pandas as pd
import numpy as np


WORK_DIR = "/project/zwang3049/discord-log/"
TIMESTAMP_DIR = "/project/zwang3049/discord-log/timestamps-authors"
N_PROC = 36


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


def parse_bot_command(raw_command):
    """
    Parse meta data from a bot command.
    """

    metadata = {
        "p": "",
        "np": "",
        "se": "",
        "c": 7.0,
        "st": 50,
        "sa": "k_lms",
        "a": "",
        "w": 512,
        "h": 512,
    }

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

    # The discord bot only parses arguments after the quotation mark, we do the
    # same here. During scraping, we treat all unparsable args as error and skip
    # the images However, we have to fix it for parsing the width and height for
    # timestamps parsing
    args = re.search(r".*\".*\"(.*)", command).group(1)

    # Parse the width
    if "-W " in args:
        try:
            metadata["w"] = int(re.search(r".*-W\s(.*?)(\s|$).*", args).group(1))
        except ValueError:
            pass

    if "--width " in args:
        try:
            metadata["w"] = int(re.search(r".*--width\s(.*?)(\s|$).*", args).group(1))
        except ValueError:
            pass

    # Parse the height
    if "-H " in args:
        try:
            metadata["h"] = int(re.search(r".*-H\s(.*?)(\s|$).*", args).group(1))
        except ValueError:
            pass

    if "--height " in args:
        try:
            metadata["h"] = int(re.search(r".*--height\s(.*?)(\s|$).*", args).group(1))
        except ValueError:
            pass

    return metadata


def get_utc_datetime(time_str):
    """
    Parse message date time to Python UTC datetime object.
    """
    parsed_time = datetime.strptime(time_str, "%d-%b-%y %I:%M %p")
    return datetime.fromtimestamp(parsed_time.timestamp(), tz=timezone.utc)


def update_timestamp_map(
    chanel_timestamp_map,
    chanel_timestamp_collisions,
    prompt,
    seed,
    cfg,
    step,
    sampler,
    width,
    height,
    author,
    timestamp,
):
    """
    Update the timestamp dictionary. Return collision count.
    """
    collision_count = 0
    # Make all key elements string to avoid float('nan') != float('nan') weirdness
    cur_key = (
        prompt,
        str(seed),
        str(cfg),
        str(step),
        str(sampler),
        str(width),
        str(height),
    )

    if cur_key in chanel_timestamp_map:
        # Collision: add the timestamp to a different map
        collision_count += 1
        if cur_key in chanel_timestamp_collisions:
            chanel_timestamp_collisions[cur_key].append((timestamp, author))
        else:
            # Add the old and new timestamps
            chanel_timestamp_collisions[cur_key] = [
                chanel_timestamp_map[cur_key],
                (timestamp, author),
            ]
    else:
        chanel_timestamp_map[cur_key] = (timestamp, author)

    return collision_count


def scrape_one_html(
    channel, cur_file_i, chanel_timestamp_map, chanel_timestamp_collisions
):
    """
    Scrape prompts and grid images from one html chunk file.
    """

    HTML_DIR = join(WORK_DIR, f"{channel}-htmls")
    cur_html = join(HTML_DIR, f"{channel}-{cur_file_i:03}.html")

    # Identify the image names
    with open(cur_html, "r", encoding="utf8") as fp:
        soup = BeautifulSoup(fp, "html.parser")

    error_count = 0
    collision_count = 0

    for message_group in soup.find_all(
        "div", attrs={"class", "chatlog__message-group"}
    ):
        author_tag = message_group.find("span", attrs={"class", "chatlog__author"})

        if author_tag is None:
            error_count += 1
            break

        # Parse timestamp in UTC
        timestamp_tag = message_group.find(
            "span", attrs={"class", "chatlog__timestamp"}
        ).find("a")
        timestamp = get_utc_datetime(timestamp_tag.text)

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
                        except IndexError as error:
                            # Sometimes the bot only generates 2/3 out of 4 images
                            # Skip these cases
                            # print(error)
                            error_count += 1
                            break

                    # Get the image path
                    try:
                        image_path = image_attachments[0].find("img")["src"]
                        image_path = unquote(image_path)
                    except (AttributeError, ValueError, TypeError) as error:
                        # print(error)
                        error_count += 1
                        break

                    # Extract meta data
                    try:
                        metadata = parse_bot_command(raw_command)
                    except (AttributeError, ValueError, TypeError) as error:
                        # print(error)
                        error_count += 1
                        break

                    # Parse timestamp
                    # Two cases for handling the local meta data
                    # Case 1, seeds are given
                    if len(seeds) == image_count:
                        for i in range(image_count):
                            prompt = metadata["p"]
                            seed = seeds[i]
                            cfg = metadata["c"]
                            step = metadata["st"]
                            sampler = metadata["sa"]
                            width = metadata["w"]
                            height = metadata["h"]
                            author = artist_name
                            collision_count += update_timestamp_map(
                                chanel_timestamp_map,
                                chanel_timestamp_collisions,
                                prompt,
                                seed,
                                cfg,
                                step,
                                sampler,
                                width,
                                height,
                                author,
                                timestamp,
                            )

                    # Case 2: individual commands are given
                    elif len(individual_commands) == image_count:
                        try:
                            for i in range(image_count):
                                local_metadata = parse_bot_command(
                                    individual_commands[i]
                                )
                                prompt = local_metadata["p"]
                                seed = local_metadata["se"]
                                cfg = local_metadata["c"]
                                step = local_metadata["st"]
                                sampler = local_metadata["sa"]
                                width = local_metadata["w"]
                                height = local_metadata["h"]
                                author = artist_name
                                collision_count += update_timestamp_map(
                                    chanel_timestamp_map,
                                    chanel_timestamp_collisions,
                                    prompt,
                                    seed,
                                    cfg,
                                    step,
                                    sampler,
                                    width,
                                    height,
                                    author,
                                    timestamp,
                                )
                        except (AttributeError, ValueError, TypeError) as error:
                            # print(error)
                            error_count += 1

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
                    except (AttributeError, ValueError, TypeError) as error:
                        # print(error)
                        error_count += 1
                        break

                    metadata["a"] = artist_name

                    if len(image_attachments) == 1:
                        # Update the timestamp map
                        prompt = metadata["p"]
                        seed = metadata["se"]
                        cfg = metadata["c"]
                        step = metadata["st"]
                        sampler = metadata["sa"]
                        width = metadata["w"]
                        height = metadata["h"]
                        author = artist_name
                        collision_count += update_timestamp_map(
                            chanel_timestamp_map,
                            chanel_timestamp_collisions,
                            prompt,
                            seed,
                            cfg,
                            step,
                            sampler,
                            width,
                            height,
                            author,
                            timestamp,
                        )
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
                            except IndexError as error:
                                # Sometimes the bot only generates 2/3 out of 4 images
                                # Skip these cases
                                # print(error)
                                error_count += 1
                                break

                        # Parse timestamp
                        # Two cases for handling the local meta data
                        # Case 1, seeds are given
                        if len(seeds) == len(image_attachments):
                            for i, _ in enumerate(image_attachments):
                                prompt = metadata["p"]
                                seed = seeds[i]
                                cfg = metadata["c"]
                                step = metadata["st"]
                                sampler = metadata["sa"]
                                width = metadata["w"]
                                height = metadata["h"]
                                author = artist_name
                                collision_count += update_timestamp_map(
                                    chanel_timestamp_map,
                                    chanel_timestamp_collisions,
                                    prompt,
                                    seed,
                                    cfg,
                                    step,
                                    sampler,
                                    width,
                                    height,
                                    author,
                                    timestamp,
                                )

                        # Case 2: individual commands are given
                        elif len(individual_commands) == len(image_attachments):
                            try:
                                for i, _ in enumerate(image_attachments):
                                    local_metadata = parse_bot_command(
                                        individual_commands[i]
                                    )
                                    prompt = local_metadata["p"]
                                    seed = local_metadata["se"]
                                    cfg = local_metadata["c"]
                                    step = local_metadata["st"]
                                    sampler = local_metadata["sa"]
                                    width = local_metadata["w"]
                                    height = local_metadata["h"]
                                    author = artist_name
                                    collision_count += update_timestamp_map(
                                        chanel_timestamp_map,
                                        chanel_timestamp_collisions,
                                        prompt,
                                        seed,
                                        cfg,
                                        step,
                                        sampler,
                                        width,
                                        height,
                                        author,
                                        timestamp,
                                    )
                            except (AttributeError, ValueError, TypeError) as error:
                                # print(error)
                                error_count += 1

                        break

                    else:
                        # Attachment is empty
                        error_count += 1
                        break

                # ASCII mode
                else:
                    error_count += 1
                    break

    return collision_count


def scrape_one_channel(channel):
    """
    Scrape the timestamps from one channel.
    """

    # Dictionary to keep track of the timestamp mappings
    chanel_timestamp_map = {}
    chanel_timestamp_collisions = {}
    collision_count = 0

    HTML_DIR = join(WORK_DIR, f"{channel}-htmls")
    chunk_count = len(glob(join(HTML_DIR, "*.html")))
    for i in range(1, chunk_count + 1):
        collision_count += scrape_one_html(
            channel, i, chanel_timestamp_map, chanel_timestamp_collisions
        )

    # Save the dictionaries
    pickle.dump(
        chanel_timestamp_map,
        open(join(TIMESTAMP_DIR, f"{channel}-timestamp.pkl"), "wb"),
    )
    pickle.dump(
        chanel_timestamp_collisions,
        open(join(TIMESTAMP_DIR, f"{channel}-timestamp-collision.pkl"), "wb"),
    )

    return collision_count


def main():
    """
    Main function
    """
    start_time = time.time()
    channels = []
    for i in range(1, 51):
        channels.append(f"dream-{i}")

    # Scrape channels in parallel
    with Pool(N_PROC) as p:
        collision_counts = list(
            tqdm(p.imap(scrape_one_channel, channels), total=len(channels))
        )

    print("Total collisions", np.sum(collision_counts))
    print("Finished in", (time.time() - start_time) / 60, "minutes")


if __name__ == "__main__":
    main()
