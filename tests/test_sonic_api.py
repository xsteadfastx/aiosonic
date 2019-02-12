# pylint: disable=missing-docstring,protected-access,redefined-outer-name
import pytest
from asynctest import call, patch

from aiosonic import sonic_api


@pytest.fixture
def sonic():
    yield sonic_api.SonicAPI("server", "username", "password")


@pytest.mark.asyncio
@patch("aiosonic.sonic_api.SonicAPI._create_md5")
@patch("aiosonic.sonic_api.SonicAPI._create_salt")
async def test_create_token(mock_create_salt, mock_create_md5, sonic):
    mock_create_salt.return_value = "foobar"
    mock_create_md5.return_value = "f00b4r"

    result = await sonic._create_token()

    assert result == ("foobar", "f00b4r")

    mock_create_salt.assert_called_once()

    mock_create_md5.assert_has_calls([call("passwordfoobar")])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "server,expected",
    [
        (
            "https://foo.bar:4040",
            (
                "https://foo.bar:4040/rest/endpoint"
                "?u=username&t=token&s=salt&c=aiosonic&v=1.15.0&f=json"
            )
        ),
        (
            "https://bla.tld:8080/subsonic/",
            (
                "https://bla.tld:8080/subsonic/rest/endpoint"
                "?u=username&t=token&s=salt&c=aiosonic&v=1.15.0&f=json"
            )
        ),
        (
            "https://bla.tld:8080/subsonic",
            (
                "https://bla.tld:8080/subsonic/rest/endpoint"
                "?u=username&t=token&s=salt&c=aiosonic&v=1.15.0&f=json"
            )
        ),
    ],
)
@patch("aiosonic.sonic_api.SonicAPI._create_token")
async def test_create_url(mock_create_token, server, expected):
    mock_create_token.return_value = ("salt", "token")

    sonic = sonic_api.SonicAPI(server, "username", "password")

    result = await sonic._create_url("/endpoint")

    assert result == expected
