from tests.conftest import signup, upload


def test_signup_login_me(client):
    headers, data = signup(client)
    assert data["orgs"][0]["role"] == "owner"
    assert data["orgs"][0]["plan"] == "free"

    r = client.post("/api/v1/auth/login", json={"email": "owner@acme.example.com", "password": "password123"})
    assert r.status_code == 200
    r = client.get("/api/v1/auth/me", headers=headers)
    assert r.json()["user"]["email"] == "owner@acme.example.com"


def test_duplicate_signup_and_bad_login(client):
    signup(client)
    r = client.post("/api/v1/auth/signup",
                    json={"email": "owner@acme.example.com", "password": "password123", "org_name": "XY"})
    assert r.status_code == 409
    r = client.post("/api/v1/auth/login", json={"email": "owner@acme.example.com", "password": "wrong-pass"})
    assert r.status_code == 401


def test_missing_and_invalid_token(client):
    assert client.get("/api/v1/datasets").status_code == 401
    assert client.get("/api/v1/datasets", headers={"Authorization": "Bearer nope", "X-Org-Id": "1"}).status_code == 401


def test_org_header_required(client, owner):
    h = {"Authorization": owner["Authorization"]}
    assert client.get("/api/v1/datasets", headers=h).status_code == 400


def test_cannot_access_other_org(client, owner):
    other, _ = signup(client, email="eve@globex.example.com", org="Globex")
    upload(client, owner)
    # Eve uses her own token but Acme's org id -> not found
    h = {"Authorization": other["Authorization"], "X-Org-Id": owner["X-Org-Id"]}
    assert client.get("/api/v1/datasets", headers=h).status_code == 404
    # and her own org sees nothing of Acme's data
    assert client.get("/api/v1/datasets", headers=other).json() == []


def test_roles_viewer_admin_owner(client, owner):
    r = client.post("/api/v1/orgs/members", headers=owner,
                    json={"email": "viewer@acme.example.com", "role": "viewer", "password": "password123"})
    assert r.status_code == 201
    viewer_tok = client.post("/api/v1/auth/login",
                             json={"email": "viewer@acme.example.com", "password": "password123"}).json()
    vh = {"Authorization": f"Bearer {viewer_tok['access_token']}", "X-Org-Id": owner["X-Org-Id"]}

    # viewer can read but not upload or create dashboards
    assert client.get("/api/v1/datasets", headers=vh).status_code == 200
    assert upload(client, vh).status_code == 403
    assert client.post("/api/v1/dashboards", headers=vh, json={"name": "x"}).status_code == 403

    # promote to admin -> can upload; still can't change roles (owner only)
    uid = r.json()["user_id"]
    assert client.patch(f"/api/v1/orgs/members/{uid}", headers=owner, json={"role": "admin"}).status_code == 200
    assert upload(client, vh).status_code == 201
    assert client.patch(f"/api/v1/orgs/members/{uid}", headers=vh, json={"role": "owner"}).status_code == 403


def test_last_owner_protected(client, owner):
    members = client.get("/api/v1/orgs/members", headers=owner).json()
    me = members[0]["user_id"]
    assert client.patch(f"/api/v1/orgs/members/{me}", headers=owner, json={"role": "viewer"}).status_code == 400
    assert client.delete(f"/api/v1/orgs/members/{me}", headers=owner).status_code == 400


def test_invite_requires_password_for_new_user_and_no_duplicates(client, owner):
    r = client.post("/api/v1/orgs/members", headers=owner, json={"email": "new@acme.example.com", "role": "viewer"})
    assert r.status_code == 400
    body = {"email": "new@acme.example.com", "role": "viewer", "password": "password123"}
    assert client.post("/api/v1/orgs/members", headers=owner, json=body).status_code == 201
    assert client.post("/api/v1/orgs/members", headers=owner, json=body).status_code == 409


def test_create_second_org_and_list(client, owner):
    r = client.post("/api/v1/orgs", headers={"Authorization": owner["Authorization"]}, json={"name": "Acme"})
    assert r.status_code == 201
    assert r.json()["slug"] == "acme-2"
    orgs = client.get("/api/v1/orgs", headers={"Authorization": owner["Authorization"]}).json()
    assert len(orgs) == 2


def test_member_removal(client, owner):
    r = client.post("/api/v1/orgs/members", headers=owner,
                    json={"email": "bye@acme.example.com", "role": "viewer", "password": "password123"})
    uid = r.json()["user_id"]
    assert client.delete(f"/api/v1/orgs/members/{uid}", headers=owner).status_code == 204
    assert client.delete(f"/api/v1/orgs/members/{uid}", headers=owner).status_code == 404
