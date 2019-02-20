"""The Sonic API Object."""
import asyncio
import hashlib
import logging
import random
import string
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiofiles
import aiohttp

from aiosonic.errors import APIError
from aiosonic.types import QueryDict


@dataclass
class SonicAPI:
    """A SonicAPI object."""

    server: str
    username: str
    password: str
    logger: logging.Logger = logging.getLogger("SonicAPI")

    def _create_salt(self) -> str:
        """Creates random salt."""
        random_salt = "".join(
            random.SystemRandom().choice(string.ascii_uppercase + string.digits)
            for _ in range(10)
        )
        self.logger.debug("random salt: %s", random_salt)

        return random_salt

    def _create_md5(self, password) -> str:
        """Create MD5 sum from password."""
        md5_hash = hashlib.md5(password.encode("utf-8")).hexdigest()
        self.logger.debug("created md5 hash: %s", md5_hash)

        return md5_hash

    async def _create_token(self) -> Tuple[str, str]:
        """Create authentication token."""
        loop = asyncio.get_running_loop()
        salt = await loop.run_in_executor(None, self._create_salt)
        self.logger.debug("salt: %s", salt)
        token = await loop.run_in_executor(None, self._create_md5, self.password + salt)
        self.logger.debug("token: %s", token)

        return (salt, token)

    async def _create_url(self, endpoint: str, extra_query: QueryDict = None) -> str:
        salt, token = await self._create_token()
        query_dict: QueryDict = {
            "u": self.username,
            "t": token,
            "s": salt,
            "c": "aiosonic",
            "v": "1.15.0",
            "f": "json",
        }
        if extra_query:
            query_dict.update(extra_query)
        query = urlencode(query_dict)
        scheme, netloc, path, _, fragment = urlsplit(self.server)
        if path and path[-1] == "/":
            path = path[:-1]
        path = path + "/rest" + endpoint
        url = urlunsplit((scheme, netloc, path, query, fragment))
        self.logger.debug("created url: %s", url)

        return url

    async def _request(
        self, req_method: str, endpoint: str, extra_query: QueryDict = None, json=True
    ) -> Union[Dict, bytes]:
        """Does requests against the Subsonic API.

        A wrapper to create GET requests against the API. It takes the endpoint, builds
        url, does the requests and parses the json data.

        Args:
            req_method (str): The request method to use.
            endpoint (str): The Endpoint to connect to.
            extra_query (QueryDict, optional): Extra query arguments that needs to
                get encoded in the API url.
            json (bool, optional): If data should get decoded to a dict object.
                Defaults to True.

        Returns:
            Parsed json data dict or raw bytes.

        Raises:
            APIError: An error when something goes wrong while communicating
                with the API.
        """
        if req_method not in ("GET", "POST"):
            raise APIError(f"{req_method} not a known request method!")

        url = await self._create_url(endpoint, extra_query=extra_query)

        async with aiohttp.ClientSession() as session:

            session_methods = {"GET": session.get, "POST": session.post}

            async with session_methods[req_method](url) as resp:
                self.logger.debug("got response: %s", resp)

                if resp.status == 200:
                    if json:
                        data = await resp.json()
                        self.logger.debug("got json: %s", data)
                        if data["subsonic-response"]["status"] == "failed":
                            raise APIError(
                                data["subsonic-response"]["error"]["message"]
                            )
                        return data

                    data = await resp.read()
                    return data

                raise APIError(f"got status code {resp.status}!")

    async def ping(self) -> Dict:
        """/ping

        Used to test connectivity with the server. Takes no extra parameters.
        """
        return await self._request("GET", "/ping")

    async def get_license(self) -> Dict:
        """/getLicense

        Get details about the software license. Takes no extra parameters.
        """
        return await self._request("GET", "/getLicense")

    async def get_music_folders(self) -> Dict:
        """/getMusicFolders

    Returns all configured top-level music folders. Takes no extra parameters.
    """
        return await self._request("GET", "/getMusicFolders")

    async def get_indexes(
        self,
        music_folder_id: Optional[int] = None,
        if_modified_since: Optional[int] = None,
    ) -> Dict:
        """/getIndexes

        Args:
            music_folder_id (int, optional): If specified, only return artists in
                the music folder with the given ID.
            if_modified_since (int, optional): If specified, only return a result if the
                artist collection has changed since the given time (in milliseconds
                since 1 Jan 1970)
        """
        extra_query: QueryDict = {}
        extra_query["musicFolderId"] = music_folder_id
        extra_query["ifModifiedSince"] = if_modified_since

        result = await self._request("GET", "/getIndexes", extra_query=extra_query)

        return result["subsonic-response"]["indexes"]

    async def get_music_directory(self, folder_id: int) -> Dict:
        """/getMusicDirectory

        Returns a listing of all files in a music directory. Typically used to get
        list of albums for an artist, or list of songs for an album.

        Args:
            folder_id (int): A string which uniquely identifies the music folder.
                Obtained by calls to getIndexes or getMusicDirectory.
        """
        result = await self._request(
            "GET", "/getMusicDirectory", extra_query={"id": folder_id}
        )

        return result["subsonic-response"]["directory"]

    async def get_genres(self) -> Dict:
        """/getGenres

        Returns all genres.
        """
        result = await self._request("GET", "/getGenres")

        return result["subsonic-response"]["genres"]

    async def get_artists(self, music_folder_id: Optional[int] = None) -> Dict:
        """/getArtists

        Similar to getIndexes, but organizes music according to ID3 tags.

        Args:
           music_folder_id (int, optional): If specified, only return artists in the
               music folder with the given ID.

        Returns:
            dict: Dictionary with Artists and its album count.

            Example::

                {
                    'index': [
                        {
                            'artist': [
                                {
                                    'albumCount': 1,
                                    'coverArt': 'ar-998',
                                    'id': '998',
                                    'name': 'A.M. Thawn'
                                }
                            ]
                        }
                    ]
                }

        """
        extra_query: QueryDict = {}
        extra_query["musicFolderId"] = music_folder_id

        result = await self._request("GET", "/getArtists", extra_query=extra_query)

        return result["subsonic-response"]["artists"]

    async def get_artist(self, artist_id: int) -> Dict:
        """/getArtist

        Returns details for an artist, including a list of albums.
        This method organizes music according to ID3 tags.

        Args:
            artist_id (int): The artist ID.

        Returns:
            dict: Dictionary with artist data.

            Example::

                {
                    'album': [
                        {
                            'artist': 'A.M. Thawn',
                            'artistId': '998',
                            'coverArt': 'al-2636',
                            'created': '2015-05-19T06:29:18.000Z',
                            'duration': 1378,
                            'genre': 'Post-Hardcore',
                            'id': '2636',
                            'name': 'The Oscillating Fan',
                            'songCount': 7,
                            'year': 2000
                        }
                    ],
                    'albumCount': 1,
                    'coverArt': 'ar-998',
                    'id': '998',
                    'name': 'A.M. Thawn'
                }

        """
        result = await self._request("GET", "/getArtist", extra_query={"id": artist_id})

        return result["subsonic-response"]["artist"]

    async def get_album(self, album_id: int) -> Dict:
        """/getAlbum

        Returns details for an album, including a list of songs.
        This method organizes music according to ID3 tags.

        Args:
            album_id (int): The album ID.

        Returns:
            dict: Album data.

            Example::

                {
                    'artist': 'A.M. Thawn',
                    'artistId': '998',
                    'coverArt': 'al-2636',
                    'created': '2015-05-19T06:29:18.000Z',
                    'duration': 1378,
                    'genre': 'Post-Hardcore',
                    'id': '2636',
                    'name': 'The Oscillating Fan',
                    'song': [
                        {
                           'album': 'The Oscillating Fan',
                           'albumId': '2636',
                           'artist': 'A.M. Thawn',
                           'artistId': '998',
                           'bitRate': 997,
                           'contentType': 'audio/flac',
                           'coverArt': '36959',
                           'created': '2015-05-19T06:29:18.000Z',
                           'discNumber': 1,
                           'duration': 180,
                           'genre': 'Post-Hardcore',
                           'id': '36964',
                           'isDir': False,
                           'isVideo': False,
                           'parent': '36959',
                           'path': 'A.M. Thawn/The Oscillating Fan/01 The Money.flac',
                           'playCount': 7,
                           'size': 22454316,
                           'suffix': 'flac',
                           'title': 'The Money Race',
                           'track': 1,
                           'transcodedContentType': 'audio/mpeg',
                           'transcodedSuffix': 'mp3',
                           'type': 'music',
                           'year': 2000
                        },
                    ]
                    'songCount': 1,
                    'year': 2000
                }

        """
        result = await self._request("GET", "/getAlbum", extra_query={"id": album_id})

        return result["subsonic-response"]["album"]

    async def get_song(self, song_id: int) -> Dict:
        """/getSong

        Returns details for a song.

        Args:
            song_id (int): The song ID.

        Returns:
            dict: Details for a song.

            Example::

                {
                    'album': 'The Oscillating Fan',
                    'albumId': '2636',
                    'artist': 'A.M. Thawn',
                    'artistId': '998',
                    'bitRate': 997,
                    'contentType': 'audio/flac',
                    'coverArt': '36959',
                    'created': '2015-05-19T06:29:18.000Z',
                    'discNumber': 1,
                    'duration': 180,
                    'genre': 'Post-Hardcore',
                    'id': '36964',
                    'isDir': False,
                    'isVideo': False,
                    'parent': '36959',
                    'path': 'A.M. Thawn/The Oscillating Fan/01 The Money Race.flac',
                    'playCount': 7,
                    'size': 22454316,
                    'suffix': 'flac',
                    'title': 'The Money Race',
                    'track': 1,
                    'transcodedContentType': 'audio/mpeg',
                    'transcodedSuffix': 'mp3',
                    'type': 'music',
                    'year': 2000
                }

        """
        result = await self._request("GET", "/getSong", extra_query={"id": song_id})

        return result["subsonic-response"]["song"]

    async def get_videos(self) -> List[Dict]:
        """/getVideos

        Returns all video files.

        Returns:
            list: Videos with details.

            Example::

                [
                    {
                        'video': [
                            {
                                'album': '12 Monkeys',
                                'contentType': 'video/avi',
                                'created': '2014-09-02T09:20:37.000Z',
                                'id': '59079',
                                'isDir': False,
                                'isVideo': True,
                                'parent': '58722',
                                'path': '12 Monkeys/12 Monkeys.avi',
                                'playCount': 0,
                                'size': 572141414,
                                'suffix': 'avi',
                                'title': '12 Monkeys',
                                'transcodedContentType': 'video/x-flv',
                                'transcodedSuffix': 'flv',
                                'type': 'video'
                            },
                        ]
                    }
                ]

        """
        result = await self._request("GET", "/getVideos")

        return result["subsonic-response"]["videos"]

    async def get_video_info(self, video_id: int) -> Dict:
        """/getVideoInfo

        Returns details for a video, including information about available
        audio tracks, subtitles (captions) and conversions.

        Args:
           video_id (int): The video ID.

        Returns:
            dict: Video details.

        """
        result = await self._request(
            "GET", "/getVideoInfo", extra_query={"id": video_id}
        )

        return result

    async def download(self, file_id: int, destination: str) -> None:
        """/download

        Downloads file.

        Args:
            file_id (int): Id of the file in the subsonic db.
            destination (str): the local full path to download the file to.
        """
        file = await aiofiles.open(destination, mode="wb")
        self.logger.info("start to download file to %s", destination)
        await file.write(
            await self._request(
                "GET", "/download", extra_query={"id": file_id}, json=False
            )
        )
        await file.close()
        self.logger.info("done writing file")
