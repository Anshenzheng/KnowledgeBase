"""
Web Scraper Tool - Recursive web content extraction with strict limit control
"""
from typing import List, Dict, Set, Optional, Callable, Awaitable
from bs4 import BeautifulSoup
import httpx
from urllib.parse import urljoin, urlparse
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
import re
import asyncio
import ipaddress
import socket


class WebScraper:
    """Recursive web scraper with controlled concurrency - Producer-Consumer pattern"""

    def __init__(self, max_depth: int = 5, max_pages: int = 100, max_concurrent: int = 5):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.max_concurrent = max_concurrent
        self.visited_urls: Set[str] = set()
        self._start_domain: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._dns_cache: Dict[str, bool] = {}  # DNS 缓存
        self._max_html_size = 5 * 1024 * 1024  # 限制 HTML 最大 5MB

    def _get_start_domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _is_same_domain(self, url: str) -> bool:
        if self._start_domain is None:
            return False
        return urlparse(url).netloc.lower() == self._start_domain

    async def _is_private_ip_async(self, hostname: str) -> bool:
        """Async DNS resolution with caching"""
        if hostname in self._dns_cache:
            return self._dns_cache[hostname]
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            
            for res in result:
                try:
                    ip = res[4][0]
                    ip_obj = ipaddress.ip_address(ip)
                    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                        logger.warning(f"Blocked access to internal IP: {ip_obj}")
                        self._dns_cache[hostname] = True
                        return True
                except (ValueError, IndexError):
                    continue
            self._dns_cache[hostname] = False
            return False
        except Exception as e:
            logger.warning(f"DNS resolution failed for {hostname}: {e}, blocking request")
            self._dns_cache[hostname] = True
            return True

    async def _is_allowed_url(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https']:
                return False
            hostname = parsed.hostname
            if hostname and await self._is_private_ip_async(hostname):
                return False
            if not self._is_same_domain(url):
                return False
            return True
        except Exception as e:
            logger.warning(f"URL validation failed: {e}")
            return False

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def fetch_page(self, url: str) -> Optional[str]:
        if not await self._is_allowed_url(url):
            logger.warning(f"Blocked URL: {url}")
            return None

        response = await self._client.get(url)
        response.raise_for_status()
        
        html = response.text
        if len(html) > self._max_html_size:
            logger.warning(f"HTML too large for {url}, truncating to {self._max_html_size/1024/1024:.1f}MB")
            html = html[:self._max_html_size]
        
        return html

    def _extract_links_from_soup(self, soup: BeautifulSoup, base_url: str) -> List[str]:
        links = []
        for link in soup.find_all('a', href=True):
            href = link['href'].strip()
            if href.startswith(('javascript:', 'mailto:', '#')):
                continue
            absolute_url = urljoin(base_url, href)
            if self._is_valid_url_sync(absolute_url):
                links.append(absolute_url)
        return links

    def _is_valid_url_sync(self, url: str) -> bool:
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ['http', 'https']:
                return False
            skip_extensions = (
                '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.zip',
                '.exe', '.mp4', '.mp3', '.avi', '.mov', '.css', '.js'
            )
            path = url.lower().split('?')[0]
            if any(path.endswith(ext) for ext in skip_extensions):
                return False
            return True
        except Exception:
            return False

    def extract_content(self, html: str, url: str):
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'iframe', 'noscript']):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        main_content = None
        for tag_name in ('article', 'main', 'div'):
            for elem in soup.find_all(tag_name, class_=re.compile(r'(content|post|article|main)')):
                main_content = elem
                break
            if main_content:
                break

        if not main_content:
            main_content = soup.body

        text = main_content.get_text(separator='\n', strip=True) if main_content else ""
        text = re.sub(r'\s+', ' ', text)

        description = ""
        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            description = meta_desc['content']

        links = self._extract_links_from_soup(soup, url)
        page_data = {
            "url": url,
            "title": title,
            "content": text,
            "description": description,
        }
        return page_data, links

    async def crawl(
        self,
        url: str,
        current_depth: int,
        fetch_semaphore: asyncio.Semaphore,
        page_queue: asyncio.Queue,
        cancel_check_callback=None,  # 优化 web_fast_cancel：添加取消检查
    ) -> int:
        """爬虫只负责抓取和提取，将结果放入队列"""
        if current_depth > self.max_depth:
            return 0
        
        if len(self.visited_urls) >= self.max_pages:
            return 0
        
        # 优化 web_fast_cancel：检查取消
        if cancel_check_callback and cancel_check_callback():
            logger.info("Crawl cancelled by user, stopping early")
            return 0
        
        async with fetch_semaphore:
            if len(self.visited_urls) >= self.max_pages:
                return 0
            
            if url in self.visited_urls:
                return 0
            self.visited_urls.add(url)
            
            pages_added = 0
            logger.info(f"Crawling [{len(self.visited_urls)}/{self.max_pages}] depth={current_depth} {url}")

            try:
                html = await self.fetch_page(url)
                if not html:
                    return 0

                page_data, child_links = self.extract_content(html, url)
                
                # 优化 web_fast_cancel：放入队列前检查取消
                if cancel_check_callback and cancel_check_callback():
                    logger.info("Crawl cancelled before queue put, skipping")
                    return 0
                
                # 只将结果放入队列，不等待处理完成
                await page_queue.put(page_data)
                pages_added += 1

                if current_depth >= self.max_depth:
                    return pages_added

                # 预检查并收集子链接
                child_urls = []
                for link in child_links:
                    if link not in self.visited_urls and len(self.visited_urls) < self.max_pages:
                        child_urls.append(link)
                
                # 优化 web_fast_cancel：并发爬取子链接时传入取消检查
                if child_urls:
                    child_coroutines = [
                        self.crawl(child_url, current_depth + 1, fetch_semaphore, page_queue, cancel_check_callback)
                        for child_url in child_urls
                    ]
                    results = await asyncio.gather(*child_coroutines, return_exceptions=True)
                    for result in results:
                        if isinstance(result, int):
                            pages_added += result
                        elif isinstance(result, Exception):
                            logger.error(f"Child crawl error: {result}")

                return pages_added

            except Exception as e:
                logger.error(f"Error crawling {url}: {e}")
                return pages_added

    async def crawl_site_producer_consumer(
        self,
        start_url: str,
        process_page: Callable[[Dict], Awaitable[None]],
        num_workers: int = 3,
        cancel_check_callback=None,  # 修复 web_stop_crawl：添加取消检查回调
    ) -> int:
        """生产者 - 消费者模式：爬虫只入队，worker 处理"""
        self.visited_urls.clear()
        self._start_domain = self._get_start_domain(start_url)
        logger.info(f"Starting crawl from {start_url}, domain={self._start_domain}")
        
        # 优化 web_4：队列添加背压，防止内存无限增长
        page_queue: asyncio.Queue = asyncio.Queue(maxsize=50)  # 最多 50 个页面在队列中
        fetch_semaphore = asyncio.Semaphore(self.max_concurrent)
        processed_count = 0
        crawl_done = asyncio.Event()
        
        async def worker(worker_id: int):
            """消费者：从队列取数据并处理"""
            nonlocal processed_count
            logger.info(f"Worker {worker_id} started")
            
            while True:
                try:
                    # 修复 web_stop_crawl：检查取消
                    if cancel_check_callback and cancel_check_callback():
                        logger.info(f"Worker {worker_id} cancelled, stopping")
                        break
                    
                    page_data = await page_queue.get()
                    if page_data is None:  # 结束信号
                        page_queue.task_done()
                        break
                    
                    try:
                        await process_page(page_data)
                        processed_count += 1
                    except Exception as e:
                        logger.error(f"Worker {worker_id} failed to process page: {e}")
                    finally:
                        page_queue.task_done()
                        
                except asyncio.CancelledError:
                    logger.info(f"Worker {worker_id} cancelled")
                    break
        
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=self.max_concurrent)

        async with httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
            timeout=30.0,
            follow_redirects=True,
            limits=limits,
        ) as client:
            self._client = client
            try:
                # 启动消费者 workers
                workers = [asyncio.create_task(worker(i)) for i in range(num_workers)]
                
                # 优化 web_fast_cancel：启动生产者（爬虫）时传入取消检查
                crawl_task = asyncio.create_task(
                    self.crawl(start_url, 0, fetch_semaphore, page_queue, cancel_check_callback)
                )
                
                # 等待爬虫完成
                await crawl_task
                
                # 优化 queue_join_cancel：取消时清空队列，避免 join 长时间阻塞
                if cancel_check_callback and cancel_check_callback():
                    logger.info("Task cancelled, clearing queue to stop immediately")
                    # 清空队列中剩余的页面
                    while not page_queue.empty():
                        try:
                            page_queue.get_nowait()
                            page_queue.task_done()
                        except asyncio.QueueEmpty:
                            break
                
                # 等待所有已入队的页面处理完成
                await page_queue.join()
                
                # 发送结束信号给所有 worker
                for _ in range(num_workers):
                    await page_queue.put(None)
                
                # 等待所有 worker 结束
                await asyncio.gather(*workers)
                
            finally:
                self._client = None
                self._dns_cache.clear()

        return processed_count