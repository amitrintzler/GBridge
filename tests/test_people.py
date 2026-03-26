"""Tests for the Google People API wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from gbridge.google.people import PeopleService


def _make_service(responses: list[dict]) -> PeopleService:
    """Create a PeopleService with a mocked Google API client."""
    svc = PeopleService.__new__(PeopleService)

    mock_service = MagicMock()
    call_count = 0

    def mock_execute() -> dict:
        nonlocal call_count
        resp = responses[call_count]
        call_count += 1
        return resp

    mock_service.people().connections().list().execute = mock_execute
    # Re-chain for the builder pattern
    mock_service.people().connections().list.return_value.execute = mock_execute
    svc._service = mock_service
    return svc


class TestPeopleService:
    def test_parse_person(self, sample_person_response: dict) -> None:
        contact = PeopleService._parse_person(sample_person_response)
        assert contact.resource_name == "people/c123456"
        assert contact.display_name == "Jane Doe"
        assert contact.given_name == "Jane"
        assert contact.family_name == "Doe"
        assert "jane@example.com" in contact.emails
        assert contact.organization == "Acme Corp"
        assert contact.title == "Engineer"
        assert contact.notes == "Met at conference"

    def test_parse_person_empty_fields(self) -> None:
        contact = PeopleService._parse_person({
            "resourceName": "people/c999",
            "etag": '"x"',
        })
        assert contact.resource_name == "people/c999"
        assert contact.display_name == ""
        assert contact.emails == ()
        assert contact.phones == ()

    def test_emails_sorted_at_parse(self) -> None:
        person = {
            "resourceName": "people/c1",
            "etag": '"e"',
            "emailAddresses": [
                {"value": "z@test.com"},
                {"value": "a@test.com"},
            ],
        }
        contact = PeopleService._parse_person(person)
        assert contact.emails == ("a@test.com", "z@test.com")

    @patch("gbridge.google.people.build")
    def test_fetch_all_single_page(self, mock_build: MagicMock) -> None:
        mock_api = MagicMock()
        mock_build.return_value = mock_api

        mock_api.people().connections().list().execute.return_value = {
            "connections": [
                {
                    "resourceName": "people/c1",
                    "etag": '"e1"',
                    "names": [{"displayName": "Alice"}],
                }
            ],
            "nextSyncToken": "sync_token_new",
        }

        svc = PeopleService(MagicMock())
        result = svc.fetch_all()

        assert len(result.items) == 1
        assert result.items[0].display_name == "Alice"
        assert result.sync_token == "sync_token_new"
        assert result.deleted_resource_names == []

    @patch("gbridge.google.people.build")
    def test_delta_sync_detects_deletions(self, mock_build: MagicMock) -> None:
        mock_api = MagicMock()
        mock_build.return_value = mock_api

        mock_api.people().connections().list().execute.return_value = {
            "connections": [
                {
                    "resourceName": "people/c_deleted",
                    "etag": '"e"',
                    "metadata": {"deleted": True},
                },
                {
                    "resourceName": "people/c_existing",
                    "etag": '"e2"',
                    "names": [{"displayName": "Bob"}],
                },
            ],
            "nextSyncToken": "sync_token_v2",
        }

        svc = PeopleService(MagicMock())
        result = svc.fetch_all(sync_token="old_token")

        assert len(result.items) == 1
        assert result.items[0].resource_name == "people/c_existing"
        assert result.deleted_resource_names == ["people/c_deleted"]
