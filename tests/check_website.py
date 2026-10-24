"""Optional real-browser checks: pip install playwright; install Chromium first."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading

from playwright.sync_api import sync_playwright


def main():
    root=Path(__file__).resolve().parents[1]/'website'
    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self,*args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=str(root)))
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    url=f'http://127.0.0.1:{server.server_port}/'
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1440,'height':1000})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(url)
            page.locator('#explorer').wait_for(state='visible')
            assert page.locator('.problem').count()==6
            page.locator('#show-more').click()
            assert page.locator('.problem').count()==12
            page.locator('#topic-filter').select_option('graphs')
            assert page.locator('.problem').count()>0
            assert all('graphs' in t for t in page.locator('.problem').all_text_contents())
            page.locator('#min-rating').fill('5000')
            assert page.locator('#filter-error').inner_text()
            page.locator('#max-rating').fill('5100')
            assert page.locator('.problem').count()==0
            assert 'No saved candidates' in page.locator('#problems').inner_text()
            page.locator('#reset').click()
            page.locator('#handle').fill('not-a-saved-user')
            page.locator('#user-form button').click()
            assert 'not in the saved examples' in page.locator('#handle-error').inner_text()
            page.locator('#handle').fill('RAHMA_HISHAM925')
            page.locator('#user-form button').click()
            assert 'exploration only' in page.locator('#user-summary').inner_text()
            assert 'Probability withheld' in page.locator('.problem').first.inner_text()
            page.locator('#test-select').select_option('unseen_user_test')
            assert '17 users' in page.locator('#test-summary').inner_text()
            assert 'includes no improvement' in page.locator('#uncertainty').inner_text()
            before=page.locator('#metrics').inner_text()
            page.locator('#weight-select').select_option('submission')
            assert before != page.locator('#metrics').inner_text()
            page.locator('#handle').fill('ethanxupro')
            page.locator('#user-form button').click()
            page.goto(url)
            page.locator('#explorer').wait_for(state='visible')
            page.screenshot(path='/tmp/dsa-website-desktop.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.screenshot(path='/tmp/dsa-website-mobile.png',full_page=True)
            failed=browser.new_page()
            failed.route('**/data.json',lambda route:route.abort())
            failed.goto(url)
            failed.get_by_text('Saved examples could not be loaded.',exact=False).wait_for()
            assert not errors,errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print('Browser checks passed: filters, invalid/empty states, sparse user, model comparison, mobile layout and load failure.')


if __name__=='__main__':
    main()
