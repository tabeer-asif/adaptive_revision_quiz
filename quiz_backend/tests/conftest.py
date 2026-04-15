import sys
from pathlib import Path
from types import SimpleNamespace


# Allow running `pytest` from either repo root or quiz_backend root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class StubResponse(SimpleNamespace):
    def __init__(self, data=None, count=None):
        super().__init__(data=data, count=count)


class StubQuery:
    def __init__(self, db, table_name):
        self._db = db
        self._table = table_name
        self._op = "select"

    def select(self, *args, **kwargs):
        self._op = "select"
        return self

    def eq(self, *args, **kwargs):
        return self

    def lte(self, *args, **kwargs):
        return self

    def gte(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    @property
    def not_(self):
        return self

    def single(self):
        self._op = "select"
        return self

    def insert(self, payload):
        self._op = "insert"
        self._db.last_payloads[(self._table, "insert")] = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._db.last_payloads[(self._table, "update")] = payload
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._db.last_payloads[(self._table, "upsert")] = payload
        self._db.last_payloads[(self._table, "upsert_on_conflict")] = on_conflict
        return self

    def delete(self):
        self._op = "delete"
        return self

    def execute(self):
        return self._db.pop(self._table, self._op)


class StubSupabaseDB:
    def __init__(self, scripted=None):
        self.scripted = scripted or {}
        self.last_payloads = {}

    def table(self, table_name):
        return StubQuery(self, table_name)

    def pop(self, table_name, op):
        key = (table_name, op)
        entries = self.scripted.get(key)
        if entries:
            item = entries.pop(0)
            if isinstance(item, StubResponse):
                return item
            return StubResponse(**item)

        fallback = self.scripted.get((table_name, "default"))
        if fallback:
            item = fallback.pop(0)
            if isinstance(item, StubResponse):
                return item
            return StubResponse(**item)

        return StubResponse(data=[])


class FakeUser:
    def __init__(self, user_id):
        self.id = user_id


class FakeAuthModule:
    def __init__(self):
        self.sign_up_result = None
        self.sign_in_result = None
        self.get_user_result = None
        self.sign_up_error = None
        self.sign_in_error = None
        self.get_user_error = None

    def sign_up(self, payload):
        if self.sign_up_error:
            raise self.sign_up_error
        return self.sign_up_result

    def sign_in_with_password(self, payload):
        if self.sign_in_error:
            raise self.sign_in_error
        return self.sign_in_result

    def get_user(self, token):
        if self.get_user_error:
            raise self.get_user_error
        return self.get_user_result


class FakeSupabaseAuthClient:
    def __init__(self, auth_module):
        self.auth = auth_module
