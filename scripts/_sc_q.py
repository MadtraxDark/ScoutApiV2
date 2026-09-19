from scout_api.modules.crawler.services.product_scrape_service import get_shared_html_fetcher
from scout_api.modules.crawler.services.store_resolver import resolve_spider_by_store_key
get_shared_html_fetcher.cache_clear()
spider=resolve_spider_by_store_key('shoppingchina')
f=get_shared_html_fetcher()
for q in [
 'CFI2114B','CFI-2115B','cfi-2115b','0711719021483',
 'sony playstation 5 digital','playstation 5 digital 825gb',
 'sony playstation 5 slim digital 825gb','playstation 5 slim digital',
 'playstation 5 digital','console playstation 5 digital',
]:
  url=spider.prepare_fetch_url(spider.build_search_url(q))
  resp=f.fetch(url)
  cands=spider.parse_search_results(resp)
  titles=[c.title[:60] for c in cands[:2]]
  print(repr(q), len(cands), titles, flush=True)
