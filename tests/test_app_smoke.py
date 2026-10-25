"""Rauchtest durch die echte App (HTTP): Anmeldung und die wichtigsten Seiten."""

import pytest
from fastapi.testclient import TestClient

AUTH = ("tester", "test-passwort-123")


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app, follow_redirects=False) as c:
        yield c


def test_ohne_anmeldung_401(client):
    assert client.get("/batches").status_code == 401


def test_falsches_passwort_401(client):
    assert client.get("/batches", auth=("tester", "falsch")).status_code == 401


def test_standard_zugang_funktioniert_nicht(client):
    assert client.get("/batches", auth=("admin", "brewlog")).status_code == 401


@pytest.mark.parametrize("path", ["/batches", "/inventory", "/settings", "/statistics", "/batches/new", "/inventory/new"])
def test_seiten_laden(client, path):
    assert client.get(path, auth=AUTH).status_code == 200


def test_lager_anlegen_zubuchen_und_anzeigen(client):
    r = client.post(
        "/inventory/new",
        auth=AUTH,
        data={"category": "malz", "name": "Testmalz", "unit": "kg", "initial_amount": "5", "color_ebc": "3,5"},
    )
    assert r.status_code == 303
    item_id = 1
    assert client.post(f"/inventory/{item_id}/restock", auth=AUTH, data={"amount": "2", "note": "Test"}).status_code == 303
    page = client.get(f"/inventory/{item_id}", auth=AUTH)
    assert page.status_code == 200
    assert "Testmalz" in page.text and "7.0 kg" in page.text


def test_sud_anlegen_ansehen_und_etikett(client):
    r = client.post(
        "/batches/new",
        auth=AUTH,
        data={
            "batch_number": "1",
            "name": "Rauchtest-Sud",
            "target_volume_l": "20",
            "target_og_plato": "12",
            "grain_inventory_id": "1",
            "grain_malt_name": "",
            "grain_amount_kg": "4",
            "grain_color_ebc": "",
        },
    )
    assert r.status_code == 303
    detail = client.get("/batches/1", auth=AUTH)
    assert detail.status_code == 200 and "Rauchtest-Sud" in detail.text
    label = client.get("/batches/1/label", auth=AUTH)
    assert label.status_code == 200 and "Rauchtest-Sud" in label.text
    assert client.get("/batches/1/edit", auth=AUTH).status_code == 200
    assert client.get("/statistics", auth=AUTH).status_code == 200
