import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from expand_reviewed_officers import expand_reviewed_officers


def office_pair(a, b, person="山田太郎", url="https://example.com/board"):
    return {"id": a + b, "source": {"code": a}, "target": {"code": b},
            "relation_type": "interlocking_director", "person": person,
            "roles": {a: "社外取締役", b: "監査役"}, "as_of": None,
            "document": {"url": url, "origin": "independent_primary_website", "sha256": "abc"},
            "review": {"status": "source_checked", "on": "2026-09-21"}}


class ReviewedOfficerExpansionTests(unittest.TestCase):
    def test_same_profile_establishes_each_shared_officer_pair(self):
        rows = [office_pair("A", "B"), office_pair("A", "C")]
        extra = expand_reviewed_officers(rows)
        self.assertEqual(len(extra), 1)
        self.assertEqual((extra[0]["source"]["code"], extra[0]["target"]["code"]), ("B", "C"))
        self.assertEqual(extra[0]["derived_from"], ["AB", "AC"])
        self.assertEqual(expand_reviewed_officers(rows + extra), [])

    def test_same_name_in_other_documents_does_not_prove_identity(self):
        self.assertEqual(expand_reviewed_officers([
            office_pair("A", "B"), office_pair("A", "C", url="https://example.com/other")]), [])

    def test_different_people_dates_or_document_versions_do_not_join(self):
        left = office_pair("A", "B")
        for changes in ({"person": "山田次郎"}, {"as_of": "2025-01-01"},
                        {"document": {**left["document"], "sha256": "changed"}},
                        {"review": {"status": "needs_review", "on": "2026-09-21"}}):
            right = office_pair("A", "C")
            right.update(copy.deepcopy(changes))
            self.assertEqual(expand_reviewed_officers([left, right]), [])

    def test_adviser_is_not_an_officer(self):
        rows = [office_pair("A", "B"), office_pair("A", "C")]
        rows[1]["roles"]["C"] = "顧問"
        self.assertEqual(expand_reviewed_officers(rows), [])

    def test_executive_employee_is_not_statutory_executive(self):
        rows = [office_pair("A", "B"), office_pair("A", "C")]
        rows[1]["roles"]["C"] = "常務執行役員"
        self.assertEqual(expand_reviewed_officers(rows), [])
        rows[1]["roles"]["C"] = "常務執行役"
        self.assertEqual(len(expand_reviewed_officers(rows)), 1)
