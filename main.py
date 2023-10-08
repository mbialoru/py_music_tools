import mutagen
import logging
import sys
import argparse
import time
import pprint
import glob
import re

from functools import wraps
from collections import namedtuple
from pathlib import Path
from unidecode import unidecode
from attrs import define, field, validators

logger = logging.getLogger(__name__)


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


def chrono(method):
    """Report execution time in miliseconds of wrapped function."""
    @wraps(method)
    def wrapped(*args, **kwargs):
        startTime = time.time_ns()
        result = method(*args, **kwargs)
        finishTime = round((time.time_ns() - startTime) / 1000000, 8)
        logger.debug(f"CHRONO {method.__name__}() {finishTime} ms")
        return result
    return wrapped


def id3_tag_to_str(tag: list) -> str:
    return " ".join(tag)


def to_snake_case(string: str):
    """convert given string to snake_case"""
    return re.sub("__+", "_", re.sub(r"(?<=[a-z])(?=[A-Z])|[^a-zA-Z0-9]", "_", string).strip("_").lower())


def get_key_with_fallback(file: mutagen.File, key: str, fallback = ""):
    try:
        return file[key]
    except KeyError:
        logger.error(f"key {key} not found")
        logger.info(f"using fallback value {fallback}")
        return fallback


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


def create_musicsong_object(file: Path):
    # for mp3 with id3 files we can use better API
    if isinstance(mutagen.File(file), mutagen.mp3.MP3):
        audio = mutagen.mp3.MP3(file, ID3 = mutagen.easyid3.EasyID3)
    else:
        logger.info(f"{file} is not a mp3 format file")
        audio = mutagen.File(file)
    return MusicSong(file, get_key_with_fallback(audio, "artist"), get_key_with_fallback(audio, "album"), get_key_with_fallback(audio, "title"))


def get_statistics(musicsong_object_list):
    """ yes, this function does have a side effect - I know """
    artist_list = []
    album_list = []
    title_list = []

    stats = Stats()

    for item in musicsong_object_list:
        if item.artist == "Unknown":
            stats.unknown_artists += 1
        elif item.artist not in artist_list:
            artist_list.append(item.artist)
        if item.artist_ascii == "Empty":
            stats.empty_artists += 1
        
        if item.album == "Unknown":
            stat.sunknown_albums += 1
        elif item.album not in album_list:
            album_list.append(item.album)
        if item.album_ascii == "Empty":
            stats.empty_albums += 1
        
        if item.title == "Unknown":
            stats.unknown_titles += 1
            item.title += str(unknown_titles) # prevent overwriting unknown titles
        elif item.title not in title_list:
            title_list.append(item.title)
        if item.title_ascii == "Empty":
            stats.empty_titles += 1
            item.title += str(empty_titles) # prevent overwriting empty asciified titles

    stats.artists = len(artist_list)
    stats.albums = len(album_list)
    stats.titles = len(title_list)

    return stats


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


def build_directory_tree(musicsong_object_list, target_dir):
    artist_dirs = 0
    album_dirs = 0

    for item in music_file_paths:
        artist_dir = target_dir / to_snake_case(item.artist_ascii)
        album_dir = artist_dir / to_snake_case(item.album_ascii)
        if not artist_dir.exists():
            logger.debug(f"creating artist directory {to_snake_case(item.artist_ascii)}")
            artist_dir.mkdir()
            artist_dirs += 1
        if not album_dir.exists():
            logger.debug(f"creating album directory {to_snake_case(item.album_ascii)}")
            album_dir.mkdir()
            album_dirs += 1

    logger.debug(f"created {artist_dirs} artist directories")
    logger.debug(f"created {album_dirs} album directories")
    logger.debug(f"created {artist_dirs + album_dirs} total directories")


Stats = namedtuple("Stats", ["artists", "albums", "titles", "unknown_artists", "unknown_albums",
                    "unknown_titles", "empty_artists", "empty_albums", "empty_titles"],
                    defaults=[0,0,0,0,0,0,0,0,0])


@define
class MusicSong:
    file_path: Path = field()

    artist: str = field(converter=id3_tag_to_str)
    album: str = field(converter=id3_tag_to_str)
    title: str = field(converter=id3_tag_to_str)

    artist_ascii:str = field(init=False)
    album_ascii:str = field(init=False)
    title_ascii:str = field(init=False)

    @artist.default
    def _artist_unknown(self):
        if not self.artist or self.artist == "":
            logger.warning("empty artist, setting to Unknown")
            return "Unknown"

    @album.default
    def _album_unknown(self):
        if not self.album or self.album == "":
            logger.warning("empty album, setting to Unknown")
            return "Unknown"

    @title.default
    def _title_default(self):
        if not self.title or self.title == "":
            logger.warning("empty title, setting to Unknown")
            return "Unknown"
    
    @artist_ascii.default
    def _artist_ascii_default(self):
        if not (artist_ascii := unidecode(self.artist)):
            logger.warning("unidecode returned empty string")
            return "Empty"
        return artist_ascii

    @album_ascii.default
    def _album_ascii_default(self):
        if not (album_ascii := unidecode(self.album)):
            logger.warning("unidecode returned empty string")
            return "Empty"
        return album_ascii

    @title_ascii.default
    def _title_ascii_default(self):
        if not (title_ascii := unidecode(self.title)):
            logger.warning("unidecode returned empty string")
            return "Empty"
        return title_ascii

    @property
    def path(self) -> Path:
        result = Path('.')
        result /= to_snake_case(self.artist_ascii)
        result /= to_snake_case(self.album_ascii)
        result /= to_snake_case(self.title_ascii)
        return result


# shamelessly stolen from https://stackoverflow.com/questions/9727673/list-directory-tree-structure-in-python
class DisplayablePath(object):
    display_filename_prefix_middle = '├──'
    display_filename_prefix_last = '└──'
    display_parent_prefix_middle = '    '
    display_parent_prefix_last = '│   '

    def __init__(self, path, parent_path, is_last):
        self.path = Path(str(path))
        self.parent = parent_path
        self.is_last = is_last
        if self.parent:
            self.depth = self.parent.depth + 1
        else:
            self.depth = 0

    @property
    def displayname(self):
        if self.path.is_dir():
            return self.path.name + '/'
        return self.path.name

    @classmethod
    def make_tree(cls, root, parent=None, is_last=False, criteria=None):
        root = Path(str(root))
        criteria = criteria or cls._default_criteria

        displayable_root = cls(root, parent, is_last)
        yield displayable_root

        children = sorted(list(path
                               for path in root.iterdir()
                               if criteria(path)),
                          key=lambda s: str(s).lower())
        count = 1
        for path in children:
            is_last = count == len(children)
            if path.is_dir():
                yield from cls.make_tree(path,
                                         parent=displayable_root,
                                         is_last=is_last,
                                         criteria=criteria)
            else:
                yield cls(path, displayable_root, is_last)
            count += 1

    @classmethod
    def _default_criteria(cls, path):
        return True

    @property
    def displayname(self):
        if self.path.is_dir():
            return self.path.name + '/'
        return self.path.name

    def displayable(self):
        if self.parent is None:
            return self.displayname

        _filename_prefix = (self.display_filename_prefix_last
                            if self.is_last
                            else self.display_filename_prefix_middle)

        parts = ['{!s} {!s}'.format(_filename_prefix,
                                    self.displayname)]

        parent = self.parent
        while parent and parent.parent is not None:
            parts.append(self.display_parent_prefix_middle
                         if parent.is_last
                         else self.display_parent_prefix_last)
            parent = parent.parent

        return ''.join(reversed(parts))

@chrono
def main(argv: argparse.Namespace):
    music_file_paths = get_music_files_list(argv.scan_dir)
    musicsong_object_list = [create_musicsong_object(path) for path in music_file_paths]
    stats = get_statistics(musicsong_object_list)
    logger.info(f"Artists: {stats.artists}")
    logger.info(f"Albums: {stats.albums}")
    logger.info(f"Titles: {stats.titles}")
    build_directory_tree(musicsong_object_list, argv.target_dir)

    logger.debug(f"directory tree")
    tree = DisplayablePath.make_tree(argv.target_dir)
    for item in tree:
        logger.debug(item.displayable())

    # data_dictionary = build_data_dictionary(music_file_paths)
    # move_files_to_folders(data_dictionary, argv.target_dir)

if __name__ == "__main__":
    argv = setup_argv()
    setup_logger(argv.debug)
    sys.exit(main(argv) or 0)
