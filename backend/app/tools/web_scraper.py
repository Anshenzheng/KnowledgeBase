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
    """Recursive web scraper with controlled concurrency"""

    def __init__(self, max_depth: int = 5, max_pages: int = 100, max_concurrent: int = 5):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.max_concurrent = max_concurrent
        self.visited_urls: Set[str] = set()
        self._start_domain: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def _get_start_domain(self, url: str) -> str:
        return urlparse(url).netloc.lower()

    def _is_same_domain(self, url: str) -> bool:
        if self._start_domain is None:
            return False  # Fail-Closed
        return urlparse(url).netloc.lower() == self._start_domain

    async def _is_private_ip_async(self, hostname: str) -> bool:
        """Async DNS resolution with Fail-Closed policy using getaddrinfo"""
        try:
            # Use asyncio's getaddrinfo for async DNS resolution
            loop = asyncio.get_event_loop()
            # getaddrinfo returns (family, type, proto, canonname, sockaddr)
            # sockaddr is (ip, port) for IPv4 or (ip, port, flowinfo, scope_id) for IPv6
            result = await loop.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            
            for res in result:
                try:
                    ip = res[4][0]  # Extract IP from sockaddr
                    ip_obj = ipaddress.ip_address(ip)
                    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                        logger.warning(f"Blocked access to internal IP: {ip_obj}")
                        return True
                except (ValueError, IndexError):
                    continue
            return False
        except Exception as e:
            # Fail-Closed: DNS resolution failed, BLOCK the request
            logger.warning(f"DNS resolution failed for {hostname}: {e}, blocking request")
            return True  # Block if DNS fails (security first)

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
        return response.text

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
        semaphore: asyncio.Semaphore,
        on_page: Callable[[Dict], Awaitable[None]],
    ) -> int:
        if current_depth > self.max_depth:
            return 0
        
        # 严格限制：如果已经达到上限，直接拦截
        if len(self.visited_urls) >= self.max_pages:
            return 0
        
        async with semaphore:
            # 再次进入双重校验，严格拦截并发溢出
            if len(self.visited_urls) >= self.max_pages:
                return 0
            
            # 进入临界区后，如果是新网页则立即占位
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
                await on_page(page_data)
                pages_added += 1

                if current_depth >= self.max_depth:
                    return pages_added

                child_coroutines = []
                for link in child_links:
                    # 预检查：确保即将生成的子任务不会突破上限
                    if link not in self.visited_urls and len(self.visited_urls) < self.max_pages:
                        child_coroutines.append(
                            self.crawl(link, current_depth + 1, semaphore, on_page)
                        )
                
                if child_coroutines:
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

    async def crawl_site(
        self,
        start_url: str,
        on_page: Optional[Callable[[Dict], Awaitable[None]]] = None,
    ) -> List[Dict]:
        self.visited_urls.clear()
        self._start_domain = self._get_start_domain(start_url)
        logger.info(f"Starting crawl from {start_url}, domain={self._start_domain}")
        
        results: Optional[List[Dict]] = [] if on_page is None else None

        if on_page is None:
            async def _on_page(page: Dict) -> None:
                if results is not None:
                    results.append(page)
            on_page = _on_page

        semaphore = asyncio.Semaphore(self.max_concurrent)
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
                await self.crawl(start_url, 0, semaphore, on_page)
            finally:
                self._client = None
                # 显式清理 DNS Resolver 防止文件句柄或内存泄漏
                self._dns_resolver = None

        return results if results is not None else []