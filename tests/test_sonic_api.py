# pylint: disable=missing-docstring,protected-access,redefined-outer-name
import pytest
from asynctest import CoroutineMock, call, patch

from aiosonic import sonic_api
from aiosonic.errors import APIError


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
    "server,extra_query,expected",
    [
        (
            "https://foo.bar:4040",
            None,
            (
                "https://foo.bar:4040/rest/endpoint"
                "?u=username&t=token&s=salt&c=aiosonic&v=1.15.0&f=json"
            ),
        ),
        (
            "https://bla.tld:8080/subsonic/",
            None,
            (
                "https://bla.tld:8080/subsonic/rest/endpoint"
                "?u=username&t=token&s=salt&c=aiosonic&v=1.15.0&f=json"
            ),
        ),
        (
            "https://bla.tld:8080/subsonic",
            None,
            (
                "https://bla.tld:8080/subsonic/rest/endpoint"
                "?u=username&t=token&s=salt&c=aiosonic&v=1.15.0&f=json"
            ),
        ),
        (
            "https://bla.tld:8080/subsonic",
            {"foo": "bar"},
            (
                "https://bla.tld:8080/subsonic/rest/endpoint"
                "?u=username&t=token&s=salt&c=aiosonic&v=1.15.0&f=json&foo=bar"
            ),
        ),
    ],
)
@patch("aiosonic.sonic_api.SonicAPI._create_token")
async def test_create_url(mock_create_token, server, extra_query, expected):
    mock_create_token.return_value = ("salt", "token")

    sonic = sonic_api.SonicAPI(server, "username", "password")

    result = await sonic._create_url("/endpoint", extra_query=extra_query)

    assert result == expected


@pytest.mark.asyncio
@patch("aiosonic.sonic_api.SonicAPI._create_url")
@patch("aiosonic.sonic_api.aiohttp.ClientSession.get")
async def test_request_exception(mock_get, mock_create_url, sonic):
    mock_create_url.return_value = "http://foo.bar.tld/endpoint"
    mock_get.return_value.__aenter__.return_value.json = CoroutineMock(
        return_value={
            "subsonic-response": {
                "status": "failed",
                "error": {"message": "this is a test"},
            }
        }
    )
    mock_get.return_value.__aenter__.return_value.status = 200

    with pytest.raises(APIError, match="this is a test"):
        await sonic._request("GET", "/endpoint")


@pytest.mark.asyncio
@patch("aiosonic.sonic_api.SonicAPI._create_url")
@patch("aiosonic.sonic_api.aiohttp.ClientSession.get")
async def test_request_no_200(mock_get, mock_create_url, sonic):
    mock_create_url.return_value = "http://foo.bar.tld/endpoint"
    mock_get.return_value.__aenter__.return_value.status = 404

    with pytest.raises(APIError, match="got status code 404!"):
        await sonic._request("GET", "/endpoint")


@pytest.mark.asyncio
async def test_request_wrong_method(sonic):
    with pytest.raises(APIError):
        await sonic._request("FOO", "/endpoint")


@pytest.mark.asyncio
@patch("aiosonic.sonic_api.SonicAPI._create_url")
@patch("aiosonic.sonic_api.aiohttp.ClientSession.get")
async def test_request_json_false(mock_get, mock_create_url, sonic):
    mock_create_url.return_value = "http://foo.bar.tld/endpoint"
    mock_get.return_value.__aenter__.return_value.read = CoroutineMock(
        return_value="this is data"
    )
    mock_get.return_value.__aenter__.return_value.status = 200

    result = await sonic._request("GET", "/endpoint", json=False)

    assert result == "this is data"


@pytest.mark.asyncio
@patch("aiosonic.sonic_api.SonicAPI._create_url")
@patch("aiosonic.sonic_api.aiohttp.ClientSession.get")
async def test_request_json_true(mock_get, mock_create_url, sonic):
    mock_create_url.return_value = "http://foo.bar.tld/endpoint"
    mock_get.return_value.__aenter__.return_value.json = CoroutineMock(
        return_value={"subsonic-response": {"status": "ok", "foo": "bar"}}
    )
    mock_get.return_value.__aenter__.return_value.status = 200

    result = await sonic._request("GET", "/endpoint", json=True)

    assert result == {"subsonic-response": {"status": "ok", "foo": "bar"}}


@pytest.mark.asyncio
@patch("aiosonic.sonic_api.SonicAPI._request")
async def test_download(mock_request, sonic, tmpdir):
    mock_request.return_value = b"foo bar"
    download_file = tmpdir.join("foo.txt")
    await sonic.download(123, download_file.strpath)

    assert download_file.read() == "foo bar"
