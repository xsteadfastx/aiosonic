"""The Sonic API Object."""
import asyncio
import hashlib
import logging
import random
import string
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Union
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp

from aiosonic.errors import APIError


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

    async def _create_url(
        self, endpoint: str, extra_query: Optional[Dict] = None
    ) -> str:
        salt, token = await self._create_token()
        query_dict = {
            "u": self.username,
            "t": token,
            "s": salt,
            "c": "aiosonic",
            "v": "1.15.0",
            "f": "json",
        }
        if extra_query:
            query_dict = {**query_dict, **extra_query}
        query = urlencode(query_dict)
        scheme, netloc, path, _, fragment = urlsplit(self.server)
        if path and path[-1] == "/":
            path = path[:-1]
        path = path + "/rest" + endpoint
        url = urlunsplit((scheme, netloc, path, query, fragment))
        self.logger.debug("created url: %s", url)

        return url

    async def _get(
        self, endpoint: str, extra_query: Optional[Dict] = None
    ) -> Dict:
        """Doing GET requests against the Subsonic API."""
        url = await self._create_url(endpoint, extra_query=extra_query)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                self.logger.debug("got response: %s", resp)
                if resp.status == 200:
                    data = await resp.json()
                    self.logger.debug("got json: %s", data)
                    if data["subsonic-response"]["status"] == "failed":
                        raise APIError(data["subsonic-response"]["error"]["message"])
                    return data
                raise APIError("status code not 200!")

    async def ping(self) -> Dict:
        """/ping

        Used to test connectivity with the server. Takes no extra parameters.
        """
        return await self._get("/ping")

    async def get_license(self) -> Dict:
        """/getLicense

        Get details about the software license. Takes no extra parameters.
        """
        return await self._get("/getLicense")

    async def get_music_folders(self) -> Dict:
        """/getMusicFolders

    Returns all configured top-level music folders. Takes no extra parameters.
    """
        return await self._get("/getMusicFolders")

    async def get_indexes(
        self,
        music_folder_id: Optional[int] = None,
        if_modified_since: Optional[int] = None,
    ) -> Dict:
        """/getIndexes

        Args:
            music_folder_id (int): If specified, only return artists in the music folder
                with the given ID
            if_modified_since (int): If specified, only return a result if the
                artist collection has changed since the given time
                (in milliseconds since 1 Jan 1970)
        """
        extra_query: Optional[Dict[str, Any]] = {}
        extra_query["musicFolderId"] = music_folder_id
        extra_query["ifModifiedSince"] = if_modified_since

        result = await self._get("/getIndexes", extra_query=extra_query)

        return result["subsonic-response"]["indexes"]

    async def get_music_directory(self, folder_id: int) -> Dict:
        """/getMusicDirectory

        Returns a listing of all files in a music directory. Typically used to get
        list of albums for an artist, or list of songs for an album.

        Args:
            folder_id (int): A string which uniquely identifies the music folder.
                Obtained by calls to getIndexes or getMusicDirectory.
        """
        result = await self._get("/getMusicDirectory", extra_query={"id": folder_id})

        return result["subsonic-response"]["directory"]

    async def get_genres(self) -> Dict:
        """/getGenres

        Returns all genres.
        """
        result = await self._get("/getGenres")

        return result["subsonic-response"]["genres"]

    async def get_artists(self, music_folder_id: Optional[int] = None) -> Dict:
        """/getArtists

        Similar to getIndexes, but organizes music according to ID3 tags.

        Args:
           music_folder_id (int): If specified, only return artists in the
               music folder with the given ID.

        Returns:
            Dict: Dictionary with Artists and its album count.

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
        extra_query: Optional[Dict] = {}
        if music_folder_id:
            extra_query["musicFolderId"] = music_folder_id

        result = await self._get("/getArtists", extra_query=extra_query)

        return result["subsonic-response"]["artists"]
