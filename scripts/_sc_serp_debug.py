from scout_api.modules.crawler.services.product_scrape_service import get_shared_html_fetcher
from scout_api.modules.crawler.services.store_resolver import resolve_spider_by_store_key
get_shared_html_fetcher.cache_clear()
spider=resolve_spider_by_store_key('shoppingchina')
q='playstation 5 digital'
url=spider.build_search_url(q)
print('URL', url, flush=True)
fetch=spider.prepare_fetch_url(url)
print('FETCH', fetch, flush=True)
resp=get_shared_html_fetcher().fetch(fetch)
print('status', getattr(resp,'status_code',None), 'final', getattr(resp,'url',None), 'len', len(resp.text or ''), flush=True)
print('snippet', (resp.text or '')[:500].replace('\n',' '), flush=True)
cands=spider.parse_search_results(resp)
print('n', len(cands), flush=True)
for c in cands[:5]:
  print('-', c.title, c.url, flush=True)
