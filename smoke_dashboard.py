"""Browser interaction checks against a running dashboard (uses Microsoft Edge)."""
from pathlib import Path
import argparse
from playwright.sync_api import sync_playwright, expect

parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8765')
args = parser.parse_args()

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100}, device_scale_factor=1)
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(args.url)
    expect(page.locator('#symbol')).to_have_text('AAPL')
    expect(page.locator('#rows tr')).to_have_count(15)
    page.screenshot(path='data/dashboard-desktop.png', full_page=True)
    page.locator('#search').fill('microsoft')
    expect(page.locator('.asset')).to_have_count(1)
    page.locator('.asset').click()
    expect(page.locator('#symbol')).to_have_text('MSFT')
    expect(page.locator('#rows tr')).to_have_count(15)
    page.locator('#save').click()
    page.locator('#search').fill('')
    page.locator('[data-filter="Saved"]').click()
    expect(page.locator('.asset')).to_have_count(1)
    page.get_by_role('button', name='Crypto', exact=True).click()
    expect(page.locator('.asset')).to_have_count(2)
    page.locator('[data-symbol="BTC-USD"]').click()
    expect(page.locator('#symbol')).to_have_text('BTC-USD')
    page.locator('#start').fill('2025-01-01')
    page.locator('#end').fill('2025-01-31')
    page.locator('#apply').click()
    expect(page.locator('#records')).to_have_text('31')
    page.locator('#metric').select_option('adjusted_close')
    page.locator('#next').click()
    expect(page.locator('#pageInfo')).to_contain_text('16–30')
    with page.expect_download() as download:
        page.locator('#download').click()
    path = download.value.path()
    assert len(Path(path).read_text().splitlines()) == 32
    page.locator('#start').fill('2025-02-01')
    page.locator('#apply').click()
    expect(page.locator('#error')).to_be_visible()
    page.locator('#start').fill('1900-01-01')
    page.locator('#end').fill('1900-01-02')
    page.locator('#apply').click()
    expect(page.locator('#records')).to_have_text('0')
    expect(page.locator('#download')).to_be_disabled()
    page.locator('[data-period="1Y"]').click()
    expect(page.locator('#rows tr')).to_have_count(15)
    page.set_viewport_size({'width':390, 'height':844})
    page.screenshot(path='data/dashboard-mobile.png', full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile layout overflow'
    assert not errors, errors
    browser.close()
    print('PASS: search, selection, favorites, crypto filter, dates, pagination, export, empty/error states, mobile layout; no JavaScript errors.')
