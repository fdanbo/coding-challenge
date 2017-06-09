#!/usr/bin/env python

import re
import sys

from collections import deque
from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException
from urlparse import urlparse


def domain_from_subdomain(subdomain):
    # www.jana.com -> jana.com
    return '.'.join(subdomain.split('.')[-2:])


class EmailFinder:
    def run(self, url):
        self.emails_found = set()

        parsed_url = urlparse(url)
        if parsed_url.scheme != 'http' and parsed_url.scheme != 'https':
            raise Exception('please pass a full URL, http or https')

        # we'll only follow links that stay on this domain. It's not clear from
        # the instructions whether we should follow a link from, say,
        # 'www.cnn.com' to 'specials.cnn.com', but it seems reasonable, so we
        # compare here just against the domain, 'cnn.com'.
        self.domain = domain_from_subdomain(parsed_url.netloc)

        self.urls_to_process = deque([url])

        # remember all urls we see, and set the state as either 'queued' or
        # 'visited'. both states prevent queuing if the url is seen again, but
        # because of redirects we still might end up visiting the same url
        # again, and we skip parsing in that case.
        self.urls_seen = {url: 'queued'}

        self.driver = webdriver.PhantomJS()
        # self.driver.set_window_size(1120, 550)

        while self.urls_to_process:
            # popping from the beginning of the list (efficient because we're
            # using a deque) makes the search breadth-first, so you're looking
            # at all the links at depth 1 first, then depth 2, then depth 3,
            # etc.
            url = self.urls_to_process.popleft()

            # skip things that were already visited. again, we do avoid
            # queueing things we've already seen, but this can happen if there
            # was a redirect to this url from somewhere else.
            if self.urls_seen.get(url) == 'visited':
                continue

            self.driver.get(url)

            # if there was a redirect, make sure it's not something we've
            # already visited.
            redirected_url = self.driver.current_url
            if self.urls_seen.get(redirected_url) == 'visited':
                continue

            # if we were redirected off of the domain, skip that.
            if (domain_from_subdomain(
                    urlparse(redirected_url).netloc) != self.domain):
                continue

            # mark both the start url and the redirected url as visited
            self.urls_seen[url] = 'visited'
            self.urls_seen[redirected_url] = 'visited'

            # now look at the contents of the page, parsing out emails and
            # adding any links to the queue of urls.
            self.parse_current_page()

        self.driver.quit()

    def parse_current_page(self):
        # search the raw page source for things that look like email
        # addresses. I grabbed this regex from the internet somewhere -- it'll
        # miss some things like "danob@social.horse" or whatever, but it seems
        # to work well in normal cases. Trying to make it perfect starts
        # catching other stuff that isn't email addresses.
        email_re = r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,4}\b'
        for match in re.finditer(email_re, self.driver.page_source,
                                 flags=re.IGNORECASE):
            self.on_email_found(match.group(0))

        # look for '<a href=whatever>' tags, which we'll search recursively.
        for element in self.driver.find_elements_by_tag_name('a'):
            try:
                href = element.get_attribute('href')
            except StaleElementReferenceException:
                # this can happen depending on javascript timing (element
                # was there, now it's not).
                href = None

            if href:
                self.on_href_found(href)

    def on_href_found(self, href):
        parsed = urlparse(href)

        # for mailto: links, record the email address
        if parsed.scheme == 'mailto':
            # handle the "mailto:foo@jana.com?subject=whatever" case by
            # truncating at the first question mark.
            email = parsed.path.split('?', 1)[0]
            self.on_email_found(email)

        elif parsed.scheme == 'http' or parsed.scheme == 'https':
            # only consider links in the same domain that have not yet been
            # seen.
            if (domain_from_subdomain(parsed.netloc) == self.domain and
                    href not in self.urls_seen):
                self.urls_seen[href] = 'queued'
                self.urls_to_process.append(href)

    def on_email_found(self, email):
        if email not in self.emails_found:
            print(email)
            self.emails_found.add(email)


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else 'http://jana.com'

    finder = EmailFinder()
    print('finding email addresses on {}...'.format(url))
    finder.run(url)


if __name__ == '__main__':
    main()
