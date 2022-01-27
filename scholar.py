from __future__ import print_function

import os.path
import base64
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from bs4 import BeautifulSoup

import pandas

# zotero read
from pyzotero import zotero

# progress bar
from tqdm import tqdm

# command line
import fire


# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def get_gmail(service, userId):
    """
    Get unread emails with label
    """
    scholar_emails = service.users().messages().list(userId=userId, labelIds='Label_5', q='is:unread').execute()
    scholar_emails = scholar_emails['messages']
    scholar_emails_ids = list(map(lambda x: x['id'], scholar_emails))

    scholar_emails = [service.users().messages().get(userId=userId, id=email_id, format='raw').execute()
                        for email_id in scholar_emails_ids]
    # pair (raw_text, date as unix timestamp)
    scholar_raw_emails = [(base64.urlsafe_b64decode(mail['raw']).decode('utf-8'), mail['internalDate'])
                            for mail in scholar_emails]

    return scholar_raw_emails


def papers_from_emails(scholar_raw_emails):
    """
    Extract papers list from raw Scholar emails.
    """
    papers_list = list()

    for raw_email, date in tqdm(scholar_raw_emails):
        email_html = raw_email.replace('=\r\n', '').replace('\t', '')
        email_html = email_html[raw_email.index('<html'):email_html.index('</html') + 7]
        soup = BeautifulSoup(email_html, 'html.parser')

        links = soup.find_all('a')
        # a paper every 5 links: [PAPER, star, twitter, linkedin, facebook, PAPER, star, ...]
        links_indices = [5 * i for i in range(0, len(links) // 5)]
        links = [links[i] for i in links_indices]

        # paper title
        titles = [link.get_text() for link in links]
        titles = [t.replace('=\r\n', '').replace('\t', '') for t in titles]
        
        # link to paper
        urls = list()
        indices = [(s.start(), e.start()) for s, e in zip(list(re.finditer('<a', email_html)),
                                                            list(re.finditer('</a', email_html)))]
        indices = [indices[i] for i in links_indices]
        # parse
        for start_index, end_index in indices:
            url = email_html[start_index:end_index]
            url = url.replace('=\r\n', '').replace('\t', '')
            if 'scholar_url?url=3D' in url:
                k, l = url.index('scholar_url?url=3D') + 18, url.index('amp;hl=') - 1
            else:
                k = url.index('href=') + 8
                l = url[k + 1:].index('"') + k + 1
            url = url[k:l].replace('=\r\n', '').replace('\t', '').replace('3D', '')
            urls.append(url)

        # abstract and authors
        abstracts, authors = list(), list()
        indices = [(s.start(), e.start()) for s, e in zip(list(re.finditer('</h3><div', email_html)),
                                                            list(re.finditer('<div style=3D\"width:auto\"><table', email_html)))]
        # parse
        for start_index, end_index in indices:
            full_text = email_html[start_index + 34:end_index]
            full_text = full_text.replace('=\r\n', '').replace('\t', '')
            
            paper_authors = full_text[:full_text.index('</div>')]
            abstract = full_text[full_text[6:].index('>') + 35:-6]
            abstract = abstract.replace('<br>', '').replace('=C2=A0=E2=80=A6', '').replace('=C2=A0=E2=80=A6', '')
            authors.append(paper_authors)
            abstracts.append(abstract)        

        papers_list += list(zip(titles, urls, authors, abstracts))
    # remove duplicates
    papers_list = set(papers_list)

    return papers_list


def zotero_papers(zotero_id, library_type, key, force=False):
    """
    Create a DataFrame of the zotero group
    """
    library = zotero.Zotero(zotero_id, library_type, key)
    docs = library.everything(library.top())
    max_nr_tags = 50

    elements = list()
    for doc in docs:
        title, url, abstract, date = doc['data']['title'], doc['data']['url'], doc['data']['abstractNote'], doc['data']['date']
        tags = [tag['tag'] for tag in doc['data']['tags']]
        row = [title, url, abstract, date, tags] + tags + [None] * (max_nr_tags - len(tags))
        elements.append(row)
    df = pandas.DataFrame(elements, columns=['title', 'url', 'abstract', 'date', 'tags'] +
                            ['tags_{0}'.format(i) for i in range(max_nr_tags)])

    return df


def new_papers(email=None, zotero_id=None, zotero_key=None, blacklist=False):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    service = build('gmail', 'v1', credentials=creds)

    # load blacklists
    if os.path.exists('./blacklist_papers.list'):
        with open('./blacklist_papers.list', 'r') as log:
            blacklist_papers = log.readlines()
        blacklist_papers = [paper.replace('\n', '') for paper in blacklist_papers]

    # load known papers
    if zotero_id is not None and zotero_key is not None:
        if not os.path.exists('./zotero_papers.csv'):
            print('Reading zotero papers...')
            zotero_papers_df = zotero_papers(zotero_id, 'group', zotero_key)
            zotero_papers_df.to_csv('./zotero_papers.csv', index=False, sep=';')
            print('Done')
        else:
            print('Loading zotero papers...')
            zotero_papers_df = pandas.read_csv('./zotero_papers.csv', sep=';')
    elif os.path.exists('./zotero_papers.csv'):
        print('Loading zotero papers...')
        zotero_papers_df = pandas.read_csv('./zotero_papers.csv', sep=';')
    
    # find new papers
    print('Reading new emails...')
    unread_papers_emails = get_gmail(service, email)
    scholar_new_papers = papers_from_emails(unread_papers_emails)

    if zotero_id is not None:
        scholar_new_papers = [(paper, abstract, authors, url) for paper, url, authors, abstract in scholar_new_papers
                                if paper not in zotero_papers_df.title.values]
        # filter with blacklist
        scholar_new_papers = [(paper, url, authors, abstract) for paper, url, authors, abstract in scholar_new_papers
                                if paper not in blacklist_papers]
    else:
        scholar_new_papers = list()

    if blacklist:
        with open('./blacklist_papers.list', 'a') as log:
            for paper, url, authors, abstract in scholar_new_papers:
                log.write(paper + '\n')


    if len(scholar_new_papers) > 0:
        print('{0} new papers :('.format(len(scholar_new_papers)))
        for i, (paper, abstract, authors, url) in enumerate(scholar_new_papers):
            print('Paper {0}/{1}'.format(i, len(scholar_new_papers)))
            print('\tTitle: {0}'.format(paper))
            print('\tAbstract: {0}'.format(abstract))
            print('\tAuthors: {0}'.format(authors))
            print('\tURL: {0}'.format(url))
            print('--------\n')
    else:
        print('No new papers :)')

if __name__ == '__main__':
    fire.Fire(new_papers)
