from playwright.sync_api import sync_playwright

from interface_automation.demo import serve


def test_balance_edit_validation_and_tab_persistence():
    with serve() as url, sync_playwright() as driver:
        browser = driver.chromium.launch()
        page = browser.new_page()
        page.goto(url)

        def lookup(member):
            page.get_by_role("textbox", name="Member ID", exact=True).fill(member)
            page.get_by_role("button", name="Search", exact=True).click()

        lookup("99999")
        page.get_by_text("Member not found", exact=True).wait_for()
        assert page.get_by_role("button", name="Update savings balance").count() == 0
        lookup("12345")
        page.get_by_role("link", name="View accounts").click()
        amount = page.get_by_role("textbox", name="New savings balance (USD)")
        for value in ["-1", "abc", "1.001", "1000000000", ""]:
            amount.fill(value)
            page.get_by_role("button", name="Update savings balance").click()
            assert (
                page.get_by_role("status", name="Savings balance", exact=True).inner_text()
                == "1250.75"
            )
        amount.fill("2500.5")
        page.get_by_role("button", name="Update savings balance").click()
        assert (
            page.get_by_role("status", name="Savings balance", exact=True).inner_text() == "2500.50"
        )
        page.reload()
        lookup("12345")
        page.get_by_role("link", name="View accounts").click()
        assert (
            page.get_by_role("status", name="Savings balance", exact=True).inner_text() == "2500.50"
        )
        page.get_by_role("textbox", name="Member ID", exact=True).fill("67890")
        page.get_by_role("textbox", name="New savings balance (USD)").fill("9")
        page.get_by_role("button", name="Update savings balance").click()
        page.get_by_text("Search for the current member before updating a balance.").wait_for()
        lookup("67890")
        page.get_by_role("link", name="View accounts").click()
        assert (
            page.get_by_role("status", name="Savings balance", exact=True).inner_text() == "842.10"
        )
        browser.close()
