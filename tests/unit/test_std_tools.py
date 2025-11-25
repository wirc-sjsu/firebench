import pytest
from firebench.standardize import merge_authors


@pytest.mark.parametrize(
    "created_by_1, created_by_2, expected",
    [
        # 1. Simple case: same length, no overlaps
        # file1: alice, bob
        # file2: carol, dan
        # order: a1, a2, b1, b2
        (
            "alice;bob;",
            "carol;dan;",
            "alice;carol;bob;dan;",
        ),
        # 2. Different length, no overlaps (file1 longer)
        # file1: alice, bob, charlie
        # file2: dan, erin
        # positions:
        #   i=0: alice, dan
        #   i=1: bob, erin
        #   i=2: charlie (only file1)
        (
            "alice;bob;charlie;",
            "dan;erin;",
            "alice;dan;bob;erin;charlie;",
        ),
        # 3. Different length, no overlaps (file2 longer)
        # file1: alice, bob
        # file2: carol, dan, erin
        # positions:
        #   i=0: alice, carol
        #   i=1: bob, dan
        #   i=2: erin (only file2)
        (
            "alice;bob;",
            "carol;dan;erin;",
            "alice;carol;bob;dan;erin;",
        ),
        # 4. Overlap across lists
        # file1: alice, bob
        # file2: bob, carol
        # positions:
        #   i=0: alice, bob -> alice, bob
        #   i=1: bob (already seen), carol -> carol
        # merged: alice, bob, carol
        (
            "alice;bob;",
            "bob;carol;",
            "alice;bob;carol;",
        ),
        # 5. Duplicate within the same list + overlap
        # file1: alice, alice, bob
        # file2: carol, alice
        # positions:
        #   i=0: alice, carol -> alice, carol
        #   i=1: alice (seen), alice (seen) -> no new author
        #   i=2: bob -> bob
        # merged: alice, carol, bob
        (
            "alice;alice;bob;",
            "carol;alice;",
            "alice;carol;bob;",
        ),
        # 6. One side empty (no authors in file1)
        # file1: ""
        # file2: alice, bob
        (
            "",
            "alice;bob;",
            "alice;bob;",
        ),
        # 7. One side empty (no authors in file2)
        # file1: alice, bob
        # file2: ""
        (
            "alice;bob;",
            "",
            "alice;bob;",
        ),
        # 8. Both empty
        (
            "",
            "",
            "",
        ),
        # 9. Trailing semicolons with possible stray spaces
        # Expect that your function strips whitespace around names.
        # file1: " alice  ", "bob"
        # file2: "bob ", "  carol"
        # merged: alice, bob, carol (no duplicates, trimmed)
        (
            " alice  ;bob ;",
            "bob ;  carol ;",
            "alice;bob;carol;",
        ),
        # 10. Multiple overlaps and reordering
        # file1: alice, bob, charlie, dave
        # file2: bob, erin, charlie, frank
        # positions:
        #   i=0: alice, bob       -> alice, bob
        #   i=1: bob(seen), erin  -> erin
        #   i=2: charlie, charlie -> charlie
        #   i=3: dave, frank      -> dave, frank
        # merged: alice, bob, erin, charlie, dave, frank
        (
            "alice;bob;charlie;dave;",
            "bob;erin;charlie;frank;",
            "alice;bob;erin;charlie;dave;frank;",
        ),
    ],
)
def test_merge_authors(created_by_1, created_by_2, expected):
    assert merge_authors(created_by_1, created_by_2) == expected
