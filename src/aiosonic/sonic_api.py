"""The Sonic API Object."""
import asyncio
import hashlib
import logging
import random
import string
from dataclasses import dataclass
from typing import Any, Dict, Tuple
from urllib.parse import urlencode, urlsplit, urlunsplit

import aiohttp

LOGGER = logging.getLogger("SonicAPI")


@dataclass
class SonicAPI:
    """A SonicAPI object."""

    server: str
    username: str
    password: str

    @staticmethod
    def _create_salt() -> str:
        """Creates random salt."""
        random_salt = "".join(
            random.SystemRandom().choice(string.ascii_uppercase + string.digits)
            for _ in range(10)
        )
        LOGGER.debug("random salt: %s", random_salt)

        return random_salt

    @staticmethod
    def _create_md5(password) -> str:
        """Create MD5 sum from password."""
        md5_hash = hashlib.md5(password.encode("utf-8")).hexdigest()
        LOGGER.debug("created md5 hash: %s", md5_hash)

        return md5_hash

    async def _create_token(self) -> Tuple[str, str]:
        """Create authentication token."""
        loop = asyncio.get_running_loop()
        salt = await loop.run_in_executor(None, self._create_salt)
        LOGGER.debug("salt: %s", salt)
        token = await loop.run_in_executor(None, self._create_md5, self.password + salt)
        LOGGER.debug("token: %s", token)

        return (salt, token)

    async def _create_url(self, endpoint: str) -> str:
        salt, token = await self._create_token()
        query = urlencode(
            {
                "u": self.username,
                "t": token,
                "s": salt,
                "c": "aiosonic",
                "v": "1.15.0",
                "f": "json",
            }
        )
        scheme, netloc, path, _, fragment = urlsplit(self.server)
        if path and path[-1] == "/":
            path = path[:-1]
        path = path + "/rest" + endpoint
        url = urlunsplit((scheme, netloc, path, query, fragment))
        LOGGER.debug("created url: %s", url)

        return url

    async def _get(self, endpoint: str) -> Dict[Any, Any]:
        """Doing GET requests against the Subsonic"""
        url = await self._create_url(endpoint)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                # TODO: exception handling on other return codes.
                if resp.status == 200:
                    return await resp.json()

    async def ping(self) -> Dict[Any, Any]:
        """/ping"""
        return await self._get("/ping")

    async def get_license(self) -> Dict[Any, Any]:
        """/getLicense"""
        return await self._get("/getLicense")
