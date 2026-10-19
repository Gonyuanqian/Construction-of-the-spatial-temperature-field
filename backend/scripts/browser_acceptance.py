"""可选 Playwright 浏览器联调；只查询和调整展示，不训练或保存模型。"""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url',required=True); p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); args.output.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'page_errors':[]}
    def check(name,ok,detail=None):
        report['checks'].append({'name':name,'passed':bool(ok),'detail':detail})
        print(('PASS ' if ok else 'FAIL ')+name,flush=True)
        if not ok: raise AssertionError(name)
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True,args=['--use-angle=swiftshader','--enable-unsafe-swiftshader'])
            page=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
            page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
            page.goto(args.base_url+'/data'); page.get_by_role('heading',name='数据导入与检查',exact=True).wait_for(timeout=30000)
            page.screenshot(path=str(args.output/'data.png'),full_page=True)
            page.goto(args.base_url+'/field')
            page.locator('[data-view="volume"]').click(timeout=30000)
            page.locator('.scene canvas').wait_for(timeout=60000)
            page.get_by_label('剖切刀',exact=True).wait_for(timeout=30000)
            before=page.locator('.vol-stage').bounding_box()
            right=page.locator('.vol-ask').bounding_box()
            geometry=page.locator('.vol-geom').bounding_box()
            check('训练三维左右布局和剖切位置',before['x']<right['x'] and geometry['y']>=right['y']+right['height']-2)
            check('训练画布与右侧模块底部对齐',abs(before['y']+before['height']-geometry['y']-geometry['height'])<=2)
            for control in page.locator('.query-box input').all(): control.fill('1')
            page.get_by_role('button',name='查询',exact=True).click()
            page.wait_for_function("!document.querySelector('.query-result').innerText.includes('待查询')")
            after=page.locator('.vol-stage').bounding_box()
            check('查询前后画布高度保持稳定',abs(before['height']-after['height'])<=2)
            for label,value in (('剖切刀','9'),('棚体示意长度','3.5')):
                control=page.get_by_label(label,exact=True)
                control.fill(value); control.dispatch_event('input')
            page.screenshot(path=str(args.output/'field.png'),full_page=True)
            page.goto(args.base_url+'/live')
            page.locator('.scene canvas').wait_for(timeout=60000)
            check('实时三维可渲染',page.locator('.scene canvas').count()==1)
            stage=page.locator('.vol-stage').bounding_box()
            available=page.locator('.vol-grid.stage-only').bounding_box()
            check('实时画布铺满中间展示区',stage['width']>=available['width']*0.95)
            cards=page.locator('.bottom > .card')
            if cards.count()==0: cards=page.locator('.env').locator('..')
            check('实时环境参数横向展示',page.locator('.env .geom-card').count()==2)
            boxes=[item.bounding_box() for item in page.locator('.env > *').all()]
            check('实时环境三项横向排列',len(boxes)==3 and boxes[0]['x']<boxes[1]['x']<boxes[2]['x'])
            page.screenshot(path=str(args.output/'live.png'),full_page=True)
            page.reload(); page.locator('.scene canvas').wait_for(timeout=60000)
            check('刷新实时页面后可加载三维',True)
            check('页面无未捕获异常',not report['page_errors'],report['page_errors'])
            browser.close()
    finally:
        (args.output/'browser-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
