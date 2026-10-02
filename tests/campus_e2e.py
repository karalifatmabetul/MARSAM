"""Real HTTP functional and viewport checks for the Marmara enhancement.
No request mocks, localStorage shims, download interception or CSP removal.
"""
import json,os,subprocess,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'dist/build-manifest.json').read_text());base=m['base'];origin=os.environ.get('PREVIEW_ORIGIN','http://127.0.0.1:4191')
out=ROOT/'.browser-results/campus';out.mkdir(parents=True,exist_ok=True)
checks=[];errors=[];posts=[]
def ck(name,passed):
    checks.append({'name':name,'passed':bool(passed)})
    assert passed,name
server=None
if not os.environ.get('PREVIEW_ORIGIN'):
    server=subprocess.Popen(['node','scripts/serve.mjs'],cwd=ROOT,env={**os.environ,'PORT':'4191'},stdout=subprocess.DEVNULL)
try:
    for _ in range(60):
        try:urllib.request.urlopen(origin+base+'tr/',timeout=1);break
        except Exception:time.sleep(.15)
    with sync_playwright() as p:
        kw={'headless':True}
        if os.getenv('BROWSER_PATH'):kw['executable_path']=os.environ['BROWSER_PATH']
        browser=p.chromium.launch(**kw)
        for l in m['locales']:
            ctx=browser.new_context(viewport={'width':1440,'height':960},accept_downloads=True)
            page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:posts.append(r.url) if r.method=='POST' else None)
            for w in [320,390,768,1440]:
                page.set_viewport_size({'width':w,'height':960})
                for path in ['', 'collections/', 'compare/', 'events/', 'about/']:
                    r=page.goto(origin+base+l+'/'+path,wait_until='networkidle')
                    ck(f'HTTP {l}/{path} {w}',r.status==200)
                    ck(f'no body overflow {l}/{path} {w}',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                    ck(f'official university mark loaded {l}/{path} {w}',page.locator('.university-signature img').evaluate('(e)=>e.complete&&e.naturalWidth>0'))
                    ck(f'locale direction {l}/{path} {w}',page.locator('html').get_attribute('dir')==('rtl' if l=='ar' else 'ltr'))
                    if path=='' and w<=768:
                        menu=page.locator('.mobile-nav')
                        ck(f'closed menu excluded from layout {l} {w}',not menu.locator('nav').is_visible())
                        menu.locator('summary').click()
                        ck(f'open mobile menu within viewport {l} {w}',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
                        menu.locator('summary').click()
                    if (path=='' and w in [390,1440]) or (l in ['tr','ar'] and path in ['collections/','events/'] and w==1440):
                        page.screenshot(path=str(out/f'{l}-{path.strip("/") or "home"}-{w}.png'),full_page=True)
            page.set_viewport_size({'width':1440,'height':960})
            page.goto(origin+base+l+'/library/',wait_until='networkidle')
            buttons=page.locator('[data-compare-id]')
            ck(f'comparison controls on every record {l}',buttons.count()==m['resources'])
            ids=[]
            for i in range(4):
                ids.append(buttons.nth(i).get_attribute('data-compare-id'));buttons.nth(i).click()
            ck(f'four IDs selected {l}',page.locator('[data-compare-count]').first.inner_text()=='4')
            buttons.nth(4).click()
            ck(f'fifth ID rejected {l}',buttons.nth(4).get_attribute('aria-pressed')=='false')
            page.reload(wait_until='networkidle')
            ck(f'comparison persists {l}',page.locator('[data-compare-count]').first.inner_text()=='4')
            page.locator('[data-compare-nav]').first.click();page.wait_for_selector('.comparison-table')
            ck(f'four real source columns {l}',page.locator('.comparison-table thead th').count()==5)
            ck(f'comparison query binding {l}',all(x in page.url for x in ids))
            ck(f'bibliography is LTR {l}',page.locator('.comparison-table td[dir="ltr"]').count()>=4)
            page.set_viewport_size({'width':390,'height':960})
            ck(f'wide comparison scroll contained {l}',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))
            if l in ['tr','ar']:page.screenshot(path=str(out/f'{l}-comparison-390.png'),full_page=True)
            with page.expect_download() as ev:page.locator('[data-comparison-export]').click()
            data=json.loads(Path(ev.value.path()).read_text())
            ck(f'export is descriptive not clinical {l}',len(data['items'])==4 and data['clinicalRanking'] is False and data['scientificApproval'] is False)
            target='ar' if l!='ar' else 'en'
            page.locator('.language-select summary').click()
            page.locator(f'.language-panel a[hreflang="{target}"]').click();page.wait_for_selector('.comparison-table')
            ck(f'comparison preserved across languages {l}',all(x in page.url for x in ids) and page.locator('.comparison-table thead th').count()==5)
            page.goto(origin+base+l+'/compare/?ids=aservic-principles,aservic-principles,not-a-source,%3Cimg%3E',wait_until='networkidle')
            ck(f'duplicate and unsafe IDs removed {l}',page.locator('.comparison-table thead th').count()==2)
            page.locator('[data-compare-slot]').nth(0).select_option('')
            ck(f'empty comparison handles correctly {l}',page.locator('[data-comparison-export]').is_disabled())
            page.goto(origin+base+l+'/events/',wait_until='networkidle')
            ck(f'no unapproved external event feed {l}',page.locator('.event-card').count()==0 and page.locator('.centre-empty').count()==1)
            ctx.close()
        nojs=browser.new_context(java_script_enabled=False);page=nojs.new_page()
        page.goto(origin+base+'ar/collections/')
        ck('collection source navigation works without JavaScript',page.locator('.collection-section .source-card a[href]').count()>12)
        nojs.close();browser.close()
    ck('no uncaught browser errors',not errors);ck('no POST requests',not posts)
finally:
    if server:server.terminate();server.wait(timeout=10)
    (ROOT/'verification/campus-browser.json').write_text(json.dumps({'mode':'LIVE_HTTP_BROWSER','mockedIO':False,'checks':checks,'count':len(checks),'errors':errors,'posts':posts,'limits':['Chromium only. Not scientific or native-language approval. Not independent user research.']},ensure_ascii=False,indent=2))
print(json.dumps({'passed':len(checks),'mode':'LIVE_HTTP_BROWSER'}))
