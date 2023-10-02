import mutagen
import logging
import sys
import argparse
import time
import pprint
import glob
import re

from functools import wraps
from pathlib import Path
from unidecode import unidecode
from attrs import define, field, validators

logger = logging.getLogger(__name__)

def is_not_empty(string: str):
    if string == "":
        logger.warning("empty string received")
        return "Unknown"
    return string

@define
class MusicSong:
    artist: str
    album: str
    title: str

    artist_ascii:str = field(init=false)
    album_ascii:str = field(init=false)
    title_ascii:str = field(init=false)

    def __attrs_post_init__(self):
        self.artist = is_not_empty(self.artist)
        self.album = is_not_empty(self.album)
        self.title = is_not_empty(self.title)
        self.artist_ascii = unidecode_with_fallback(self.artist, "Empty")
        self.album_ascii = unidecode_with_fallback(self.album, "Empty")
        self.title_ascii = unidecode_with_fallback(self.title, "Empty")

    @property
    def path(self) -> Path:
        result = Path()
        result / to_snake_case(self.artist_ascii)
        result / to_snake_case(self.album_ascii)
        result / to_snake_case(self.title)
        return result


def setup_logger(debug: bool = False):
    log_format = "%(levelname)-8s %(message)s"
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format=log_format, stream = sys.stdout)


class convert_to_pathlib(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, Path(values))


def setup_argv() -> argparse.Namespace:
    """Create argparse namespace object - ARGV style."""
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("scan_dir", help="directory to scan", type=Path, action=convert_to_pathlib)
    parser.add_argument("target_dir", help="directory where to deposit files", type=Path, action=convert_to_pathlib)
    parser.add_argument("-v", help="increase verbosity", action="count")
    parser.add_argument("--debug", help="Debug logging", action="store_true")
    return parser.parse_args()


def unidecode_with_fallback(string: str, fallback: str):
    result = unidecode(string)
    if not result:
        logger.warning(f"unidecode returned empty string for {string}")
        logger.info(f"using fallback value {fallback}")
        return fallback
    return result


def to_snake_case(string: str):
    """convert given string to snake_case"""
    return re.sub("__+", "_", re.sub(r"(?<=[a-z])(?=[A-Z])|[^a-zA-Z0-9]", "_", string).strip("_").lower())


def chrono(method):
    """Report execution time in miliseconds of wrapped function."""
    @wraps(method)
    def wrapped(*args, **kwarg/s):
        startTime = time.time_ns()
        result = method(*args, **kwargs)
        finishTime = round((time.time_ns() - startTime) / 1000000, 8)
        logger.debug(f"CHRONO {method.__name__}() {finishTime} ms")
        return result
    return wrapped


@chrono
def get_music_files_list(directory: Path):
    """recursively search given directory for valid music files"""
    valid_files_list = []
    
    for item in directory.rglob("*"):
        if item.is_file():
            try:
                if(isinstance(mutagen.File(str(item.resolve())), mutagen.FileType)):
                    valid_files_list.append(item.resolve())
                else:
                    logger.warning(f"non music file type for {item}")
            except Exception as e:
                logger.error(f"error when reading file {item}")
                raise e
    logger.info(f"found {len(valid_files_list)} music files in {directory}")
    return valid_files_list


def get_key_with_fallback(file: mutagen.File, key: str, fallback = ""):
    try:
        return file[key]
    except KeyError:
        logger.error(f"key {key} not found")
        logger.info(f"using fallback value {fallback}")
        return fallback


def create_musicsong_object(file: Path):
    # for mp3 with id3 files we can use better API
    if isinstance(mutagen.File(file), mutagen.mp3.MP3):
        file = mutagen.mp3.MP3(file, ID3 = mutagen.easyid3.EasyID3)
    else:
        logger.warning(f"{file} is not mp3 format file")
        file = mutagen.File(file)

    artist = " ".join(get_key_with_fallback(file, "artist"))
    album = " ".join(get_key_with_fallback(file, "album"))
    title = " ".join(get_key_with_fallback(file, "title"))

    return MusicSong(artist, album, title)


def build_data_dictionary(file_list):
    data = {}

    artist_count = 0
    album_count = 0
    title_count = 0

    artist_unknown_count = 0
    album_unknown_count = 0
    title_unknown_count = 0

    for file in file_list:
        artist, album, title = extract_metadata(file)

        if artist not in data.keys():
            logger.debug(f"new artist {artist}")
            data[artist] = {}
            artist_count += 1
        
        if album not in data[artist].keys():
            logger.debug(f"new album {album} of {artist}")
            data[artist][album] = []
            album_count += 1

        if title not in data[artist][album]:
            logger.debug(f"adding {file}")
            data[artist][album].append((title, file))
            title_count += 1

        if artist == "Unknown":
            logger.debug(f"unknown artist for {file}")
            artist_unknown_count += 1
        if album == "Unknown":
            logger.debug(f"unknown album for {file}")
            album_unknown_count += 1
        if title == "Unknown":
            logger.debug(f"unknown title for {file}")
            title_unknown_count += 1

    logger.info(f"{artist_count} artists")
    logger.info(f"{album_count} albums")
    logger.info(f"{title_count} titles")

    logger.info(f"{artist_unknown_count} unknown artists")
    logger.info(f"{album_unknown_count} unknown albums")
    logger.info(f"{title_unknown_count} unknown titles")

    return data

def move_files_to_folders(data_dictionary: dict, target_dir: Path):
    for artist in data_dictionary.keys():
        artist_dir = target_dir / to_snake_case(artist)
        if not artist_dir.exists():
            logger.debug(f"creating artist directory {artist_dir}")
            artist_dir.mkdir()
        for album in data_dictionary[artist]:
            album_dir = artist_dir / to_snake_case(album)
            if not album_dir.exists():
                logger.debug(f"creating album directory {album_dir}")
                album_dir.mkdir()
            unknown_titles = 0
            for title, file in data_dictionary[artist][album]:
                if title == "Unknown":
                    title = title + str(unknown_titles)
                    unknown_titles += 1
                file_dir = album_dir / (to_snake_case(title) + str(file.suffix))
                logger.debug(f"moving {file.name} to {file_dir}")
                file.rename(file_dir)

@chrono
def main(argv: argparse.Namespace):
    music_file_paths = get_music_files_list(argv.scan_dir)
    data_dictionary = build_data_dictionary(music_file_paths)
    move_files_to_folders(data_dictionary, argv.target_dir)

if __name__ == "__main__":
    argv = setup_argv()
    setup_logger(argv.debug)
    sys.exit(main(argv) or 0)
